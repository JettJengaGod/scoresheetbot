import datetime
import os
import sys
import traceback
from typing import List, Tuple, Optional, Iterable, Dict, Sequence, Any, Mapping, Set, TYPE_CHECKING
from collections import defaultdict

import discord
import psycopg2

from src.battle import Battle, InfoMatch, TimerMatch, ForfeitMatch, BattleType
from src.character import Character
from src.crew import Crew, DbCrew
from src.db_config import config
from src.elo_helpers import EloPlayer, rating_update
from src.gambit import Gambit
from src.constants import *

if TYPE_CHECKING:
    from src.bracket import Match


def logfile():
    logfilename = 'logs.log'
    if os.path.exists(logfilename):
        append_write = 'a'  # append if already exists
    else:
        append_write = 'w'  # make a new file if not
    logfile = open(logfilename, append_write)
    return logfile


def log_error_and_reraise(error: Exception):
    lf = logfile()
    traceback.print_exception(type(error), error, error.__traceback__, file=lf)
    traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
    lf.close()
    raise error


def add_thanks(user: discord.Member) -> str:
    add = """INSERT into thank (count, userid, username)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    update = """UPDATE thank set count = count +1
    where userid = %s;"""
    find = """SELECT count, username from thank where userid = %s;"""
    total = """SELECT SUM(count) from thank;"""
    conn = None
    ret = ''
    try:
        # read database configuration
        params = config()
        # connect to the PostgreSQL database
        conn = psycopg2.connect(**params)
        # create a new cursor
        cur = conn.cursor()
        # execute the INSERT statement
        cur.execute(add, (0, str(user.id), user.display_name,))
        cur.execute(update, (str(user.id),))
        # get the generated id back
        cur.execute(find, (str(user.id),))
        res = cur.fetchone()
        ret = f'{res[1]} has thanked alexjett {res[0]} times.\n'
        cur.execute(total, )

        res = cur.fetchone()
        ret += f'alexjett has been thanked {res[0]} total times. (Try `,thankboard`)'
        # commit the changes to the database
        conn.commit()
        # close communication with the database
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)

    finally:
        if conn is not None:
            conn.close()
    return ret


def thank_board(user: discord.Member) -> discord.Embed:
    board = """select count, userid, username, 
        RANK() OVER (ORDER BY count DESC) thank_rank from thank;"""
    solo = """SELECT * from (SELECT *, RANK () OVER (ORDER BY count DESC) 
           thank_rank FROM thank) total where userid = %s;"""
    conn = None
    desc = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(board)
        leaderboard = cur.fetchmany(10)
        for entry in leaderboard:
            desc.append(f'{entry[3]}. {entry[2]} <@!{entry[1]}>: {entry[0]}')
        cur.execute(solo, (str(user.id),))
        res = cur.fetchone()
        desc.append(f'\n{user.mention} is rank {res[3]}.')
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return discord.Embed(title='Top thankers!', color=discord.Color.gold(), description='\n'.join(desc))


def add_member_and_roles(member: discord.Member) -> None:
    add_member = """INSERT into members (id, nickname, discord_name)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    add_role = """INSERT into roles (id, name, guild_id)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    add_mem_role = """INSERT into current_member_roles (member_id, role_id, gained)
     values(%s, %s, current_timestamp) ON CONFLICT DO NOTHING;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_member, (member.id, member.display_name, member.name))
        for role in member.roles:
            cur.execute(add_role, (role.id, role.name, role.guild.id))
            cur.execute(add_mem_role, (member.id, role.id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def update_member_roles(member: discord.Member) -> None:
    add_member = """INSERT into members (id, nickname, discord_name)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    find_roles = """SELECT roles.id, roles.name from current_member_roles, roles, members 
                        where members.id = %s 
                            and current_member_roles.member_id = members.id 
                            and roles.id = current_member_roles.role_id
                            and roles.guild_id = %s
                            and roles.name != '@everyone';"""
    add_role = """INSERT into roles (id, name, guild_id)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    add_mem_role = """INSERT into current_member_roles (member_id, role_id, gained)
     values(%s, %s, current_timestamp);"""
    delete_current = """DELETE FROM current_member_roles 
        where member_id = %s
        and role_id = %s
        returning gained;"""

    add_member_history = """INSERT into member_roles_history (member_id, role_id, gained, lost)
     values(%s, %s, %s, current_timestamp);"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_member, (member.id, member.display_name, member.name))
        cur.execute(find_roles, (str(member.id), member.guild.id,))
        returned = cur.fetchall()
        expected = set(row[0] for row in returned)
        actual = set(role.id for role in member.roles if role.name != '@everyone')

        lost = expected - actual
        gained = actual - expected
        for role_id in gained:
            role = member.guild.get_role(role_id)
            cur.execute(add_role, (role.id, role.name, role.guild.id))
            cur.execute(add_mem_role, (member.id, role.id))
        for role_id in lost:
            cur.execute(delete_current, (member.id, role_id,))
            gained = cur.fetchone()[0]
            cur.execute(add_member_history, (member.id, role_id, gained))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def add_member_and_crew(member: discord.Member, crew: Crew) -> None:
    add_member = """INSERT into members (id, nickname, discord_name)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    add_crew = """INSERT into crews (discord_id, name, tag, overflow)
        select %s, %s, %s, %s WHERE
        NOT EXISTS (
            SELECT name FROM crews WHERE name = %s
        );"""
    find_crew = """SELECT id from crews where name = %s;"""
    current_crew = """SELECT member_id, crew_id, joined from current_member_crews where member_id = %s;"""
    delete_current = """DELETE FROM current_member_crews where member_id = %s;"""
    old_crew = """INSERT into member_crews_history (member_id, crew_id, joined, leave)
     values(%s, %s, %s, current_timestamp);"""
    add_member_crew = """INSERT into current_member_crews (member_id, crew_id, joined)
     values(%s, %s, current_timestamp) ON CONFLICT DO NOTHING;"""

    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_member, (member.id, member.display_name, member.name))

        cur.execute(add_crew, (crew.role_id, crew.name, crew.abbr, crew.overflow, crew.name))
        cur.execute(find_crew, (crew.name,))
        crew_id = cur.fetchone()[0]
        cur.execute(current_crew, (member.id,))
        current = cur.fetchone()
        if current:
            if current[1] != crew_id:
                cur.execute(delete_current, (member.id,))
                cur.execute(old_crew, (current[0], current[1], current[2],))
        cur.execute(add_member_crew, (member.id, crew_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def new_crew(crew: Crew):
    add_crew = """INSERT into crews (discord_id, name, tag, overflow)
         select %s, %s, %s, %s WHERE
         NOT EXISTS (
             SELECT name FROM crews WHERE name = %s
         );"""

    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(add_crew, (crew.role_id, crew.name, crew.abbr, crew.overflow, crew.name))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def find_member_roles(member: discord.Member) -> List[str]:
    roles = """SELECT roles.id from current_member_roles, roles, members 
                        where members.id = %s 
                            and current_member_roles.member_id = members.id 
                            and roles.id = current_member_roles.role_id
                            and roles.guild_id = %s
                            and roles.name != '@everyone';"""
    conn = None
    everything = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(roles, (str(member.id), member.guild.id,))
        everything = [row[0] for row in cur.fetchall()]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return everything


def all_member_roles(member_id: int) -> List[int]:
    roles = """SELECT roles.id from current_member_roles, roles, members 
                        where members.id = %s 
                            and current_member_roles.member_id = members.id 
                            and roles.id = current_member_roles.role_id
                            and roles.name != '@everyone';"""
    conn = None
    everything = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(roles, (str(member_id),))
        everything = [row[0] for row in cur.fetchall()]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return everything


def remove_member_role(member_id: int, role_id: int) -> None:
    delete_current = """DELETE FROM current_member_roles 
        where member_id = %s
        and role_id = %s
        returning gained;"""

    add_member_history = """INSERT into member_roles_history (member_id, role_id, gained, lost)
     values(%s, %s, %s, current_timestamp);"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(delete_current, (member_id, role_id,))
        ret = cur.fetchone()
        if ret:
            gained = ret[0]
            cur.execute(add_member_history, (member_id, role_id, gained))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def add_member_role(member_id: int, role_id: int) -> None:
    add_mem_role = """INSERT into current_member_roles (member_id, role_id, gained)
     values(%s, %s, current_timestamp);"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(add_mem_role, (member_id, role_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def crew_id_from_crews(cr: Crew, cursor):
    fr_id = crew_id_from_role_id(cr.role_id, cursor)
    return fr_id if fr_id else crew_id_from_name(cr.name, cursor)


def crew_id_from_name(name: str, cursor) -> int:
    find_crew = """SELECT id from crews where name = %s;"""
    cursor.execute(find_crew, (name,))
    fetched = cursor.fetchone()
    if fetched:
        return fetched[0]
    return None


def crew_id_from_role_id(role_id: int, cursor) -> int:
    find_crew = """SELECT id from crews where discord_id = %s;"""
    cursor.execute(find_crew, (role_id,))
    fetched = cursor.fetchone()
    crew_id = fetched[0] if fetched else None
    return crew_id


def id_from_crew(cr: Crew) -> int:
    cr_id = 0
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        if not cr_id:
            cr_id = crew_id_from_name(cr.name, cur)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return cr_id


def add_character(name: str):
    add_char = """INSERT into fighters (name)
        select %s WHERE
        NOT EXISTS (
            SELECT name FROM fighters WHERE name = %s
        );"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_char, (name, name))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def char_id_from_name(name: str, cursor) -> int:
    find_crew = """SELECT id from fighters where name = %s;"""
    cursor.execute(find_crew, (name,))
    char_id = cursor.fetchone()[0]
    return char_id


def add_finished_battle(battle: Battle, link: str, league: int) -> int:
    add_battle = """INSERT into battle (crew_1, crew_2, final_score, link, winner, finished, league_id, mvps, players)
     values(%s, %s, %s, %s, %s, current_timestamp, %s, %s, %s)  RETURNING id;"""
    add_member_stats = """
            insert into member_stats(member_id) values (%s) on conflict do nothing;"""
    add_mvp = """
        update member_stats set mvps = mvps + 1 where member_id = %s;
    """
    add_match = """INSERT into match (p1, p2, p1_taken, p2_taken, winner, battle_id, p1_char_id, p2_char_id, match_order)
     values(%s, %s, %s, %s, %s, %s, %s, %s, %s);"""

    update_view = """refresh MATERIALIZED view crew_stats;"""

    conn = None
    battle_id = -1
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        mvps = []
        for mvp in battle.team1.mvp() + battle.team2.mvp():
            mvps.append(mvp.id)
            cur.execute(add_member_stats, (mvp.id,))
            cur.execute(add_mvp, (mvp.id,))
        cur.execute(add_battle, (
            crew_id_from_name(battle.team1.name, cur),
            crew_id_from_name(battle.team2.name, cur),
            battle.winner().stocks,
            link,
            crew_id_from_name(battle.winner().name, cur),
            league,
            mvps,
            battle.team1.num_players,
        ))
        battle_id = cur.fetchone()[0]
        for order, match in enumerate(battle.matches):
            if isinstance(match, TimerMatch) or isinstance(match, InfoMatch) or isinstance(match, ForfeitMatch):
                continue
            winner_id = match.p1.id if match.winner == 1 else match.p2.id
            cur.execute(add_match, (
                match.p1.id,
                match.p2.id,
                match.p1_taken,
                match.p2_taken,
                winner_id,
                battle_id,
                char_id_from_name(match.p1.char.base, cur),
                char_id_from_name(match.p2.char.base, cur),
                order
            ))
        # cur.execute(update_view)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return battle_id


def add_non_ss_battle(winner: Crew, loser: Crew, size: int, score: int, link: str, league: int) -> int:
    add_battle = """INSERT into battle (crew_1, crew_2, final_score, link, winner, finished, league_id, players)
     values(%s, %s, %s, %s, %s, current_timestamp, %s, %s)  RETURNING id;"""
    update_view = """refresh MATERIALIZED view crew_stats;"""

    conn = None
    battle_id = -1
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_battle, (
            crew_id_from_crews(winner, cur),
            crew_id_from_crews(loser, cur),
            score,
            link,
            crew_id_from_crews(winner, cur),
            league,
            size,
        ))
        battle_id = cur.fetchone()[0]
        # cur.execute(update_view)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return battle_id


def add_failed_reg_battle(winner: Crew, size: int, score: int, link: str, league: int) -> int:
    add_battle = """INSERT into battle (crew_1, crew_2, final_score, link, winner, finished, league_id, players)
     values(%s, %s, %s, %s, %s, current_timestamp, %s, %s)  RETURNING id;"""
    conn = None
    battle_id = -1
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_battle, (
            crew_id_from_crews(winner, cur),
            339,
            score,
            link,
            crew_id_from_crews(winner, cur),
            league,
            size,
        ))
        battle_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return battle_id


def add_weird_reg_battle(loser: Crew, size: int, score: int, link: str, league: int) -> int:
    add_battle = """INSERT into battle (crew_1, crew_2, final_score, link, winner, finished, league_id, players)
     values(%s, %s, %s, %s, %s, current_timestamp, %s, %s)  RETURNING id;"""
    conn = None
    battle_id = -1
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_battle, (
            crew_id_from_crews(loser, cur),
            339,
            score,
            link,
            339,
            league,
            size,
        ))
        battle_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return battle_id


def battle_elo_changes(battle_id: int, forfeit=False) -> Tuple[
    int, int, int, int, int, int, int, int]:
    find_battle = """
     select winner,
       Case
           when winner = crew_1 then crew_2
           else crew_1 END as loser,
       league_id
from battle
where battle.id = %s;"""

    crew_rating = """with current as (
    insert into crew_ratings(crew_id, league_id) values (%s, %s) on conflict do nothing returning rating, k)
select rating, k from current
union all
select rating, k from crew_ratings where crew_id = %s and league_id = %s;"""

    battle_rating = """insert into battle_ratings (battle_id, crew_id, rating_before, rating_after, league_id)
values (%s, %s, %s, %s, %s);"""

    set_crew_rating = """update crew_ratings
    set rating = %s, k = greatest(k-%s, %s)
        where crew_id = %s and league_id = %s;"""

    set_crew_rating_forfeit = """update crew_ratings
    set rating = %s
        where crew_id = %s and league_id = %s;"""
    winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k = 0, 0, 0, 0, 0, 0, 0, 0
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        # Find the battle
        cur.execute(find_battle, (battle_id,))
        winner, loser, league_id = cur.fetchone()
        # Get the winner rating
        cur.execute(crew_rating, (winner, league_id, winner, league_id))
        winner_elo, winner_k = cur.fetchone()
        winner_player = EloPlayer(winner, winner_elo, winner_k)
        # Get the loser rating
        cur.execute(crew_rating, (loser, league_id, loser, league_id))
        loser_elo, loser_k = cur.fetchone()
        # Losers have default K
        loser_player = EloPlayer(loser, loser_elo, DEFAULT_K)
        # Calculate changes
        winner_change, loser_change = rating_update(winner_player, loser_player, 1)

        # Add battle results
        winner_new_elo = winner_elo + winner_change
        cur.execute(battle_rating, (battle_id, winner, winner_elo, winner_new_elo, league_id))
        loser_new_elo = loser_elo + loser_change
        cur.execute(battle_rating, (battle_id, loser, loser_elo, loser_new_elo, league_id))
        # Update team ratings
        if forfeit:
            cur.execute(set_crew_rating_forfeit, (winner_new_elo, winner, league_id))
            cur.execute(set_crew_rating_forfeit, (loser_new_elo, loser, league_id))
        else:
            cur.execute(set_crew_rating, (winner_new_elo, K_CHANGE, DEFAULT_K, winner, league_id))
            cur.execute(set_crew_rating, (loser_new_elo, K_CHANGE, DEFAULT_K, loser, league_id))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k


def battle_weight_changes(battle_id: int, reverse: bool = False, season: bool = False):
    # TODO modify this to handle MC/BF matches
    find_matches = """select p1, p2, p1_taken, p2_taken from match where battle_id = %s;"""
    mvps = """select mvps from battle where id = %s;"""
    current_weight = """
    with current as (
        insert into member_stats(member_id) values (%s) on conflict do nothing returning weighted_taken, lost)
    select  greatest(weighted_taken, 1) as weighted_taken, greatest(lost, 1) as lost from current
    union all
    select greatest(weighted_taken, 1) as weighted_taken, greatest(lost, 1) as lost from member_stats where member_id = %s;"""

    update_weight = """update member_stats set weighted_taken = weighted_taken + %s, taken = taken + %s,
        lost = lost + %s, played  = played + %s, mvps = mvps + %s
        where member_id = %s;"""
    conn = None
    battle_weight_changes_season(battle_id, reverse)
    if season:
        return
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        # Find the matches
        cur.execute(find_matches, (battle_id,))
        matches = cur.fetchall()
        # Get each performance
        player_weights = {}
        player_taken = defaultdict(int)
        player_weighted_taken = defaultdict(int)
        player_lost = defaultdict(int)
        for p1, p2, p1_taken, p2_taken in matches:
            if p1 not in player_weights:
                cur.execute(current_weight, (p1, p1))
                ret = cur.fetchone()
                if ret:
                    player_weights[p1] = ret[0] / ret[1]
            if p2 not in player_weights:
                cur.execute(current_weight, (p2, p2))
                ret = cur.fetchone()
                if ret:
                    player_weights[p2] = ret[0] / ret[1]
            if reverse:
                player_taken[p1] -= p1_taken
                player_taken[p2] -= p2_taken
                player_weighted_taken[p1] -= p1_taken * player_weights[p2]
                player_lost[p1] -= p2_taken
                player_weighted_taken[p2] -= p2_taken * player_weights[p1]
                player_lost[p2] -= p1_taken
            else:
                player_taken[p1] += p1_taken
                player_taken[p2] += p2_taken
                player_weighted_taken[p1] += p1_taken * player_weights[p2]
                player_lost[p1] += p2_taken
                player_weighted_taken[p2] += p2_taken * player_weights[p1]
                player_lost[p2] += p1_taken

        played = 0 if reverse else 1
        cur.execute(mvps, (battle_id,))
        mvp_list = cur.fetchone()[0]

        for player in player_taken:
            mvp = 1 if player in mvp_list else 0
            cur.execute(update_weight,
                        (player_weighted_taken[player], player_taken[player], player_lost[player], played, mvp, player))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def battle_weight_changes_season(battle_id: int, reverse: bool = False):
    # TODO modify this to handle MC/BF matches
    find_matches = """select p1, p2, p1_taken, p2_taken from match where battle_id = %s;"""
    mvps = """select mvps from battle where id = %s;"""
    current_weight = """
    with current as (
        insert into member_season_stats(member_id) values (%s) on conflict do nothing returning weighted_taken, lost)
    select  greatest(weighted_taken, 1) as weighted_taken, greatest(lost, 1) as lost from current
    union all
    select greatest(weighted_taken, 1) as weighted_taken, greatest(lost, 1) as lost from member_season_stats where member_id = %s;"""

    update_weight = """update member_season_stats set weighted_taken = weighted_taken + %s, taken = taken + %s,
        lost = lost + %s, played  = played + %s, mvps = mvps + %s
        where member_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        # Find the matches
        cur.execute(find_matches, (battle_id,))
        matches = cur.fetchall()
        # Get each performance
        player_weights = {}
        player_taken = defaultdict(int)
        player_weighted_taken = defaultdict(int)
        player_lost = defaultdict(int)
        for p1, p2, p1_taken, p2_taken in matches:
            if p1 not in player_weights:
                cur.execute(current_weight, (p1, p1))
                ret = cur.fetchone()
                if ret:
                    player_weights[p1] = ret[0] / ret[1]
            if p2 not in player_weights:
                cur.execute(current_weight, (p2, p2))
                ret = cur.fetchone()
                if ret:
                    player_weights[p2] = ret[0] / ret[1]
            if reverse:
                player_taken[p1] -= p1_taken
                player_taken[p2] -= p2_taken
                player_weighted_taken[p1] -= p1_taken * player_weights[p2]
                player_lost[p1] -= p2_taken
                player_weighted_taken[p2] -= p2_taken * player_weights[p1]
                player_lost[p2] -= p1_taken
            else:
                player_taken[p1] += p1_taken
                player_taken[p2] += p2_taken
                player_weighted_taken[p1] += p1_taken * player_weights[p2]
                player_lost[p1] += p2_taken
                player_weighted_taken[p2] += p2_taken * player_weights[p1]
                player_lost[p2] += p1_taken

        played = 0 if reverse else 1
        cur.execute(mvps, (battle_id,))
        mvp_list = cur.fetchone()[0]

        for player in player_taken:
            mvp = 1 if player in mvp_list else 0
            cur.execute(update_weight,
                        (player_weighted_taken[player], player_taken[player], player_lost[player], played, mvp, player))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def master_weight_changes(battle_id: int, reverse: bool = False):
    find_matches = """select p1, p2, p1_taken, p2_taken from match where battle_id = %s;"""
    mvps = """select mvps from battle where id = %s;"""
    current_weight = """
    with current as (
        insert into master_member_stats(member_id) values (%s) on conflict do nothing returning weighted_taken, lost)
    select  greatest(weighted_taken, 1) as weighted_taken, greatest(lost, 1) as lost from current
    union all
    select greatest(weighted_taken, 1) as weighted_taken, greatest(lost, 1) as lost from master_member_stats where member_id = %s;"""

    update_weight = """update master_member_stats set weighted_taken = weighted_taken + %s, taken = taken + %s,
        lost = lost + %s, played  = played + %s, mvps = mvps + %s
        where member_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        # Find the matches
        cur.execute(find_matches, (battle_id,))
        matches = cur.fetchall()
        # Get each performance
        player_weights = {}
        player_taken = defaultdict(int)
        player_weighted_taken = defaultdict(int)
        player_lost = defaultdict(int)
        for p1, p2, p1_taken, p2_taken in matches:
            if p1 not in player_weights:
                cur.execute(current_weight, (p1, p1))
                ret = cur.fetchone()
                if ret:
                    player_weights[p1] = ret[0] / ret[1]
            if p2 not in player_weights:
                cur.execute(current_weight, (p2, p2))
                ret = cur.fetchone()
                if ret:
                    player_weights[p2] = ret[0] / ret[1]
            if reverse:
                player_taken[p1] -= p1_taken
                player_taken[p2] -= p2_taken
                player_weighted_taken[p1] -= p1_taken * player_weights[p2]
                player_lost[p1] -= p2_taken
                player_weighted_taken[p2] -= p2_taken * player_weights[p1]
                player_lost[p2] -= p1_taken
            else:
                player_taken[p1] += p1_taken
                player_taken[p2] += p2_taken
                player_weighted_taken[p1] += p1_taken * player_weights[p2]
                player_lost[p1] += p2_taken
                player_weighted_taken[p2] += p2_taken * player_weights[p1]
                player_lost[p2] += p1_taken

        played = 0 if reverse else 1

        cur.execute(mvps, (battle_id,))
        mvp_list = cur.fetchone()[0]

        for player in player_taken:
            mvp = 1 if player in mvp_list else 0
            cur.execute(update_weight,
                        (player_weighted_taken[player], player_taken[player], player_lost[player], played, mvp, player))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def power_rankings() -> List[Tuple[str, int, int, int]]:
    everything = """
select name, coalesce(wins, 0),(coalesce(c2.p2, 0) + coalesce(c1.p1, 0)) as total, tf_group
from crews left join
     (select crew_2, count(*) as p2 from battle where league_id = 22 group by battle.crew_2) as c2 on crew_2 = crews.id
         left join
     (select crew_1, count(*) as p1 from battle where league_id = 22 group by battle.crew_1) as c1 on crew_1 = crews.id
left join

(select winner, count(*) as wins from battle where league_id = 22 group by battle.winner) as w on w.winner = crews.id
where crews.triforce = 2
order by tf_group, coalesce(wins,0)desc;"""
    conn = None
    ids = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        ids = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ids


def courage_rankings() -> List[Tuple[str, int, int, int]]:
    everything = """
select name, coalesce(wins, 0),(coalesce(c2.p2, 0) + coalesce(c1.p1, 0)) as total, tf_group
from crews left join
     (select crew_2, count(*) as p2 from battle where league_id = 21 group by battle.crew_2) as c2 on crew_2 = crews.id
         left join
     (select crew_1, count(*) as p1 from battle where league_id = 21 group by battle.crew_1) as c1 on crew_1 = crews.id
left join

(select winner, count(*) as wins from battle where league_id = 21 group by battle.winner) as w on w.winner = crews.id
where crews.triforce = 1
order by tf_group, coalesce(wins,0)desc;"""
    conn = None
    ids = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        ids = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ids


def wisdom_rankings() -> List[Tuple[int, str, int]]:
    everything = """
    select rank() over(order by rating desc), name, rating
from crews,
     crew_ratings
where crews.disbanded = false
  and crew_ratings.league_id = %s
  and crews.id = crew_ratings.crew_id
order by rating desc;"""
    conn = None
    ids = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything, (CURRENT_LEAGUE_ID,))
        ids = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ids


def all_battle_ids() -> Sequence[int]:
    everything = """SELECT battle.id FROM battle where league_id  in (20, 21, 22) order by battle.id asc ;"""
    conn = None
    ids = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        ids = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ids


def crews_by_rating() -> Sequence[int]:
    everything = """select crews.id from crews where crews.disbanded = false order by crews.id;"""
    conn = None
    ids = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        ids = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ids


def destiny_pair(cr1_id: int, cr2_id: int):
    pair = """update destiny_gain set opponent = %s where crew_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(pair, (cr1_id, cr2_id))
        cur.execute(pair, (cr2_id, cr1_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def destiny_opt(cr_id: int, out: bool):
    pair = """update destiny_gain set opt_out = %s where crew_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(pair, (out, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def destiny_unpair(cr1_id: int, cr2_id: int):
    pair = """update destiny_gain set opponent = null where crew_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(pair, (cr1_id,))
        cur.execute(pair, (cr2_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def current_league_name() -> Tuple[str, datetime.date, bool]:
    name, start_date, reset = "", None, True
    league_name = """select name, start_date,reset from league, current_season where league.id = current_season.league_id;
"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(league_name)
        ret = cur.fetchone()
        if ret:
            name, start_date, reset = ret
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return name, start_date,reset


def destiny_result(winner_id: int, loser_id: int):
    both = """update destiny_gain set current_amount = 0, opponent = null where crew_id in (%s, %s);"""
    winner = """update destiny_gain set rank = rank + 1 where crew_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(both, (winner_id, loser_id))
        cur.execute(winner, (winner_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def battle_info(battle_id: int) -> Tuple[str, str, datetime.date, str]:
    everything = """select c1.name, c2.name, finished, link
from battle,
     crews as c1,
     crews as c2
where c1.id = battle.crew_1
  and c2.id = battle.crew_2
  and battle.id = %s;"""
    conn = None
    crew1, crew2, finished, link = '', '', datetime.datetime.now().date(), ''
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything, (battle_id,))
        ret = cur.fetchone()
        conn.commit()
        cur.close()

        if ret:
            crew1, crew2, finished, link = ret
        else:
            raise ValueError(f'Battle id {battle_id} does not exist.')
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return crew1, crew2, finished.date(), link


def battle_cancel(battle_id: int) -> str:
    # TODO modify this to handle MC/BF matches and finish implementation
    find_mvps = """select mvps, link from battle where id = %s;"""
    move_matches = """with deleted_match as (
        select * FROM match where match.battle_id = %s
    )
    insert into canceled_matches
    select * from deleted_match;"""
    delete_matches = """
        DELETE FROM match where match.battle_id = %s;"""
    decrement_mvp = """ update member_stats set mvps = mvps - 1 where member_id = %s;"""
    move_battle = """with deleted_battle as (
        select * FROM battle where battle.id = %s
    )
    insert into canceled_battle
    select * from deleted_battle;"""
    delete_battle = """
        DELETE FROM battle where battle.id = %s;"""
    find_rating_change = """
    select crew_id, rating_before, rating_after, league_id from battle_ratings
    where battle_id = %s;
    """
    del_battle_rating = """delete from battle_ratings where battle_id = %s;"""

    set_crew_rating = """update crew_ratings
    set rating = rating - %s
        where crew_id = %s and league_id = %s;"""
    link = ''
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        # Find rating change per crew
        cur.execute(find_mvps, (battle_id,))
        ret = cur.fetchone()
        if ret:
            link = ret[1]
            if ret[0]:
                for mvp in ret[0]:
                    cur.execute(decrement_mvp, (mvp,))
        cur.execute(find_rating_change, (battle_id,))
        changes = cur.fetchall()
        for crew_id, rating_before, rating_after, league_id in changes:
            # Update the crews ratings
            rating_change = rating_after - rating_before
            cur.execute(set_crew_rating, (rating_after - rating_before, crew_id, league_id))
        # Delete the rating changes
        cur.execute(del_battle_rating, (battle_id,))
        # Delete the matches
        cur.execute(move_matches, (battle_id,))
        cur.execute(delete_matches, (battle_id,))
        # Delete the battle
        cur.execute(move_battle, (battle_id,))
        cur.execute(delete_battle, (battle_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return link


def crew_correct(member: discord.Member, current: str) -> bool:
    find_crew = """SELECT crews.name
    from current_member_crews, members, crews
        where members.id = %s
            and current_member_crews.member_id = members.id
            and crews.id = current_member_crews.crew_id;"""
    conn = None
    db_crew = ''
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(find_crew, (member.id,))
        db_crew = cur.fetchone()
        if db_crew:
            db_crew = db_crew[0]
        else:
            db_crew = None
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return current == db_crew


def all_crews() -> List[DbCrew]:
    everything = """SELECT discord_id,
       tag,
       name,
       rank,
       overflow,
       watchlisted,
       freezedate,
       verify,
       strikes,
       slotstotal,
       slotsleft,
       decay_level,
       last_battle.finished,
       last_battle.opp,
       id,
       softcap_max,
       coalesce(members.member_count, 0) as member_count,
       triforce,
       hardcap

FROM crews
         left join (select battle.finished                                                              as finished,
                           opp_crew.name || case when battle.winner = crew_id then '(W)' else '(L)' end as opp,
                           newest_battle.crew_id                                                        as cid
                    from (select max(battle.id) as battle_id, crews.id as crew_id
                          from battle,
                               crews
                          where (crews.id = battle.crew_1
                              or crews.id = battle.crew_2)
                          group by crews.id)
                             as newest_battle,
                         battle,
                         crews as opp_crew
                    where newest_battle.battle_id = battle.id
                      and opp_crew.id = case
                                            when newest_battle.crew_id = battle.crew_2 then battle.crew_1
                                            else battle.crew_2 end) as last_battle on last_battle.cid = crews.id
         left join (select count(distinct member_id) as member_count, crew_id
                    from current_member_crews
                    group by crew_id) as members on members.crew_id = crews.id
where disbanded = false;"""
    conn = None
    crews = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        crew_info = cur.fetchall()

        for cr in crew_info:
            crews.append(DbCrew(*cr))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return crews


def all_crew_usage(offset: int = 0) -> List[List]:
    # TODO Update this to handle year too
    everything = """select count(distinct (players.player)) as total, crews.name, crews.id
from (
         select p1 as player, crew_1 as cr
         from match,
              battle
         where match.battle_id = battle.id
           and extract(month from battle.finished) = extract(month from current_timestamp) - %s
           and extract(year from battle.finished) = extract(year from current_timestamp)
         union
         select p2 as player, crew_2 as cr
         from match,
              battle
         where match.battle_id = battle.id
           and extract(month from battle.finished) = extract(month from current_timestamp) - %s
           and extract(year from battle.finished) = extract(year from current_timestamp))
         as players,
     crews
where crews.id = players.cr
group by crews.id
order by total desc;"""
    conn = None
    crews = [[]]
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything, (offset, offset))
        crews = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return crews


def all_crew_destiny() -> List[List]:
    everything = """
        select crew_id, current_amount, c.name, destiny_gain.rank, destiny_gain.opt_out
        from destiny_gain
         left outer join crews c on destiny_gain.opponent = c.id;
    ;"""
    conn = None
    crews = [[]]
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        crews = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return crews


def all_crew_usage_jan(offset: int = 0) -> List[List]:
    if offset == 0:
        return all_crew_usage(0)
    everything = """select count(distinct (players.player)) as total, crews.name, crews.id
from (
         select p1 as player, crew_1 as cr
         from match,
              battle
         where match.battle_id = battle.id
           and extract(month from battle.finished) = 12
           and extract(year from battle.finished) = extract(year from current_timestamp) - 1
         union
         select p2 as player, crew_2 as cr
         from match,
              battle
         where match.battle_id = battle.id
           and extract(month from battle.finished) = 12
           and extract(year from battle.finished) = extract(year from current_timestamp) - 1)
         as players,
     crews
where crews.id = players.cr
group by crews.id
order by total desc;"""
    conn = None
    crews = [[]]
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything, (offset, offset))
        crews = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return crews


def crew_usage(cr: Crew, month_mod: int = 0) -> Dict[int, List[str]]:
    team_1 = """select distinct(p1) as players, battle.link
        from match, battle, crews
            where match.battle_id = battle.id and crews.id = battle.crew_1 and crews.id = %s
            and extract(month from battle.finished) = extract(month from current_timestamp) - %s
            and extract(year from battle.finished) = extract(year from current_timestamp);
            """
    team_2 = """select distinct(p2) as players, battle.link
        from match, battle, crews
            where match.battle_id = battle.id and crews.id = battle.crew_2 and crews.id = %s
            and extract(month from battle.finished) = extract(month from current_timestamp) - %s
            and extract(year from battle.finished) = extract(year from current_timestamp);
            """
    conn = None
    players = {}
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(cr, cur)
        cur.execute(team_1, (cr_id, month_mod))
        t1 = cur.fetchall()
        if t1:
            for member, link in t1:
                if member in players:
                    players[member].append(link)
                else:
                    players[member] = [link]

        cur.execute(team_2, (cr_id, month_mod))
        t2 = cur.fetchall()
        if t2:
            for member, link in t2:
                if member in players:
                    players[member].append(link)
                else:
                    players[member] = [link]

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return players


def crew_usage_jan(cr: Crew, month_mod: int = 0) -> Dict[int, List[str]]:
    team_1 = """select distinct(p1) as players, battle.link
        from match, battle, crews
            where match.battle_id = battle.id and crews.id = battle.crew_1 and crews.id = %s
            and extract(month from battle.finished) = 12
            and extract(year from battle.finished) = extract(year from current_timestamp) - 1;
            """
    team_2 = """select distinct(p2) as players, battle.link
        from match, battle, crews
            where match.battle_id = battle.id and crews.id = battle.crew_2 and crews.id = %s
            and extract(month from battle.finished) = 12
            and extract(year from battle.finished) = extract(year from current_timestamp) - 1;
            """
    conn = None
    players = {}
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(cr, cur)
        cur.execute(team_1, (cr_id,))
        t1 = cur.fetchall()
        if t1:
            for member, link in t1:
                if member in players:
                    players[member].append(link)
                else:
                    players[member] = [link]

        cur.execute(team_2, (cr_id,))
        t2 = cur.fetchall()
        if t2:
            for member, link in t2:
                if member in players:
                    players[member].append(link)
                else:
                    players[member] = [link]

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return players

def set_hardcap(crew: Crew) -> None:
    update_hardcap = """update crews set hardcap = %s where id = %s"""

    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_name(crew.name, cur)
        cur.execute(update_hardcap, (crew.hardcap, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()

def update_crew(crew: Crew) -> None:
    current = """SELECT id, discord_id, tag, name, rank, overflow FROM crews
    where discord_id = %s
    ;"""
    fetch_with_id = """SELECT id, discord_id, tag, name, rank, overflow FROM crews
    where id = %s"""
    history = """INSERT INTO crews_history (crew_id, old_discord_id, old_tag, old_name, old_rank, old_overflow, 
    new_discord_id, new_tag, new_name, new_rank, new_overflow, update_time) 
    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, current_timestamp)"""
    update = """UPDATE crews 
    SET tag = %s, name = %s, rank = %s,overflow = %s, discord_id = %s
    WHERE id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(current, (crew.role_id,))
        old = cur.fetchone()
        if not old:
            cr_id = crew_id_from_name(crew.name, cur)
            cur.execute(fetch_with_id, (cr_id,))
            old = cur.fetchone()
        if not old:
            new_crew(crew)
            cr_id = crew_id_from_name(crew.name, cur)
            cur.execute(fetch_with_id, (cr_id,))
            old = cur.fetchone()
        cur.execute(history,
                    (old[0], old[1], old[2], old[3], old[4], old[5], crew.role_id, crew.abbr, crew.name, None,
                     crew.overflow))
        cur.execute(update, (crew.abbr, crew.name, None, crew.overflow, crew.role_id, old[0]))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()

def hardcap_info(crew: Crew) -> Tuple[int, int]:
    unique_players =  """ SELECT COUNT(DISTINCT player_id) AS unique_players
FROM (
    SELECT p1 AS player_id
    FROM battle
    JOIN match ON match.battle_id = battle.id
    WHERE battle.crew_1 = %s
      AND battle.finished >= date_trunc('month', NOW()) - INTERVAL '1 month'
      AND battle.finished < date_trunc('month', NOW())

    UNION

    SELECT p2 AS player_id
    FROM battle
    JOIN match ON match.battle_id = battle.id
    WHERE battle.crew_2 = %s
      AND battle.finished >= date_trunc('month', NOW()) - INTERVAL '1 month'
      AND battle.finished < date_trunc('month', NOW())
) AS combined_players;"""

    number_of_battles = """select count(*)
from battle
where (crew_1 = %s or crew_2 = %s)
      AND battle.finished >= date_trunc('month', NOW()) - INTERVAL '1 month'
      AND battle.finished < date_trunc('month', NOW());"""

    conn = None
    players, battles = 0, 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_name(crew.name, cur)
        print(crew.name, crew_id)
        cur.execute(unique_players, (crew_id, crew_id))
        res = cur.fetchone()
        if res:
            players = res[0]
        cur.execute(number_of_battles, (crew_id, crew_id,))
        res = cur.fetchone()
        if res:
            battles = res[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return players, battles

def hardcap_info_current(crew: Crew, season_ids: List[int]) -> Tuple[int, int]:
    unique_players =  """ SELECT DISTINCT player_id AS unique_players
FROM (
    SELECT p1 AS player_id
    FROM battle
    JOIN match ON match.battle_id = battle.id
    WHERE battle.crew_1 = %s
      AND battle.finished > date_trunc('month', NOW())

    UNION

    SELECT p2 AS player_id
    FROM battle
    JOIN match ON match.battle_id = battle.id
    WHERE battle.crew_2 = %s
      AND battle.finished > date_trunc('month', NOW())

) AS combined_players;"""

    number_of_battles = """select count(*)
from battle
where (crew_1 = %s or crew_2 = %s)
      AND battle.finished > date_trunc('month', NOW());"""

    conn = None
    players, battles = 0, 0
    player_set = set()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_name(crew.name, cur)
        print(crew.name, crew_id)
        cur.execute(unique_players, (crew_id, crew_id))
        res = cur.fetchall()
        if res:
            for player in res:
                player_set.add(player)

        cur.execute(number_of_battles, (crew_id, crew_id,))
        res = cur.fetchone()
        if res:
            battles += res[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return len(player_set), battles


def update_crew_tomain(crew: Crew, new_role_id: int) -> None:
    current = """SELECT id, discord_id, tag, name, rank, overflow FROM crews
    where id = %s
    ;"""
    history = """INSERT INTO crews_history (crew_id, old_discord_id, old_tag, old_name, old_rank, old_overflow, 
    new_discord_id, new_tag, new_name, new_rank, new_overflow, update_time) 
    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, current_timestamp)"""
    update = """UPDATE crews 
    SET tag = %s, name = %s, rank = %s,overflow = %s, discord_id = %s
    WHERE id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_name(crew.name, cur)
        cur.execute(current, (crew_id,))
        old = cur.fetchone()
        cur.execute(history,
                    (old[0], old[1], old[2], old[3], old[4], old[5], new_role_id, crew.abbr, crew.name, None,
                     False))
        cur.execute(update, (crew.abbr, crew.name, None, False, new_role_id, crew_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def update_member_crew(member_id: int, new_crew: Crew) -> None:
    delete_current = """DELETE FROM current_member_crews where member_id = %s RETURNING member_id, crew_id, joined;"""
    old_crew = """INSERT into member_crews_history (member_id, crew_id, joined, leave)
     values(%s, %s, %s, current_timestamp);"""
    add_member_crew = """INSERT into current_member_crews (member_id, crew_id, joined)
     values(%s, %s, current_timestamp) ON CONFLICT DO NOTHING;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(delete_current, (member_id,))
        current = cur.fetchone()
        if current:
            cur.execute(old_crew, (current[0], current[1], current[2],))
        if new_crew:
            new_id = crew_id_from_role_id(new_crew.role_id, cur)
            if new_id:
                cur.execute(add_member_crew, (member_id, new_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def find_member_crew(member_id: int) -> str:
    find_current = """Select crews.name from crews, current_member_crews 
        where current_member_crews.member_id = %s and crews.id = current_member_crews.crew_id;"""
    conn = None
    crew_name = ''
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(find_current, (member_id,))
        current = cur.fetchone()
        if current:
            crew_name = current[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return crew_name


def cooldown_finished() -> List[int]:
    finished = """ 
        select member_id from 
            (SELECT EXTRACT(epoch FROM age(current_timestamp, gained))/3600 as hours,member_id, roles.name 
                from current_member_roles,roles 
                where roles.id = current_member_roles.role_id and roles.id = 786492456027029515) 
                as b where hours > 12;"""
    conn = None
    current = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(finished)
        current = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return [c[0] for c in current]


def cooldown_current() -> List[Tuple[int, datetime.timedelta]]:
    cooldown = """ 
        select member_id, age(current_timestamp, gained) as hours,member_id, roles.name 
                from current_member_roles,roles 
                where roles.id = current_member_roles.role_id and roles.id = 786492456027029515;"""
    conn = None
    current = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(cooldown)
        current = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return [(c[0], c[1]) for c in current]


def remove_expired_cooldown(user_id: int) -> None:
    cooldown = """ 
        delete from current_member_roles 
            where role_id = 786492456027029515 and member_id=%s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(cooldown, (user_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def all_battles_in_league(league: int) -> List[str]:
    battles = """
    select c1.name as crew_1, c2.name as crew_2, c3.name as winner, battle.link, battle.finished, battle.final_score, 
        battle.vod
        from battle
            join crews c1 on c1.id = battle.crew_1
            join crews c2 on c2.id = battle.crew_2
            join crews c3 on c3.id = battle.winner
            where battle.league_id = %s
            order by battle.id asc;"""
    conn = None
    out = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(battles, (league,))
        everything = cur.fetchall()
        for battle in everything:
            if battle[2] == battle[0]:
                winner = 0
                loser = 1
            else:
                winner = 1
                loser = 0

            out.append(f'**{battle[winner]}** - {battle[loser]} ({battle[5]}-0) [link]({battle[3]})')
            if battle[6]:
                out[-1] += f' [vod]({battle[6]})'
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def all_battles() -> List[str]:
    battles = """
    select c1.name as crew_1, c2.name as crew_2, c3.name as winner, battle.link, battle.finished, battle.final_score, 
        battle.vod
        from battle
            join crews c1 on c1.id = battle.crew_1
            join crews c2 on c2.id = battle.crew_2
            join crews c3 on c3.id = battle.winner
            order by battle.id asc;"""
    conn = None
    out = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(battles)
        everything = cur.fetchall()
        for battle in everything:
            if battle[2] == battle[0]:
                winner = 0
                loser = 1
            else:
                winner = 1
                loser = 0

            out.append(f'**{battle[winner]}** - {battle[loser]} ({battle[5]}-0) [link]({battle[3]})')
            if battle[6]:
                out[-1] += f' [vod]({battle[6]})'
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def crew_record(cr: Crew, league: Optional[int] = 0) -> Tuple:
    record = """
        select * from (select coalesce(wins.name,bttls.name) as name, coalesce(wins.wins,0) as ws, coalesce(bttls.matches,0) as ms  from
        (select crews.name, count(*) as wins 
            from crews, battle 
                where crews.id = battle.winner and crews.id = %s
                    group by crews.name) 
        as wins
        full outer join 
        (select crews.name, count(*) as matches 
            from crews, battle 
                where (crews.id = battle.crew_1 or crews.id = battle.crew_2) and crews.id = %s 
                    group by crews.name
        ) as bttls on bttls.name = wins.name) as crew_wrs;
    """
    record_with_league = """
    select * from (select coalesce(wins.name,bttls.name) as name, coalesce(wins.wins,0) as ws, coalesce(bttls.matches,0) as ms  from
    (select crews.name, count(*) as wins 
        from crews, battle 
            where crews.id = battle.winner and crews.id = %s and battle.league_id = %s 
                group by crews.name) 
    as wins
    full outer join 
    (select crews.name, count(*) as matches 
        from crews, battle 
            where (crews.id = battle.crew_1 or crews.id = battle.crew_2) and crews.id = %s and battle.league_id = %s 
                group by crews.name
    ) as bttls on bttls.name = wins.name) as crew_wrs;
"""
    record_with_season = """
        select * from (select coalesce(wins.name,bttls.name) as name, coalesce(wins.wins,0) as ws, coalesce(bttls.matches,0) as ms  from
        (select crews.name, count(*) as wins 
            from crews, battle 
                where crews.id = battle.winner and crews.id = %s and battle.league_id in (20,21,22)
                    group by crews.name) 
        as wins
        full outer join 
        (select crews.name, count(*) as matches 
            from crews, battle 
                where (crews.id = battle.crew_1 or crews.id = battle.crew_2) and crews.id = %s and battle.league_id in (20,21,22)
                    group by crews.name
        ) as bttls on bttls.name = wins.name) as crew_wrs;
    """
    conn = None
    ret = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_role_id(cr.role_id, cur)
        if league == 20:
            cur.execute(record_with_season, (crew_id, crew_id))
        elif league:
            cur.execute(record_with_league, (crew_id, league, crew_id, league))
        else:
            cur.execute(record, (crew_id, crew_id))
        ret = cur.fetchone()
        if not ret:
            ret = (cr.name, 0, 0)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def crew_matches(cr: Crew) -> List[str]:
    battles = """
    select c1.name as crew_1, c2.name as crew_2, c3.name as winner, battle.link, battle.finished, battle.final_score, 
        battle.vod
        from battle
            join crews c1 on c1.id = battle.crew_1
            join crews c2 on c2.id = battle.crew_2
            join crews c3 on c3.id = battle.winner
            where c1.id = %s or c2.id = %s
            order by battle.id desc;"""
    conn = None
    out = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        cur.execute(battles, (cr_id, cr_id,))
        everything = cur.fetchall()
        for battle in everything:
            if battle[2] == battle[0]:
                winner = 0
                loser = 1
            else:
                winner = 1
                loser = 0
            if battle[winner] == cr.name:
                out.append(f'**({battle[5]}-0)** {battle[loser]}  [link]({battle[3]})')
            else:
                out.append(f'(0-{battle[5]}) {battle[winner]}  [link]({battle[3]})')
            out[-1] += f' {battle[4].strftime("%m/%d/%y")}'
            if battle[6]:
                out[-1] += f' [vod]({battle[6]})'
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def player_stocks(member: discord.Member, season: bool = False) -> Tuple[float, int, int, int]:
    taken = """
    select weighted_taken, taken, lost, mvps from member_stats where member_id = %s;"""

    taken2 = """
    select weighted_taken, taken, lost, mvps from member_season_stats where member_id = %s;"""
    conn = None
    out = []
    vals = (0, 0)
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        query = taken2 if season else taken
        cur.execute(query, (member.id,))
        vals = cur.fetchone()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return vals if vals else (0, 0, 0, 0)


def player_mvps(member: discord.Member) -> int:
    mvps = """
    select count(distinct (battle_id)) as mvps
from (select mvps.battle_id, mvp, sent.id, sent.name
      from (select battle_id, max(taken) as mvp
            from (select battle_id, members.id, fighters.name, sum(p1_taken) as taken
                  from match,
                       members,
                       fighters,
                       battle
                  where members.id = match.p1
                    and fighters.id = match.p1_char_id
                    and match.battle_id = battle.id
                  group by battle_id, members.id, fighters.name) as play
            group by battle_id) as mvps
               inner join
           (select battle_id, members.id, fighters.name, sum(p1_taken) as taken
            from match,
                 members,
                 fighters,
                 battle
            where members.id = match.p1
              and fighters.id = match.p1_char_id
              and match.battle_id = battle.id
            group by battle_id, members.id, fighters.name) as sent
           on sent.battle_id = mvps.battle_id
               and mvps.mvp = sent.taken
      union
      select mvps.battle_id, mvp, sent.id, sent.name
      from (select battle_id, max(taken) as mvp
            from (select battle_id, members.id, fighters.name, sum(p2_taken) as taken
                  from match,
                       members,
                       fighters,
                       battle
                  where members.id = match.p2
                    and fighters.id = match.p2_char_id
                    and match.battle_id = battle.id
                  group by battle_id, members.id, fighters.name) as play
            group by battle_id) as mvps
               inner join
           (select battle_id, members.id, fighters.name, sum(p2_taken) as taken
            from match,
                 members,
                 fighters,
                 battle
            where members.id = match.p2
              and fighters.id = match.p2_char_id
              and match.battle_id = battle.id
            group by battle_id, members.id, fighters.name) as sent
           on sent.battle_id = mvps.battle_id
               and mvps.mvp = sent.taken) as everything
    where everything.id = %s;
;"""
    conn = None
    out = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(mvps, (member.id,))
        out = cur.fetchone()[0]

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def player_chars(member: discord.Member, season: bool = False) -> Tuple[Tuple[int, str]]:
    chars = """
        select coalesce(p1.battle_count,0)+coalesce(p2.battle_count,0) as battle_count, coalesce(p1.name, p2.name) from
            (select count(distinct(match.battle_id)) as battle_count, fighters.name
            from match, fighters where match.p1 = %s 
            and fighters.id = match.p1_char_id
            group by fighters.name) as p1 full outer join (
            (select count(distinct(match.battle_id)) as battle_count, fighters.name
            from match, fighters where match.p2 = %s 
            and fighters.id = match.p2_char_id
        group by fighters.name)) as p2 on p1.name = p2.name
    ;"""
    season_chars = """
    select coalesce(p1.battle_count, 0) + coalesce(p2.battle_count, 0) as battle_count, coalesce(p1.name, p2.name)
from (select count(distinct (match.battle_id)) as battle_count, fighters.name
      from match,
           fighters,
           battle
      where match.p1 = %s
        and fighters.id = match.p1_char_id
        and battle.id = match.battle_id
        and battle.league_id = 33
      group by fighters.name) as p1
         full outer join (
    (select count(distinct (match.battle_id)) as battle_count, fighters.name
     from match,
          fighters,
          battle
     where match.p2 = %s
       and fighters.id = match.p2_char_id

       and battle.id = match.battle_id
       and battle.league_id = 33
     group by fighters.name)) as p2 on p1.name = p2.name;"""
    conn = None
    out = []
    vals = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        query = season_chars if season else chars
        cur.execute(query, (member.id, member.id,))
        vals = cur.fetchall()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return vals


def ba_chars(member: discord.Member) -> Tuple[Tuple[int, str]]:
    chars = """
        select count(distinct(arena_matches.match_number)) as battle_count, fighters.name
            from arena_matches, fighters where arena_matches.member_id = %s
            and fighters.id = any(arena_matches.characters)
            group by fighters.name;"""
    conn = None
    out = []
    vals = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(chars, (member.id,))
        vals = cur.fetchall()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return vals


def set_vod(battle_id: int, vod: str) -> None:
    update = """
        update battle set vod = %s where battle.id = %s
    ;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(update, (vod, battle_id))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
        raise error
    finally:
        if conn is not None:
            conn.close()
    return


def player_record(member: discord.Member, season=False) -> Tuple[int, int]:
    win_loss = """
select p1_total.battles+p2_total.battles as battles, p2_wins.battle_wins+p1_wins.battle_wins as wins from
    (select count(distinct(match.battle_id)) as battles
        from match where match.p1 = %s) as p1_total,
    (select count(distinct(match.battle_id)) as battle_wins
        from match,battle 
            where match.p1 = %s 
            and battle.crew_1=battle.winner 
            and battle.id=match.battle_id) as p1_wins,
    (select count(distinct(match.battle_id)) as battles
        from match where match.p2 = %s) as p2_total,
    (select count(distinct(match.battle_id)) as battle_wins
        from match,battle 
            where match.p2 = %s 
            and battle.crew_2=battle.winner 
            and battle.id=match.battle_id) as p2_wins;"""
    win_loss_season = """
    select p1_total.battles + p2_total.battles as battles, p2_wins.battle_wins + p1_wins.battle_wins as wins
from (select count(distinct (match.battle_id)) as battles
      from match, battle
      where match.p1 = %s
        and battle.id = match.battle_id
        and battle.league_id = 33) as p1_total,
     (select count(distinct (match.battle_id)) as battle_wins
      from match,
           battle
      where match.p1 = %s
        and battle.crew_1 = battle.winner
        and battle.id = match.battle_id
        and battle.league_id = 33) as p1_wins,
     (select count(distinct (match.battle_id)) as battles
      from match, battle
      where match.p2 = %s
        and battle.id = match.battle_id
        and battle.league_id = 33) as p2_total,
     (select count(distinct (match.battle_id)) as battle_wins
      from match,
           battle
      where match.p2 = %s
        and battle.crew_2 = battle.winner
        and battle.id = match.battle_id
        and battle.league_id = 33) as p2_wins;
    """
    conn = None
    out = []
    vals = (0, 0)
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        query = win_loss_season if season else win_loss
        cur.execute(query, (member.id, member.id, member.id, member.id,))
        vals = cur.fetchone()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return vals if vals else (0, 0)


def ba_record(member: discord.Member) -> Tuple[int, int]:
    win_loss = """
select wins.number, losses.number
from (select count(distinct (match_number)) as number
      from arena_matches
      where win = True
        and member_id = %s) as wins,
     (select count(distinct (match_number)) as number
      from arena_matches
      where win = False
        and member_id = %s) as losses;"""
    conn = None
    vals = (0, 0)
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(win_loss, (member.id, member.id))
        vals = cur.fetchone()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return vals if vals else (0, 0)


def freeze_crew(cr: Crew, end: datetime.date):
    freeze = """update crews 
        set freezedate = %s
        where id = %s;
    """
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        cur.execute(freeze, (end, cr_id))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def auto_unfreeze() -> Tuple[Tuple[str]]:
    unfreeze = """update crews
    set freezedate = Null
        where freezedate <= current_date
        returning name;"""
    conn = None
    out = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(unfreeze)
        out = cur.fetchall()
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def disabled_channels() -> Iterable[int]:
    channels = """select * from disabled_channels;"""
    conn = None
    out = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(channels)
        out = cur.fetchall()
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return [o[0] for o in out]


def add_disabled_channel(id_num: int):
    add_channel = """INSERT into disabled_channels (id)
     values(%s) ON CONFLICT DO NOTHING;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_channel, (id_num,))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def remove_disabled_channel(id_num: int):
    del_channel = """delete from disabled_channels where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(del_channel, (id_num,))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def set_command_activation(command_name: int, activation: bool):
    deactivate = """
    INSERT INTO commands (cname, deactivated) values(%s, %s)
    on CONFLICT (cname)
    do update set deactivated = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(deactivate, (command_name, activation, activation))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def command_lookup(command_name: int) -> Tuple[str, bool, int]:
    lookup = """ select * from commands where cname = %s;"""
    add = """ insert into commands (cname) values (%s) returning *;"""
    conn = None
    cmd = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lookup, (command_name,))
        cmd = cur.fetchone()
        if not cmd:
            cur.execute(add, (command_name,))
            cmd = cur.fetchone()
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return cmd


def increment_command_used(command_name: str):
    increment = """ Update commands
                        set called = called + 1
                        where cname = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(increment, (command_name,))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def command_leaderboard():
    leaderboard = """select * from commands order by called desc;"""
    conn = None
    desc = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(leaderboard)
        board = cur.fetchall()
        for entry in board:
            desc.append(f'{entry[0]}: {entry[2]} uses')
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return desc


def new_member_gcoins(member: discord.Member) -> int:
    create = """ insert into gambiters (member_id) values(%s) returning gcoins;"""
    conn = None
    coins = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(create, (member.id,))
        res = cur.fetchone()
        coins = res[0]
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return coins


def refund_member_gcoins(member: discord.Member, amount: int) -> int:
    refund = """ update gambiters set gcoins = gcoins + %s where member_id = %s returning gcoins;"""
    conn = None
    coins = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(refund, (amount, member.id,))
        res = cur.fetchone()
        coins = res[0]
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return coins


def member_gcoins(member: discord.Member) -> int:
    gcoins = """ select gcoins from gambiters where member_id = %s;"""
    conn = None
    coins = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(gcoins, (member.id,))
        res = cur.fetchone()
        if res:
            coins = res[0]
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return coins


def is_gambiter(member: discord.Member) -> bool:
    gcoins = """ select * from gambiters where member_id = %s;"""
    conn = None
    gambiter = False
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(gcoins, (member.id,))
        res = cur.fetchone()
        if res:
            gambiter = True
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return gambiter


def new_gambit(c1: Crew, c2: Crew, message_id: int):
    create = """ insert into current_gambit (team_1, team_2, message_id) values(%s, %s, %s);"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        id_1 = crew_id_from_role_id(c1.role_id, cur)
        id_2 = crew_id_from_role_id(c2.role_id, cur)
        cur.execute(create, (id_1, id_2, message_id))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def current_gambit() -> Gambit:
    teams = """ 
    select c1.name, c2.name, current_gambit.locked, current_gambit.message_id, c1.id, c2.id
        from current_gambit, crews as c1, crews as c2
            where current_gambit.team_1 = c1.id and current_gambit.team_2 = c2.id;"""
    t1_bet = """select coalesce(sum(amount),0)
        from current_gambit
            join current_bets on current_gambit.team_1 = current_bets.team;
    """
    t2_bet = """select coalesce(sum(amount),0)
        from current_gambit
            join current_bets on current_gambit.team_2 = current_bets.team;"""
    top_bet = """
    SELECT nickname, MAX(amount) amount
        FROM current_bets, members, crews
            where team = %s and members.id=current_bets.member_id and crews.id = team
                group by member_id, nickname, crews.name;
    """
    conn = None
    t1, t1_bets, t2, t2_bets, locked, m_id, tb1, tb2 = '', 0, '', 0, True, 0, (), ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(teams)
        crews = cur.fetchone()
        if not crews:
            return None

        t1, t2, locked, m_id, c1_id, c2_id = crews
        cur.execute(t1_bet)
        t1_bets = cur.fetchone()[0]
        cur.execute(t2_bet)
        t2_bets = cur.fetchone()[0]
        cur.execute(top_bet, (c1_id,))

        top_bet_1 = cur.fetchone()
        if top_bet_1:
            tb1 = top_bet_1
        cur.execute(top_bet, (c2_id,))
        top_bet_2 = cur.fetchone()
        if top_bet_2:
            tb2 = top_bet_2

        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return Gambit(t1, t2, locked, m_id, t1_bets, t2_bets, tb1, tb2)


def member_bet(member: discord.Member) -> Tuple[str, int]:
    bet = """ 
    select crews.name, current_bets.amount
        from current_bets, crews
            where current_bets.team = crews.id and current_bets.member_id = %s;"""
    conn = None
    team, amount = '', 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bet, (member.id,))
        res = cur.fetchone()
        if res:
            team, amount = res
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return team, amount


def make_bet(member: discord.Member, cr: Crew, amount: int):
    bet = """ insert into current_bets
        (member_id, amount, team) values (%s, %s, %s)
        on conflict (member_id) do update set amount = current_bets.amount+EXCLUDED.amount ;"""
    deduct = """ update gambiters set gcoins = gcoins - %s where member_id = %s
    returning gcoins;
    """

    conn = None
    coins = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_role_id(cr.role_id, cur)

        cur.execute(bet, (member.id, amount, crew_id))
        cur.execute(deduct, (amount, member.id))
        res = cur.fetchone()
        if res:
            coins = res[0]
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return coins


def archive_bet(member: discord.Member, amount: int, gambit_id: int):
    archive = """ insert into past_bets
        (member_id, result, gambit_id) values (%s, %s, %s);"""

    conn = None
    coins = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(archive, (member.id, amount, gambit_id))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return coins


def lock_gambit(status: bool):
    lock = """ update current_gambit set locked = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lock, (status,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def all_bets() -> Tuple[Tuple[int, int, str]]:
    bet_list = """select member_id, amount, name
        from current_bets, crews where team = crews.id;"""
    conn = None
    bets = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bet_list)
        bets = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return bets


def cancel_gambit():
    cancel = """delete from current_gambit;"""
    remove_bets = "delete from current_bets;"
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(cancel)
        cur.execute(remove_bets)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def archive_gambit(winner: str, loser: str, winning_total: int, losing_total: int) -> int:
    archive = """insert into gambit_results (winning_crew, losing_crew, winning_total, losing_total, finished)
     values(%s, %s, %s, %s, current_date) returning id;"""
    conn = None
    gambit_id = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        winner_id = crew_id_from_name(winner, cur)
        loser_id = crew_id_from_name(loser, cur)
        cur.execute(archive, (winner_id, loser_id, winning_total, losing_total))
        gambit_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return gambit_id


def gambit_standings() -> Tuple[Tuple[int, int, int, int, str]]:
    leaderboard = """
        select RANK() OVER (ORDER BY gcoins + coalesce(spent, 0) DESC) gamb_rank,
           member_id,
           coalesce(spent, 0) + gcoins as                          total,
           gcoins,
           discord_name
    from gambiters
             full outer join (select sum(amount) as spent, member_id as cm_id
                              from charge_history
                              group by member_id) as charge on cm_id = gambiters.member_id,
         members
    where member_id = id;"""
    conn = None
    standings = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(leaderboard)
        standings = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return standings


def past_gambits() -> Tuple[Tuple[int, str, str, int, int, datetime.date]]:
    matches = """select gambit_results.id, c1.name, c2.name, winning_total, losing_total, finished
        from gambit_results, crews as c1, crews as c2 
            where c1.id = winning_crew and c2.id = losing_crew order by id desc ;"""
    conn = None
    all_past = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(matches)
        all_past = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return all_past


def past_bets() -> Tuple[Tuple[int, int, int]]:
    bets = """select gambit_id, member_id, result from past_bets;"""
    conn = None
    all_past = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bets)
        all_past = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return all_past


def crew_flairs() -> Dict[str, int]:
    flairs = """
    select crews.name, count(member_id) as total
        from current_member_crews, crews
            where crew_id = crews.id and DATE_PART('day', current_timestamp - joined) <30
                group by crews.name, crews.id
                    order by total desc;"""
    old_flairs = """
    select count(distinct(member_id)) as total, crews.name
        from member_crews_history, crews
            where crew_id = crews.id and DATE_PART('day', current_timestamp - joined) <30
            and member_id != 775586622241505281
                group by crews.name, crews.id
                    order by total desc;"""
    conn = None
    cr = {}
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(flairs)
        new = cur.fetchall()
        for name, count in new:
            cr[name] = count

        cur.execute(old_flairs)
        old = cur.fetchall()
        for count, name in old:
            if name in cr:
                cr[name] += count
            else:
                cr[name] = count
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return cr


def slots(cr: Crew) -> Tuple[int, int]:
    both = """SELECT slotsleft, slotstotal FROM crews where id = %s;"""
    conn = None
    slot = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        cur.execute(both, (cr_id,))
        slot = cur.fetchone()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return slot


def extra_slots(cr: Crew) -> Tuple[int, int, int]:
    both = """SELECT slotsleft, slotstotal, unflair FROM crews where id = %s;"""
    conn = None
    slot = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        cur.execute(both, (cr_id,))
        slot = cur.fetchone()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return slot


def mod_slot(cr: Crew, change: int) -> int:
    mod = """update crews set slotsleft = slotsleft + %s
                where id = %s returning slotsleft;"""
    conn = None
    after = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        cur.execute(mod, (change, cr_id))
        after = cur.fetchone()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return after


def cur_slot_set(cr: Crew, change: int) -> int:
    mod = """update crews set slotsleft = %s
                where id = %s returning slotsleft;"""
    conn = None
    after = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr.role_id, cur)
        cur.execute(mod, (change, cr_id))
        after = cur.fetchone()[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return after


def total_slot_set(cr: Crew, total: int) -> None:
    set = """update crews set slotsleft = %s, slotstotal = %s
                where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(cr, cur)
        if not total or not cr_id:
            print(cr.name)
            return
        cur.execute(set, (total, total, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def softcap_set(cr: Crew, softcap_max: int) -> None:
    set = """update crews set softcap_max = %s
                where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(cr, cur)
        if not softcap_max or not cr_id:
            print(cr.name)
            return
        cur.execute(set, (softcap_max, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def member_crew_history(member_id: int) -> List[Tuple[str, datetime.datetime, bool]]:
    joins = """select crews.name, joined
                from crews, flairs
                    where crews.id = flairs.crew_id
                        and flairs.member_id = %s
                            order by joined;"""
    leaves = """select crews.name, leave_time
                from crews, unflairs
                    where crews.id = unflairs.crew_id
                        and unflairs.member_id = %s
                            order by leave_time;"""
    conn = None
    hist = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(joins, (member_id,))
        join_list = cur.fetchall()
        for join in join_list:
            hist.append((join[0], join[1], True))
        cur.execute(leaves, (member_id,))
        leave_list = cur.fetchall()
        for leave in leave_list:
            hist.append((leave[0], leave[1], False))
        if hist:
            hist.sort(key=lambda x: x[1])
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return hist


def member_crew_and_date(member_id: int) -> Tuple[str, datetime.datetime]:
    current = """select crews.name, joined
                from crews, current_member_crews
                    where crews.id = current_member_crews.crew_id
                        and current_member_crews.member_id = %s
                            order by joined;"""
    conn = None
    cr = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(current, (member_id,))
        cr = cur.fetchone()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return cr


def record_flair(member: discord.Member, crew: Crew):
    record = """INSERT into flairs (member_id, crew_id, joined)
     values(%s, %s, current_timestamp) ON CONFLICT DO NOTHING;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(record, (member.id, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def record_unflair(member_id: int, crew: Crew, join_cd: bool) -> Tuple[int, int, int]:
    record = """INSERT into unflairs (member_id, crew_id, leave_time)
     values(%s, %s, current_timestamp);"""
    cr_record = """update crews set unflair = unflair + 1 where id = %s returning unflair;"""
    reset = """update crews set unflair = 0, slotsleft = slotsleft+1  where id = %s;"""
    slot = """SELECT slotsleft, slotstotal FROM crews where id = %s;"""
    conn = None
    unflairs, remaining, total = 0, 0, 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(record, (member_id, cr_id))
        if not join_cd:
            cur.execute(cr_record, (cr_id,))
            unflairs = cur.fetchone()[0]
            if unflairs == 3:
                cur.execute(reset, (cr_id,))
        cur.execute(slot, (cr_id,))
        remaining, total = cur.fetchone()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return unflairs, remaining, total


def set_return_slots(crew: Crew, number: int) -> Tuple[int, int, int]:
    cr_record = """update crews set unflair = %s where id = %s returning unflair;"""
    reset = """update crews set unflair = 0, slotsleft = slotsleft+1  where id = %s;"""
    slot = """SELECT slotsleft, slotstotal FROM crews where id = %s;"""
    conn = None
    unflairs, remaining, total = 0, 0, 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(cr_record, (number, cr_id,))
        unflairs = cur.fetchone()[0]
        if unflairs == 3:
            cur.execute(reset, (cr_id,))
            unflairs = 0
        cur.execute(slot, (cr_id,))
        remaining, total = cur.fetchone()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return unflairs, remaining, total


def disband_crew(crew: Crew) -> None:
    disband = """update crews set disbanded = TRUE,
     tag = tag || %s, name = name || %s
    where crews.id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        today = datetime.date.today()
        month = today.month
        year = today.year
        disband_str = f'(Dis {month}/{year})'
        cur.execute(disband, (disband_str, disband_str, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def disband_crew_from_id(cr_id) -> None:
    disband = """update crews set disbanded = TRUE,
     tag = tag || %s, name = name || %s
    where crews.id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_role_id(cr_id, cur)
        today = datetime.date.today()
        month = today.month
        year = today.year
        disband_str = f'(Dis {month}/{year})'
        cur.execute(disband, (disband_str, disband_str, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def ba_elo(member: discord.Member) -> int:
    member_elo = """select elo, k from arena_members where member_id = %s;"""
    conn = None
    out = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(member_elo, (member.id,))
        res = cur.fetchone()
        if res:
            out = res[0]

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def get_member_elo(member_id: int) -> Optional[EloPlayer]:
    member_elo = """select elo, k from arena_members where member_id = %s;"""
    add_new_member = """insert into arena_members (member_id) values(%s)
      returning elo, k;"""
    conn = None
    player = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(member_elo, (member_id,))
        elo = cur.fetchone()
        if not elo:
            cur.execute(add_new_member, (member_id,))
            elo = cur.fetchone()
        player = EloPlayer(member_id, elo[0], elo[1])
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return player


def add_ba_match(winner: EloPlayer, loser: EloPlayer, winner_chars: List[Character], loser_chars: List[Character],
                 winner_rating_change,
                 loser_rating_change, winner_score, loser_score):
    add_winner_match = """insert into arena_matches 
    (member_id, win, characters, score, elo_before, elo_after, opponent_score) 
        values (%s, True, %s, %s, %s, %s, %s) returning match_number;"""
    add_loser_match = """insert into arena_matches 
    (match_number, member_id, win, characters, score, elo_before, elo_after, opponent_score) 
        values (%s, %s, FALSE, %s, %s, %s, %s, %s) returning match_number;"""
    update_elo = """
    update arena_members
    set elo = %s
        where member_id = %s;"""
    conn = None
    try:

        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        winner_char_ids = [char_id_from_name(char.base, cur) for char in winner_chars]
        cur.execute(add_winner_match, (
            winner.member_id, winner_char_ids, winner_score, winner.rating, winner.rating + winner_rating_change,
            loser_score))

        match_number = cur.fetchone()[0]

        loser_char_ids = [char_id_from_name(char.base, cur) for char in loser_chars]
        cur.execute(add_loser_match, (
            match_number, loser.member_id, loser_char_ids, loser_score, loser.rating,
            loser.rating + loser_rating_change,
            winner_score))

        cur.execute(update_elo, (winner.rating + winner_rating_change, winner.member_id))
        cur.execute(update_elo, (loser.rating + loser_rating_change, loser.member_id))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def ba_standings() -> Tuple[Tuple[str, int, int, int]]:
    leaderboard = """select members.nickname, arena_members.elo, count(distinct(wins.match_number)) as wins, count(distinct (total.match_number)) as combined
    from arena_members, arena_matches as wins, arena_matches as total, members
        where arena_members.member_id = wins.member_id
            and members.id = wins.member_id and wins.member_id = total.member_id
                and wins.win = True
                    group by members.id, arena_members.member_id
                        order by arena_members.elo desc;
"""
    conn = None
    standings = ()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(leaderboard)
        standings = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return standings


def db_crew_members(cr: Crew) -> List[int]:
    mems = """select member_id
    from current_member_crews
    where crew_id = %s;
"""
    conn = None
    members = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_crews(cr, cur)
        cur.execute(mems, (crew_id,))
        members = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return [mem[0] for mem in members]


def name_from_id(mem_id: int) -> str:
    get_name = """select discord_name
        from members
        where id = %s;
    """
    conn = None
    name = ''
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(get_name, (mem_id,))
        ret = cur.fetchone()
        if ret:
            name = ret[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return name


def first_crew_flair(cr: Crew) -> datetime.date:
    get_first = """select joined
    from current_member_crews where crew_id = %s
union select joined
    from member_crews_history where crew_id = %s
order by joined
limit 1;"""
    conn = None
    first = datetime.datetime.now()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        crew_id = crew_id_from_crews(cr, cur)
        cur.execute(get_first, (crew_id, crew_id))
        ret = cur.fetchone()
        if ret:
            first = ret[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return first.date()


def wisdom_crews() -> Sequence[Tuple[str, str, int, int, datetime.datetime, str, int]]:
    bf_crews = """select crews.name,
       crews.tag,
       coalesce(battles.wins, 0),
       coalesce(battles.losses, 0),
       last_battle.finished,
       last_battle.opp,
       crew_ratings.rating
from crew_ratings,
     (select count(*) as cc
      from crew_ratings,
           crews
      where league_id = 20
        and crew_id = crews.id
        and crews.disbanded = FALSE) crew_count,
     crews
         left join (select battle.finished                                                              as finished,
                           opp_crew.name || case when battle.winner = crew_id then '(W)' else '(L)' end as opp,
                           newest_battle.crew_id                                                        as cid
                    from (select max(battle.id) as battle_id, crews.id as crew_id
                          from battle,
                               crews
                          where (crews.id = battle.crew_1
                              or crews.id = battle.crew_2)
                          group by crews.id)
                             as newest_battle,
                         battle,
                         crews as opp_crew
                    where newest_battle.battle_id = battle.id
                      and opp_crew.id = case
                                            when newest_battle.crew_id = battle.crew_2 then battle.crew_1
                                            else battle.crew_2 end) as last_battle on last_battle.cid = crews.id
         left join (select count(case when battle.winner = crews.id then 1 end)  as wins,
                           count(case when battle.winner != crews.id then 1 end) as losses,
                           crews.id                                              as crew
                    from battle,
                         crews
                    where (crews.id = battle.crew_1
                        or crews.id = battle.crew_2)
                      and battle.league_id = 20
                    group by crews.id) as battles on battles.crew = crews.id

where crew_ratings.crew_id = crews.id
  and crew_ratings.league_id = 20
  and crews.disbanded = false
order by rating desc;
"""
    conn = None
    ret = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bf_crews)
        ret = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def current_crews() -> Sequence[Tuple[str, str, int, int, datetime.datetime, str, int]]:
    bf_crews = """select crews.name,
       crews.tag,
       coalesce(battles.wins, 0),
       coalesce(battles.losses, 0),
       last_battle.finished,
       last_battle.opp,
       crew_ratings.rating
from crew_ratings,
     (select count(*) as cc
      from crew_ratings,
           crews
      where league_id = %s
        and crew_id = crews.id
        and crews.disbanded = FALSE) crew_count,
     crews
         left join (select battle.finished                                                              as finished,
                           opp_crew.name || case when battle.winner = crew_id then '(W)' else '(L)' end as opp,
                           newest_battle.crew_id                                                        as cid
                    from (select max(battle.id) as battle_id, crews.id as crew_id
                          from battle,
                               crews
                          where (crews.id = battle.crew_1
                              or crews.id = battle.crew_2)
                          group by crews.id)
                             as newest_battle,
                         battle,
                         crews as opp_crew
                    where newest_battle.battle_id = battle.id
                      and opp_crew.id = case
                                            when newest_battle.crew_id = battle.crew_2 then battle.crew_1
                                            else battle.crew_2 end) as last_battle on last_battle.cid = crews.id
         left join (select count(case when battle.winner = crews.id then 1 end)  as wins,
                           count(case when battle.winner != crews.id then 1 end) as losses,
                           crews.id                                              as crew
                    from battle,
                         crews
                    where (crews.id = battle.crew_1
                        or crews.id = battle.crew_2)
                      and battle.league_id = %s
                    group by crews.id) as battles on battles.crew = crews.id

where crew_ratings.crew_id = crews.id
  and crew_ratings.league_id = %s
  and crews.disbanded = false
order by rating desc;
"""
    conn = None
    ret = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bf_crews, (CURRENT_LEAGUE_ID,CURRENT_LEAGUE_ID,CURRENT_LEAGUE_ID))
        ret = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def crew_to_last_played() -> Sequence[Tuple[str, datetime.datetime]]:
    crews_and_battles = """
    select crews.name, last_battle.finished
     from crews
        left join ( select battle.finished, newest_battle.crew_id
from (select max(battle.id) as battle_id, crews.id as crew_id
      from battle,
           crews
      where (crews.id = battle.crew_1
          or crews.id = battle.crew_2) and battle.league_id = %s
      group by crews.id)
         as newest_battle,
     battle
    where newest_battle.battle_id = battle.id) as last_battle on last_battle.crew_id = crews.id
where disbanded = false;
    ;
"""
    conn = None
    ret = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(crews_and_battles, (CURRENT_LEAGUE_ID,))
        ret = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def trinity_crews() -> Sequence[Tuple[str, str, datetime.datetime, str, int]]:
    bf_crews = """
select crews.name,
       crews.tag,
       last_battle.finished,
       last_battle.opp,
       crew_ratings.rating
from crew_ratings,
     (select count(*) as cc
      from crew_ratings,
           crews
      where league_id = 16
        and crew_id = crews.id
        and crews.disbanded = FALSE) crew_count,
     crews
         left join (select battle.finished                                                              as finished,
                           opp_crew.name || case when battle.winner = crew_id then '(W)' else '(L)' end as opp,
                           newest_battle.crew_id                                                        as cid
                    from (select max(battle.id) as battle_id, crews.id as crew_id
                          from battle,
                               crews
                          where (crews.id = battle.crew_1
                              or crews.id = battle.crew_2)
                          group by crews.id)
                             as newest_battle,
                         battle,
                         crews as opp_crew
                    where newest_battle.battle_id = battle.id
                      and opp_crew.id = case
                                            when newest_battle.crew_id = battle.crew_2 then battle.crew_1
                                            else battle.crew_2 end) as last_battle on last_battle.cid = crews.id

where crew_ratings.crew_id = crews.id
  and crew_ratings.league_id = 16
  and crews.disbanded = false
order by rating desc;
"""
    conn = None
    ret = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bf_crews)
        ret = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def destiny_crews() -> Sequence[Tuple[str, str, int, str, int, str, int]]:
    bf_crews = """
    select crews.name,
           crews.tag,
           destiny_gain.current_amount,
           last_battle.opp,
           destiny_gain.last_gain,
           c.name,
           destiny_gain.rank
    from destiny_gain
             left outer join crews c on destiny_gain.opponent = c.id,
         (select count(*) as cc
          from crew_ratings,
               crews
          where league_id = 16
            and crew_id = crews.id
            and crews.disbanded = FALSE) crew_count,
         crews
             left join (select battle.finished                                                              as finished,
                               opp_crew.name as opp,
                               newest_battle.crew_id                                                        as cid
                        from (select max(battle.id) as battle_id, crews.id as crew_id
                              from battle,
                                   crews
                              where (crews.id = battle.winner)
                                and battle.league_id = 16
                              group by crews.id)
                                 as newest_battle,
                             battle,
                             crews as opp_crew
                        where newest_battle.battle_id = battle.id
                          and opp_crew.id = case
                                                when newest_battle.crew_id = battle.crew_2 then battle.crew_1
                                                else battle.crew_2 end) as last_battle on last_battle.cid = crews.id
    
    where destiny_gain.crew_id = crews.id
      and crews.disbanded = false
      and destiny_gain.opt_out = false
    order by rank desc, current_amount desc;
"""
    conn = None
    ret = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(bf_crews)
        ret = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def init_rating(crew: Crew, rating: int, k: int = STARTING_K):
    set_rating = """insert into crew_ratings (crew_id, league_id, rating, k) 
    values (%s, %s, %s, %s) ON CONFLICT DO NOTHING;
    """
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        if not cr_id:
            print(f'{crew.name} not in DB!')
            return
        cur.execute(set_rating, (cr_id, CURRENT_LEAGUE_ID, rating, k))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return

def reset_k( k: int = DEFAULT_K):
    set_rating = """update crew_ratings set k = %s where league_id = %s;
    """
    set_reset = """update current_season set reset = true where league_id = %s;
    """
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(set_rating, ( k, CURRENT_LEAGUE_ID))

        cur.execute(set_reset, (CURRENT_LEAGUE_ID,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def init_crew_rating(crew_id: int, rating: int, league_id: int):
    set_rating = """insert into crew_ratings (crew_id, league_id, rating, k) VALUES (
    %s, %s, %s, %s) on conflict (crew_id, league_id) do nothing ;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(set_rating, (crew_id, league_id, rating, STARTING_K))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def reset_fake_crew_rating(league_id: int):
    set_rating = """update crew_ratings
    set rating = 1500
        where crew_id = 339 and league_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(set_rating, (league_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def mc_stats() -> Sequence[Tuple[str, int, int, float, int, int, int, List[str]]]:
    get_stats = """select members.discord_name,
       crews.tag,
       members.id,
       master_member_stats.taken,
       master_member_stats.weighted_taken,
       master_member_stats.lost,
       master_member_stats.mvps,
       master_member_stats.played
from members,
     current_member_crews,
     crews,
     master_member_stats
where members.id = current_member_crews.member_id
    and current_member_crews.crew_id = crews.id
    and master_member_stats.member_id = members.id;
    """
    # TODO update this to order by usage and only use master class
    get_chars = """select fighters.name, picks.pid
from (
         select distinct(match.p1_char_id) as cid, p1 as pid
         from match
         union
         select distinct (match.p2_char_id) as cid, p2 as pid
         from match) as picks,
     fighters
where fighters.id = picks.cid;
    """
    conn = None
    out = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(get_chars)
        chars = defaultdict(list)
        for name, pid in cur.fetchall():
            chars[pid].append(name)

        cur.execute(get_stats)
        ret = cur.fetchall()
        for name, tag, pid, taken, weighted_taken, lost, mvps, played in ret:
            out.append((name, tag, pid, taken, weighted_taken, lost, mvps, played, chars[pid]))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def crew_rankings() -> Mapping[str, Tuple[int, int, int]]:
    ranking = """
    select crews.name,
           crew_id,
           rank() over (order by rating desc) placement,
           rating,
            crew_count.cc
    from crew_ratings,
         crews,
         (select count(*) as cc
      from crew_ratings,
           crews
      where league_id = %s
        and crew_id = crews.id
        and crews.disbanded = FALSE) crew_count
    where league_id = %s
      and crew_ratings.crew_id = crews.id
      and crews.disbanded = false;
    """
    conn = None
    mapping = {}
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()

        cur.execute(ranking, (CURRENT_LEAGUE_ID,CURRENT_LEAGUE_ID))
        ret = cur.fetchall()
        if ret:
            for name, _, rank, rating, count in ret:
                mapping[name] = (rank, rating, len(ret))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return mapping


def charge(member_id: int, amount: int, reason: str = 'None Specified') -> int:
    gcoins = """ update gambiters set gcoins = gcoins - %s 
    where member_id = %s returning gcoins;"""
    history = """insert into charge_history (member_id, amount, reason) VALUES (%s, %s, %s)
    """
    conn = None
    coins = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(gcoins, (amount, member_id,))
        res = cur.fetchone()
        if res:
            coins = res[0]
        cur.execute(history, (member_id, amount, reason))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return coins


def record_nicknames(member_nicks: Sequence[Tuple[int, str]]):
    record = """update members set nickname = %s where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        for i, nick in enumerate(member_nicks):
            cur.execute(record, (nick[1], nick[0]))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return

def elo_decay(crew: Crew, amount: int):
    modify = """update crews set decay_level = decay_level+1 where id = %s;"""
    record = """insert into elo_decay (crew_id, amount, league_id, happened) values
    (%s, %s, 8, CURRENT_TIMESTAMP);"""
    reduce = """update crew_ratings set rating = rating - %s 
    where crew_id = %s and league_id = 16;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(modify, (cr_id,))
        cur.execute(record, (cr_id, amount))
        cur.execute(reduce, (amount, cr_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def reset_decay(crew: Crew):
    modify = """update crews set decay_level = 0 where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(modify, (cr_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def nickname_lookup(member_id: int) -> str:
    lookup = """ select nickname from members where id = %s;"""
    conn = None
    name = ''
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lookup, (member_id,))
        res = cur.fetchone()
        if res:
            name = res[0]
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return name


def members_in_server() -> Tuple[Set[int], Set[int]]:
    lookup = """ select id, in_server from members;"""
    conn = None
    in_server, out_server = set(), set()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lookup)
        res = cur.fetchall()
        if res:
            for mem_id, location in res:
                if location:
                    in_server.add(mem_id)
                else:
                    out_server.add(mem_id)
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return (in_server, out_server)


def update_member_status(in_server: Tuple[int], out_server: Tuple[int]) -> None:
    update_in_server = """update members set in_server = %s 
    where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        for mem_id in in_server:
            cur.execute(update_in_server, (True, mem_id))
        for mem_id in out_server:
            cur.execute(update_in_server, (False, mem_id))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def members_roles() -> Tuple[Set[int], Set[int]]:
    lookup = """ select id, in_server from members;"""
    conn = None
    in_server, out_server = set(), set()
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lookup)
        res = cur.fetchall()
        if res:
            for mem_id, location in res:
                if location:
                    in_server.add(mem_id)
                else:
                    out_server.add(mem_id)
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return in_server, out_server


def get_crew_vote(crew: Crew) -> Optional[Tuple[str, int, str]]:
    lookup = """
    select crews.name, votes.choice, members.nickname
from votes,
     crews,
     members
    where votes.member_id = members.id and crews.id = votes.crew_id and crews.id = %s;"""
    out = None
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lookup, (crew_id_from_crews(crew, cur),))
        res = cur.fetchall()
        if res:
            out = res[0]
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return out


def set_crew_vote(crew: Crew, option: int, member_id: int) -> None:
    setup = """
    insert into votes (crew_id, choice, member_id)
VALUES (%s, %s, %s)
on conflict (crew_id) do update set choice    = excluded.choice,
                          member_id = excluded.member_id;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(setup, (crew_id_from_crews(crew, cur), option, member_id))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def update_crew_tf(crew: Crew, triforce: int, group: int) -> None:
    setup = """
    update crews set triforce = %s, tf_group = %s where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(setup, triforce, group, (crew_id_from_crews(crew, cur)))
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def all_votes() -> List[str]:
    lookup = """select crews.name from crews
    left join votes on votes.crew_id = crews.id
        where votes.crew_id = crews.id and crews.disbanded = false;"""
    conn = None
    names = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(lookup)
        res = cur.fetchall()
        if res:
            for name in res:
                names.append(name[0])
        conn.commit()
        cur.close()

    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return names


def track_finished() -> Tuple[Tuple[int, str, int]]:
    finished = """ 
        select member_id, name, months
from (SELECT EXTRACT(month FROM age(current_timestamp, gained)) as months, member_id,role_id, roles.name, gained
      from current_member_roles,
           roles,
           members
      where roles.id = current_member_roles.role_id
        and roles.name in ('Track 1', 'Track 2', 'Full Move Locked', 'Move Locked Next Join')
        and members.id = current_member_roles.member_id)

         as b
where months > 0"""
    conn = None
    current = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(finished)
        current = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return tuple((int(c[0]), str(c[1]), int(c[2])) for c in current)


def track_finished_out() -> Tuple[Tuple[int, int]]:
    finished = """ 
        select member_id, months
from (SELECT EXTRACT(month FROM age(current_timestamp, gained)) as months, member_id,role_id, roles.name, gained
      from current_member_roles,
           roles,
           members
      where roles.id = current_member_roles.role_id
        and roles.name in ('Track 1', 'Track 2', 'Full Move Locked', 'Move Locked Next Join')
        and members.in_server = False
        and members.id = current_member_roles.member_id)

         as b
where months > 0"""
    conn = None
    current = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(finished)
        current = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return ((c[0], int(c[1])) for c in current)


def track_down_out(member_id: int):
    current_track = """select  roles.name, roles.id
      from current_member_roles,
           roles,
           members
      where roles.id = current_member_roles.role_id
        and roles.name in ('Track 1', 'Track 2', 'Full Move Locked', 'Move Locked Next Join')
        and members.id = current_member_roles.member_id
        and member_id = %s;"""
    role_id_from_name = """select id from roles where name = %s;"""
    add_mem_role = """INSERT into current_member_roles (member_id, role_id, gained)
     values(%s, %s, current_timestamp);"""
    delete_current = """DELETE FROM current_member_roles 
        where member_id = %s
        and role_id = %s
        returning gained;"""

    add_member_history = """INSERT into member_roles_history (member_id, role_id, gained, lost)
     values(%s, %s, %s, current_timestamp);"""
    conn = None
    try:

        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(current_track, (member_id,))
        ret = cur.fetchone()
        if not ret:
            return
        name, role_id = ret
        track_index = FULL_TRACK.index(name)
        if track_index > 0:
            if track_index == 3 and not recent_unflair(member_id):
                track_index -= 1
            new_track = FULL_TRACK[track_index - 1]
            cur.execute(role_id_from_name, (new_track,))
            new_id = cur.fetchone()[0]
            cur.execute(add_mem_role, (member_id, new_id))
        cur.execute(delete_current, (member_id, role_id,))
        gained = cur.fetchone()[0]
        cur.execute(add_member_history, (member_id, role_id, gained))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return


def recent_unflair(mem_id: int) -> bool:
    finished = """ 
        select *
from (SELECT EXTRACT(month FROM age(current_timestamp, leave_time)) as months, member_id, leave_time
      from unflairs
      where member_id = %s)

         as b
where months = 0"""
    conn = None
    recent = False
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(finished, (mem_id,))
        current = cur.fetchall()
        if current:
            recent = True
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return recent


def battles_since_sunday(crew: Crew) -> int:
    finished = """ 
select count(*)
from battle,
     crews
where finished > (select (current_date) - extract(dow from (current_date))::integer)
  and crews.id in (battle.crew_1, battle.crew_2)
  and crews.id = %s
;"""
    conn = None
    recent = 0
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(finished, (cr_id,))
        current = cur.fetchone()
        recent = current[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return recent


def extra_slot_used(crew: Crew) -> bool:
    finished = """ 
select extra_slot_date > (select current_date - extract(dow from current_date)::integer) from crews where id = %s
;"""
    conn = None
    recent = False
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(finished, (cr_id,))
        current = cur.fetchone()
        recent = current[0]
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return recent


def set_extra_used(crew: Crew):
    finished = """ 
update crews set extra_slot_date = current_date where id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cr_id = crew_id_from_crews(crew, cur)
        cur.execute(finished, (cr_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def add_bracket_predictions(member_id: int, match_list: Iterable['Match']):
    prediction = """ 
    insert into bracket_predictions (member_id, match_number, winner, loser) 
    VALUES(%s, %s, %s, %s) on conflict (member_id, match_number) 
    DO UPDATE set winner = excluded.winner, loser = excluded.loser;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        for match in match_list:
            if match.winner:
                cur.execute(prediction, (member_id, match.number, match.winner.db_id, match.loser.db_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def add_bracket_questions(member_id: int, answers: Iterable[int]):
    prediction = """ 
    insert into bracket_questions (member_id, question_number, answer) 
    VALUES(%s, %s, %s) on conflict (member_id,question_number) 
    DO UPDATE set answer = excluded.answer;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        for i, answer in enumerate(answers):
            cur.execute(prediction, (member_id, i, answer))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()


def get_bracket_questions(member_id: int):
    prediction = """ 
    select answer
    from bracket_questions where member_id = %s
    order by question_number;"""
    question_results = []
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(prediction, (member_id,))
        question_results = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return question_results


def get_bracket_predictions(member_id: int):
    prediction = """ 
    select name
    from bracket_predictions,crews where member_id = %s and crews.id = bracket_predictions.winner
    order by match_number;"""
    match_results = []
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(prediction, (member_id,))
        match_results = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return match_results


# def get_crew_ratios(crew: Crew):
#     prediction = """
#     select name
#     from bracket_predictions,crews where member_id = %s and crews.id = bracket_predictions.winner
#     order by match_number;"""
#     match_results = []
#     conn = None
#     try:
#         params = config()
#         conn = psycopg2.connect(**params)
#         cur = conn.cursor()
#         cur.execute(prediction, (member_id,))
#         match_results = cur.fetchall()
#         conn.commit()
#         cur.close()
#     except (Exception, psycopg2.DatabaseError) as error:
#         log_error_and_reraise(error)
#     finally:
#         if conn is not None:
#             conn.close()
#     return match_results


def get_match_predictions(member_id: int):
    prediction = """ 
    select name
    from bracket_predictions,crews where member_id = %s and crews.id = bracket_predictions.winner
    order by match_number;"""
    match_results = []
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(prediction, (member_id,))
        match_results = cur.fetchall()
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return match_results


def get_all_predictions():
    prediction = """ 
    select nickname, match_number, winner
    from bracket_predictions,
         members
    where members.id = bracket_predictions.member_id;"""
    output = defaultdict(lambda: defaultdict(int))
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(prediction)
        match_results = cur.fetchall()
        for nickname, match_number, winner in match_results:
            output[nickname][match_number] = winner
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return output


def battles_by_week():
    everything = """select cr1.name, cr2.name, finished
from (select winner, case when winner = crew_1 then crew_2 else crew_1 end as loser, finished
      from (
               select crew_1, crew_2, winner, finished
               from battle
               where league_id = 16 order by id) scl_battles) bttles,
     crews as cr1,
     crews as cr2
where cr1.id = bttles.winner
  and cr2.id = bttles.loser;"""
    week_split = """select * from generate_series('2021-05-01 19:25:54.603384'::timestamp, 
                    '2021-11-21 02:12:47.840990', '1 week')"""
    conn = None
    matches = []
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(everything)
        results = cur.fetchall()
        cur.execute(week_split)
        weeks = cur.fetchall()
        current_week = 1
        current_split = []
        for match in results:

            if current_week >= len(weeks):
                print('Help!')
                return
            if match[2] > weeks[current_week][0]:
                matches.append(current_split)
                current_split = [match]
                current_week += 1
            else:
                current_split.append(match)
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        log_error_and_reraise(error)
    finally:
        if conn is not None:
            conn.close()
    return matches


"""select '<@!' || member_id || '>', name, gained
from (SELECT EXTRACT(month FROM age(current_timestamp, gained)) as months, member_id, roles.name, gained
      from current_member_roles,
           roles,
           members
      where roles.id = current_member_roles.role_id
        and roles.name in ('Track 1', 'Track 2', 'Full Move Locked', 'Move Locked Next Join')
        and members.in_server = True
        and members.id = current_member_roles.member_id)

         as b
where months > 0
"""
