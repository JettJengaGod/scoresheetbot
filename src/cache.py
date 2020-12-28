import pickle
import os.path
import time
import discord
from typing import Dict, Iterable, TYPE_CHECKING, Optional

from helpers import strip_non_ascii

if TYPE_CHECKING:
    from .scoreSheetBot import ScoreSheetBot
from constants import *
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from crew import *

# If modifying these scopes, delete the file token.pickle.

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


class Cache:
    def __init__(self):
        self.live: bool = False
        self.crews_by_name: Dict[str, Crew] = {}
        self.main_members: Dict[str, discord.Member] = {}
        self.crews: Iterable[str] = []
        self.overflow_members: Dict[str, discord.Member] = {}
        self.scs: discord.Guild = None
        self.overflow_server: discord.Guild = None
        self.roles = None
        self.channels = None
        self.timer: int = 0
        self.non_crew_roles_main: List[str] = []
        self.non_crew_roles_overflow: List[str] = []
        self.crews_by_tag: Dict[str, Crew] = {}
        self.flairing_allowed: bool = True

    async def update(self, bot: 'ScoreSheetBot'):
        current = time.time_ns()
        if current > self.timer + CACHE_TIME:
            self.crews_by_name = self.update_crews()
            self.crews = self.crews_by_name.keys()
            self.crews_by_tag = {crew.abbr.lower(): crew for crew in self.crews_by_name.values()}
            self.scs = discord.utils.get(bot.bot.guilds, name=SCS)
            self.overflow_server = discord.utils.get(bot.bot.guilds, name=OVERFLOW_SERVER)
            self.roles = self.role_factory(self.scs)
            self.channels = self.channel_factory(self.scs)
            self.main_members = self.members_by_name(self.scs.members)
            self.overflow_members = self.members_by_name(self.overflow_server.members)
            self.crew_populate()
            self.live = True
            self.timer = time.time_ns()
            await self.join_cd_parse(bot)

    @staticmethod
    def role_factory(server):
        class Roles:
            leader = discord.utils.get(server.roles, name=LEADER)
            minion = discord.utils.get(server.roles, name=MINION)
            admin = discord.utils.get(server.roles, name=ADMIN)
            advisor = discord.utils.get(server.roles, name=ADVISOR)
            watchlist = discord.utils.get(server.roles, name=WATCHLIST)
            streamer = discord.utils.get(server.roles, name=STREAMER)
            docs = discord.utils.get(server.roles, name=DOCS)
            certified = discord.utils.get(server.roles, name=CERTIFIED)
            overflow = discord.utils.get(server.roles, name=OVERFLOW_ROLE)
            track1 = discord.utils.get(server.roles, name=TRACK[0])
            track2 = discord.utils.get(server.roles, name=TRACK[1])
            track3 = discord.utils.get(server.roles, name=TRACK[2])
            true_locked = discord.utils.get(server.roles, name=TRUE_LOCKED)
            free_agent = discord.utils.get(server.roles, name=FREE_AGENT)
            join_cd = discord.utils.get(server.roles, name=JOIN_CD)
            playoff = discord.utils.get(server.roles, name=PLAYOFF_LIMITED)

        return Roles

    @staticmethod
    def channel_factory(server):
        class Channels:
            flair_log = discord.utils.get(server.channels, name=FLAIRING_LOGS)
            flairing_questions = discord.utils.get(server.channels, id=FLAIRING_QUESTIONS_ID)
            flairing_info = discord.utils.get(server.channels, name=FLAIRING_INFO)
            doc_keeper = discord.utils.get(server.channels, name=DOC_KEEPER_CHAT)
        return Channels

    def members_by_name(self, member_list: Iterable[discord.Member]) -> Dict[str, discord.Member]:
        out = {}
        for member in member_list:
            for role in member.roles:
                if role.name in self.crews:
                    self.crews_by_name[role.name].member_count += 1
            if member.name:
                out[strip_non_ascii(member.name)] = member
            if member.name != member.display_name and member.display_name:
                out[strip_non_ascii(member.display_name)] = member
        return out

    def update_crews(self) -> Dict[str, Crew]:
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    '../credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('sheets', 'v4', credentials=creds)

        docs_id = '1kZVLo1emzCU7dc4bJrxPxXfgL8Z19YVg1Oy3U6jEwSA'
        crew_info_range = 'Crew Information!A4:D2160'
        legacy_range = 'Legacy Ladder!A4:L200'
        rising_range = 'Rising Ladder!A4:L300'
        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=docs_id,
                                    range=crew_info_range).execute()

        legacy = sheet.values().get(spreadsheetId=docs_id,
                                    range=legacy_range).execute()
        rising = sheet.values().get(spreadsheetId=docs_id,
                                    range=rising_range).execute()
        values = result.get('values', [])

        legacy = legacy.get('values', [])
        rising = rising.get('values', [])
        crews_by_name = {}
        if not values:
            raise ValueError('Crews Sheet Not Found')
        else:
            for row in values:
                crews_by_name[row[0]] = Crew(name=row[0], abbr=row[1], social=row[3])
        if not legacy:
            raise ValueError('Legacy Sheet Not Found')
        else:
            for pos, row in enumerate(legacy):
                if row[0] in crews_by_name.keys():
                    crews_by_name[row[0]].merit = row[2]
                    crews_by_name[row[0]].rank = f'{row[11]} (Legacy rank {row[10]})'
                    crews_by_name[row[0]].ladder = f'({pos+1}/{len(legacy)})'
                elif row[0] != 'Pending Crew':
                    raise Exception(
                        f'There\'s an issue with {row[0]} on the docs, please tag a doc keeper to fix this.')
        if not rising:
            raise ValueError('Rising Sheet Not Found')
        else:
            for row in rising:
                if row[0] in crews_by_name.keys():
                    crews_by_name[row[0]].merit = row[2]
                    crews_by_name[row[0]].rank = f'{row[11]} (Rising rank {row[10]})'
                elif row[0] != 'Pending Crew':
                    raise Exception(
                        f'There\'s an issue with {row[0]} on the docs, please tag a doc keeper to fix this.')
        return crews_by_name

    def crew_populate(self):
        self.non_crew_roles_main = []
        self.non_crew_roles_overflow = []
        for member in self.scs.members:
            crew = self._crew(member)
            if crew:
                for r2 in member.roles:
                    if r2.name == LEADER:
                        self.crews_by_name[crew].leaders.append(str(member))
                    if r2.name == ADVISOR:
                        self.crews_by_name[crew].advisors.append(str(member))
        for role in self.scs.roles:
            if role.name in self.crews_by_name.keys():
                self.crews_by_name[role.name].color = role.color
            elif role.name not in EXPECTED_NON_CREW_ROLES:
                self.non_crew_roles_main.append(role.name)
        for role in self.overflow_server.roles:
            if role.name in self.crews_by_name.keys():
                self.crews_by_name[role.name].color = role.color
                self.crews_by_name[role.name].overflow = True
            elif role.name not in EXPECTED_NON_CREW_ROLES:
                self.non_crew_roles_overflow.append(role.name)

    def flairing_toggle(self):
        self.flairing_allowed = not self.flairing_allowed

    async def join_cd_parse(self, bot: 'ScoreSheetBot'):
        try:
            with open(TEMP_ROLES_FILE, 'r') as file:
                lines = file.readlines()
            with open(TEMP_ROLES_FILE, 'w') as file:
                for line in lines:
                    if len(line) > 17:
                        member_id = int(line[:line.index(' ')])
                        reset = float(line[line.index(' ') + 1:-1])
                        if reset < time.time():
                            member = bot.cache.scs.get_member(member_id)
                            await member.remove_roles(self.roles.join_cd)
                            await self.channels.flair_log.send(f'{member.display_name}\'s join cooldown ended.')
                        else:
                            file.write(line)
        except FileNotFoundError:
            open(TEMP_ROLES_FILE, 'w+')

    def _crew(self, user: discord.Member) -> Optional[str]:
        roles = user.roles
        if any((role.name == OVERFLOW_ROLE for role in roles)):
            overflow_user = self.overflow_server.get_member(user.id)
            if overflow_user:
                roles = overflow_user.roles
            else:
                return None

        for role in roles:
            if role.name in self.crews:
                return role.name
        return None
