from __future__ import print_function
import pickle
import os.path
import time
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


class CrewCache:
    def __init__(self):
        self.crew_set = self.init_crews()
        self.updated = time.time_ns()

    def init_crews(self) -> set:
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
        crew_info_range = 'Crew Information!A4:A2160'
        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=docs_id,
                                    range=crew_info_range).execute()
        values = result.get('values', [])
        ret = set()
        if not values:
            raise ValueError('Crews Sheet Not Found')
        else:
            for row in values:
                ret.add(row[0])

        self.updated = time.time_ns()
        return ret

    def crews(self) -> set:
        if time.time_ns() - self.updated < 1000000:
            return self.crew_set
        else:
            self.crew_set = self.init_crews()
            return self.crew_set
