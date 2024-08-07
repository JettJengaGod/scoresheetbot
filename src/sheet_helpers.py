import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pprint
import datetime
import os
from src.db_helpers import gambit_standings, past_gambits, past_bets, ba_standings, trinity_crews, mc_stats, \
    destiny_crews, wisdom_crews, current_crews

scope = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]
file_name = 'C:/Users/Owner/PycharmProjects/scoresheetbot/client_key.json'
creds = ServiceAccountCredentials.from_json_keyfile_name(file_name, scope)
client = gspread.authorize(creds)
crew_docs_name = 'SCS Crew Docs'  # if os.getenv('VERSION') == 'PROD' else 'Copy of SCS Crew Docs'


def colnum_string(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string


def update_gambit_sheet():
    sheet = client.open(crew_docs_name).worksheet('Gambit')
    player_to_rank = {}
    player_cols = []
    for rank, member_id, total, coins, name in gambit_standings():
        player_cols.append([rank, name, total, coins])
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
        'range': f'A6:D{6 + len(player_cols)}',
        'values': player_cols
    }, {
        'range': f'F1:{colnum_string(len(gambit_list) + 5)}{6 + len(player_cols)}',
        'values': rows
    }])


def update_ba_sheet():
    sheet = client.open(crew_docs_name).worksheet('Battle Arena')
    player_rows = []
    for name, elo, wins, total in ba_standings():
        player_rows.append([name, elo, '', wins, total - wins])

    sheet.batch_update([{
        'range': f'B9:F{9 + len(player_rows)}',
        'values': player_rows
    }])


def update_trinity_sheet():
    sheet = client.open(crew_docs_name).worksheet('Trinity Ladder')
    crew_rows = []

    for name, tag, finished, opp, rating in trinity_crews():
        finished = finished.date().strftime("%m/%d/%y") if finished else ''
        crew_rows.append([name, tag, '', opp or '', finished, '', rating])
    blank_rows = [['', '', '', '', '', '', ''] for _ in range(50)]
    sheet.batch_update([{
        'range': f'A5:G{5 + len(crew_rows)}',
        'values': crew_rows
    }, {
        'range': f'A{5 + len(crew_rows)}:G{5 + len(crew_rows) + 50}',
        'values': blank_rows
    }])


def update_wisdom_sheet():
    sheet = client.open(crew_docs_name).worksheet('Triforce of Wisdom')
    left = []
    right = []

    for name, tag, wins, losses, finished, opp, rating in wisdom_crews():
        finished = finished.date().strftime("%m/%d/%y") if finished else ''
        left.append([name, tag, wins, losses])
        right.append([opp or '', finished, rating])

    blank_left = [['', '', '', ''] for _ in range(50)]
    blank_right = [['', '', ''] for _ in range(50)]
    sheet.batch_update([{
        'range': f'A3:D{3 + len(left)}',
        'values': left
    }, {
        'range': f'F3:H{3 + len(right)}',
        'values': right
    }, {
        'range': f'A{3 + len(left)}:D{3 + len(left) + 50}',
        'values': blank_left
    }, {
        'range': f'F{3 + len(left)}:H{3 + len(left) + 50}',
        'values': blank_right
    }])

def update_rankings_sheet():
    sheet = client.open(crew_docs_name).worksheet('Ultimate Ladder')
    left = []
    right = []

    for name, tag, wins, losses, finished, opp, rating in current_crews():
        finished = finished.date().strftime("%m/%d/%y") if finished else ''
        left.append([name, tag, wins, losses])
        right.append([opp or '', finished, rating])

    blank_left = [['', '', '', ''] for _ in range(50)]
    blank_right = [['', '', ''] for _ in range(50)]
    sheet.batch_update([{
        'range': f'A3:D{3 + len(left)}',
        'values': left
    }, {
        'range': f'F3:H{3 + len(right)}',
        'values': right
    }, {
        'range': f'A{3 + len(left)}:D{3 + len(left) + 50}',
        'values': blank_left
    }, {
        'range': f'F{3 + len(left)}:H{3 + len(left) + 50}',
        'values': blank_right
    }])

def update_destiny_sheet():
    sheet = client.open(crew_docs_name).worksheet('Destiny Ladder')
    crew_rows = []
    right = []
    for name, tag, meter, opp, last_gain, destiny_opp, rank in destiny_crews():
        destiny_opp = destiny_opp if destiny_opp else ''
        crew_rows.append([name, tag, meter])
        right.append(([f'{opp} (+{last_gain})', destiny_opp, rank]))
    blank_rows = [['', '', '', '', '', '', ''] for _ in range(50)]
    sheet.batch_update([{
        'range': f'A5:C{5 + len(crew_rows)}',
        'values': crew_rows
    }, {
        'range': f'E5:G{5 + len(crew_rows)}',
        'values': right
    }, {
        'range': f'A{5 + len(crew_rows)}:G{5 + len(crew_rows) + 50}',
        'values': blank_rows
    }])


def update_bf_sheet():
    sheet = client.open(crew_docs_name).worksheet('Battle Frontier Ladder')
    crew_rows = []
    ratings = []
    rc_crew_rows = []
    rc_ratings = []
    for name, tag, finished, opp, rating, bf in trinity_crews():

        finished = finished.date().strftime("%m/%d/%y") if finished else ''
        if bf:
            crew_rows.append([name, tag, '', opp or '', finished])
            ratings.append([rating])
        else:
            rc_crew_rows.append([name, tag, '', opp or '', finished])
            rc_ratings.append([rating])
    blank_rows = [['', '', '', '', ''] for _ in range(50)]
    blank_col = [[''] for _ in range(50)]
    sheet.batch_update([{
        'range': f'A8:E{8 + len(crew_rows)}',
        'values': crew_rows
    }, {
        'range': f'H8:H{8 + len(ratings)}',
        'values': ratings
    }, {
        'range': f'A{8 + len(crew_rows)}:E{8 + len(crew_rows) + 50}',
        'values': blank_rows
    }, {
        'range': f'H{8 + len(crew_rows)}:H{8 + len(crew_rows) + 50}',
        'values': blank_col
    }])

    sheet = client.open(crew_docs_name).worksheet('Rookie Class Ladder')

    sheet.batch_update([{
        'range': f'A8:E{8 + len(rc_crew_rows)}',
        'values': rc_crew_rows
    }, {
        'range': f'H8:H{8 + len(rc_crew_rows)}',
        'values': rc_ratings
    }, {
        'range': f'A{8 + len(rc_crew_rows)}:E{8 + len(rc_crew_rows) + 50}',
        'values': blank_rows
    }, {
        'range': f'H{8 + len(rc_crew_rows)}:H{8 + len(rc_crew_rows) + 50}',
        'values': blank_col
    }])


def update_mc_player_sheet():
    sheet = client.open(crew_docs_name).worksheet('Master Class Stats')
    pt1, pt2, pt3 = [], [], []
    stats = sorted(mc_stats(), key=lambda x: x[4] / max(x[5], 1), reverse=True)
    for name, tag, pid, taken, weighted_taken, lost, mvps, played, chars in stats:
        pt1.append([name, ', '.join(chars), tag, pid])
        pt2.append([taken, round(weighted_taken, 2), lost])
        pt3.append([mvps, played])

    sheet.batch_update([{
        'range': f'B9:E{9 + len(pt1)}',
        'values': pt1
    }, {
        'range': f'G9:I{9 + len(pt2)}',
        'values': pt2
    }, {
        'range': f'M9:N{9 + len(pt3)}',
        'values': pt3
    }])


def update_mc_sheet():
    sheet = client.open(crew_docs_name).worksheet('Master Class Ranks')
    crew_stats = {}
    for cr_id, name, wins, matches, rating, _, st_taken, st_lost in master_league_crews():
        crew_stats[cr_id] = [name, wins, matches - wins, rating, st_taken, st_lost]

    front = []
    rear = []
    badge = []
    previous_group = 1
    in_group = 0
    for cr_id, group_id, crew_name, group_name, badges in master_listings():
        if cr_id not in crew_stats:
            crew_stats[cr_id] = [crew_name, 0, 0, 2000, 0, 0]
        if previous_group != group_id:
            while in_group < 6:
                front.append([])
                rear.append([])
                badge.append([])
                in_group += 1
            in_group = 0
        front.append(crew_stats[cr_id][0:4])
        rear.append(crew_stats[cr_id][4:])
        badge.append([badges])
        in_group += 1

        previous_group = group_id

    sheet.batch_update([{
        'range': f'B10:E{10 + len(front)}',
        'values': front
    }, {
        'range': f'G10:H{10 + len(front)}',
        'values': rear
    }, {
        'range': f'J10:J{10 + len(front)}',
        'values': badge
    }])


def update_all_sheets():
    # update_mc_sheet()
    # update_bf_sheet()
    # update_ba_sheet()
    # update_mc_player_sheet()
    update_gambit_sheet()
