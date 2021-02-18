# import gspread
# from oauth2client.service_account import ServiceAccountCredentials
# import pprint
#
# scope = [
#     'https://www.googleapis.com/auth/drive',
#     'https://www.googleapis.com/auth/drive.file'
# ]
# file_name = '../client_key.json'
# creds = ServiceAccountCredentials.from_json_keyfile_name(file_name, scope)
# client = gspread.authorize(creds)
# #Fetch the sheet
# sheet = client.open('Fake Gambit').sheet1
import dataclasses
from src.crew import Crew


@dataclasses.dataclass
class Gambit:
    team1: str
    team2: str
    locked: bool
    bets_1: int = 0
    bets_2: int = 0

    def __str__(self):
        return f'{self.team1} vs {self.team2}\n {self.bets_1} - {self.bets_2}'
