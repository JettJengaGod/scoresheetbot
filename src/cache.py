import pickle
import os.path
import time
import discord
from typing import Dict, Iterable, TYPE_CHECKING, Optional

from .helpers import strip_non_ascii

if TYPE_CHECKING:
    from .scoreSheetBot import ScoreSheetBot
from .constants import *
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from .crew import *

# If modifying these scopes, delete the file token.pickle.

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


class Cache:
    def __init__(self):
        self.crews_by_name: Dict[str, Crew] = {}
        self.main_members: Dict[str, discord.Member] = {}
        self.crews: Iterable[str] = []
        self.overflow_members: Dict[str, discord.Member] = {}
        self.scs: discord.Guild = None
        self.overflow_server: discord.Guild = None
        self.roles = None
        self.channels = None
        self.non_crew_roles_main: List[str] = []
        self.non_crew_roles_overflow: List[str] = []
        self.crews_by_tag: Dict[str, Crew] = {}
        self.flairing_allowed: bool = True

    async def update(self, bot: 'ScoreSheetBot'):
        self.scs = discord.utils.get(bot.bot.guilds, name=SCS)
        self.overflow_server = discord.utils.get(bot.bot.guilds, name=OVERFLOW_SERVER)
        self.channels = self.channel_factory(self.scs)
        self.roles = self.role_factory(self.scs)
        self.crews_by_name = await self.update_crews()
        self.crews = self.crews_by_name.keys()
        self.crews_by_tag = {crew.abbr.lower(): crew for crew in self.crews_by_name.values()}
        self.main_members = self.members_by_name(self.scs.members)
        self.overflow_members = self.members_by_name(self.overflow_server.members)
        self.crew_populate()

    def minor_update(self, bot: 'ScoreSheetBot'):
        self.scs = discord.utils.get(bot.bot.guilds, name=SCS)
        self.overflow_server = discord.utils.get(bot.bot.guilds, name=OVERFLOW_SERVER)

    @staticmethod
    def role_factory(server):
        class Roles:
            leader = discord.utils.get(server.roles, name=LEADER)
            minion = discord.utils.get(server.roles, name=MINION)
            admin = discord.utils.get(server.roles, name=ADMIN)
            advisor = discord.utils.get(server.roles, name=ADVISOR)
            watchlist = discord.utils.get(server.roles, name=WATCHLIST)
            streamer = discord.utils.get(server.roles, name=STREAMER)
            gambit = discord.utils.get(server.roles, name=GAMBIT_ROLE)
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
            everyone = discord.utils.get(server.roles, name='@everyone')

        return Roles

    @staticmethod
    def channel_factory(server):
        class Channels:
            flair_log = discord.utils.get(server.channels, name=FLAIRING_LOGS)
            flairing_questions = discord.utils.get(server.channels, id=FLAIRING_QUESTIONS_ID)
            flairing_info = discord.utils.get(server.channels, name=FLAIRING_INFO)
            recache_logs = discord.utils.get(server.channels, name='recache_logs')
            doc_keeper = discord.utils.get(server.channels, name=DOC_KEEPER_CHAT)
            gambit_announce = discord.utils.get(server.channels, id=GAMBIT_ANNOUNCE)
            gambit_bot = discord.utils.get(server.channels, id=GAMBIT_BOT_ID)

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

    async def update_crews(self) -> Dict[str, Crew]:
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
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        service = build('sheets', 'v4', credentials=creds)

        docs_id = '1kZVLo1emzCU7dc4bJrxPxXfgL8Z19YVg1Oy3U6jEwSA'
        crew_info_range = 'Crew Information!A4:E2160'
        qualifier_range = 'SCL Qualifiers Ladder!A4:L800'
        playoff_range = 'Bot Playoffs!A2:M41'

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=docs_id,
                                    range=crew_info_range).execute()

        qualifiers = sheet.values().get(spreadsheetId=docs_id,
                                        range=qualifier_range).execute()
        playoff = sheet.values().get(spreadsheetId=docs_id,
                                     range=playoff_range).execute()
        values = result.get('values', [])

        qualifiers = qualifiers.get('values', [])
        playoff = playoff.get('values', [])

        crews_by_name = {}
        issues = []
        if not values:
            raise ValueError('Crews Sheet Not Found')
        else:
            for row in values:
                while len(row) < 5:
                    row.append('')
                crews_by_name[row[0]] = Crew(name=row[0], abbr=row[1], social=row[3], icon=row[4])
        if not qualifiers:
            raise ValueError('Qualifiers Sheet Not Found')
        else:
            ranking = 1
            for pos, row in enumerate(qualifiers):
                if row[0] in crews_by_name.keys():
                    crews_by_name[row[0]].merit = row[2]
                    crews_by_name[row[0]].rank = f'Qualifier {row[7]}'
                    crews_by_name[row[0]].ladder = f'({ranking}/{len(qualifiers) - 4})'
                    ranking += 1
                elif row[0] and row[0] not in ('Pending Crew', 'Pending Unregistered Crew'):
                    issues.append(row[0])
        if not playoff:
            raise ValueError('Playoff Sheet Not Found')
        else:
            for row in playoff:
                if row[1] in crews_by_name.keys():
                    crews_by_name[row[1]].playoff = PlayoffType.LEGACY
                    crews_by_name[row[1]].pool = int(row[3])
                if len(row) > 6:
                    if row[6] in crews_by_name.keys():
                        crews_by_name[row[6]].playoff = PlayoffType.EXTREME
                if len(row) > 10:
                    if row[10] in crews_by_name.keys():
                        crews_by_name[row[10]].playoff = PlayoffType.TEMPERED
                        crews_by_name[row[10]].pool = int(row[12])

        if issues:
            issue_string = '\n'.join(issues)
            await self.channels.doc_keeper.send(
                f'{self.roles.docs.mention}, there is is an issue with these crews in the docs'
                f', please fix asap:\n ```{issue_string}```')
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
                self.crews_by_name[role.name].role_id = role.id
            elif role.name not in EXPECTED_NON_CREW_ROLES:
                self.non_crew_roles_main.append(role.name)
        for role in self.overflow_server.roles:
            if role.name in self.crews_by_name.keys():
                self.crews_by_name[role.name].color = role.color
                self.crews_by_name[role.name].role_id = role.id
                self.crews_by_name[role.name].overflow = True
            elif role.name not in EXPECTED_NON_CREW_ROLES:
                self.non_crew_roles_overflow.append(role.name)

    def flairing_toggle(self):
        self.flairing_allowed = not self.flairing_allowed

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
