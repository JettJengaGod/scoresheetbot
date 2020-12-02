import pickle
import os.path
import time
import discord
from typing import Dict, Iterable, TYPE_CHECKING

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
        self.live = False
        self.crews_by_name = None
        self.main_members = None
        self.crews = None
        self.overflow_members = None
        self.scs = None
        self.overflow_server = None
        self.roles = None
        self.channels = None
        self.timer = 0

    def update(self, bot: 'ScoreSheetBot'):
        current = time.time_ns()
        if current > self.timer + CACHE_TIME:
            self.crews_by_name = self.update_crews()
            self.crews = self.crews_by_name.keys()
            self.scs = discord.utils.get(bot.bot.guilds, name=SCS)
            self.overflow_server = discord.utils.get(bot.bot.guilds, name=OVERFLOW_SERVER)
            self.overflow_crews()
            self.roles = self.role_factory(self.scs)
            self.main_members = self.members_by_name(self.scs.members)
            self.overflow_members = self.members_by_name(self.overflow_server.members)
            self.live = True
            self.timer = time.time_ns()

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

        return Roles

    def members_by_name(self, member_list: Iterable[discord.Member]):
        out = {}
        for member in member_list:
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
        crew_info_range = 'Crew Information!A4:B2160'
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
                crews_by_name[row[0]] = Crew(name=row[0], abbr=row[1])
        if not legacy:
            raise ValueError('Legacy Sheet Not Found')
        else:
            for row in legacy:
                if row[0] in crews_by_name.keys():
                    crews_by_name[row[0]].merit = row[2]
                    crews_by_name[row[0]].rank = f'{row[11]} (Legacy rank {row[10]})'
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

    def overflow_crews(self):
        for role in self.overflow_server.roles:
            if role.name in self.crews_by_name.keys():
                self.crews_by_name[role.name].overflow = True
