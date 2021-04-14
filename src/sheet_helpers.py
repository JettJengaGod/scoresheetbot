import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pprint
import datetime

from src.db_helpers import gambit_standings, past_gambits, past_bets, ba_standings


def colnum_string(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string


def update_gambit_sheet():
    scope = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file'
    ]
    file_name = '../client_key.json'
    creds = ServiceAccountCredentials.from_json_keyfile_name(file_name, scope)
    client = gspread.authorize(creds)
    sheet = client.open('Fake Gambit').sheet1
    player_to_rank = {}
    player_cols = []
    for rank, member_id, coins, name in gambit_standings():
        player_cols.append([rank, name, coins])
        player_to_rank[member_id] = len(player_cols)

    gambits = {}
    gambit_list = []
    for gamb_id, winner_name, loser_name, winner_total, loser_total, date in past_gambits():
        gambits[gamb_id] = [f'{date.month}/{date.day}/{date.year}', winner_name, loser_name, winner_total,
                            loser_total]
        gambits[gamb_id].extend([''] * len(player_cols))
        gambit_list.append(gamb_id)

    for gamb_id, member_id, result in past_bets():
        gambits[gamb_id][player_to_rank[member_id] + 4] = result

    cols = []
    for gamb_id in gambit_list:
        cols.append(gambits[gamb_id])
    rows = [list(x) for x in zip(*cols)]  # Transpose

    sheet.batch_update([{
        'range': f'A6:C{6 + len(player_cols)}',
        'values': player_cols
    }, {
        'range': f'E1:{colnum_string(len(gambit_list) + 5)}{6 + len(player_cols)}',
        'values': rows
    }])


def update_ba_sheet():
    scope = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file'
    ]
    file_name = '../client_key.json'
    creds = ServiceAccountCredentials.from_json_keyfile_name(file_name, scope)
    client = gspread.authorize(creds)
    sheet = client.open('Battle Arena').sheet1
    player_rows = []
    for name, elo, wins, total in ba_standings():
        player_rows.append([name, elo, '', wins, total - wins])

    sheet.batch_update([{
        'range': f'B9:F{9 + len(player_rows)}',
        'values': player_rows
    }])
