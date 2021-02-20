import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pprint

from src.db_helpers import gambit_standings, past_gambits, past_bets


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
        player_to_rank[member_id] = rank

    gambits = {}
    gambit_list = []
    for gamb_id, winner_name, loser_name, winner_total, loser_total in past_gambits():
        gambits[gamb_id] = [f'{winner_name} beat {loser_name}', winner_total, loser_total]
        gambits[gamb_id].extend([''] * len(player_cols))
        gambit_list.append(gamb_id)

    for gamb_id, member_id, result in past_bets():
        gambits[gamb_id][player_to_rank[member_id] + 2] = result

    cols = []
    for gamb_id in gambit_list:
        cols.append(gambits[gamb_id])
    rows = [list(x) for x in zip(*cols)]  # Transpose

    sheet.batch_update([{
        'range': f'B4:D{4 + len(player_cols)}',
        'values': player_cols
    }, {
        'range': f'E1:{colnum_string(len(gambit_list)+5)}{4 + len(player_cols)}',
        'values': rows
    }])
