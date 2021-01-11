from typing import List, Tuple
import traceback
import psycopg2
from db_config import config
import sys
import os
from battle import Battle, InfoMatch, TimerMatch
from crew import Crew
import discord
import datetime


def logfile():
    logfilename = 'logs.log'
    if os.path.exists(logfilename):
        append_write = 'a'  # append if already exists
    else:
        append_write = 'w'  # make a new file if not
    logfile = open(logfilename, append_write)
    return logfile


def add_thanks(user: discord.Member) -> str:
    add = """INSERT into thank (count, userid, username)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    update = """UPDATE public.thank set count = count +1
    where userid = %s;"""
    find = """SELECT count, username from public.thank where userid = %s;"""
    total = """SELECT SUM(count) from public.thank;"""
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()

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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return discord.Embed(title='Top thankers!', color=discord.Color.gold(), description='\n'.join(desc))


def add_member_and_roles(member: discord.Member) -> None:
    add_member = """INSERT into members (id, nickname, discord_name)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    add_role = """INSERT into roles (id, name, guild_id)
     values(%s, %s, %s) ON CONFLICT DO NOTHING;"""
    add_member_role = """INSERT into current_member_roles (member_id, role_id, gained)
     values(%s, %s, current_timestamp);"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_member, (member.id, member.display_name, member.name))
        for role in member.roles:
            cur.execute(add_role, (role.id, role.name, role.guild.id))
            cur.execute(add_member_role, (member.id, role.id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
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
    add_member_role = """INSERT into current_member_roles (member_id, role_id, gained)
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
            cur.execute(add_member_role, (member.id, role.id))
        for role_id in lost:
            cur.execute(delete_current, (member.id, role_id,))
            gained = cur.fetchone()[0]
            cur.execute(add_member_history, (member.id, role_id, gained))

        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return


def add_member_and_crew(member: discord.Member, crew: Crew, role: discord.Role) -> None:
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

        cur.execute(add_crew, (role.id, crew.name, crew.abbr, crew.overflow, crew.name))
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return everything


def crew_id_from_name(name: str, cursor) -> int:
    find_crew = """SELECT id from crews where name = %s;"""
    cursor.execute(find_crew, (name,))
    crew_id = cursor.fetchone()[0]
    return crew_id


def crew_id_from_role_id(role_id: int, cursor) -> int:
    find_crew = """SELECT id from crews where discord_id = %s;"""
    cursor.execute(find_crew, (role_id,))
    crew_id = cursor.fetchone()[0]
    return crew_id


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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return


def char_id_from_name(name: str, cursor) -> int:
    find_crew = """SELECT id from fighters where name = %s;"""
    cursor.execute(find_crew, (name,))
    char_id = cursor.fetchone()[0]
    return char_id


def add_finished_battle(battle: Battle, link: str, league: int) -> None:
    add_battle = """INSERT into battle (crew_1, crew_2, final_score, link, winner, finished, league_id)
     values(%s, %s, %s, %s, %s, current_timestamp, %s)  RETURNING id;"""

    add_match = """INSERT into match (p1, p2, p1_taken, p2_taken, winner, battle_id, p1_char_id, p2_char_id, match_order)
     values(%s, %s, %s, %s, %s, %s, %s, %s, %s);"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(add_battle, (
            crew_id_from_name(battle.team1.name, cur),
            crew_id_from_name(battle.team2.name, cur),
            battle.winner().stocks,
            link,
            crew_id_from_name(battle.winner().name, cur),
            league,
        ))
        battle_id = cur.fetchone()[0]
        for order, match in enumerate(battle.matches):
            if isinstance(match, TimerMatch) or isinstance(match, InfoMatch):
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
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return


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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return current == db_crew


def all_crews() -> List[List]:
    everything = """SELECT discord_id, tag, name, rank, overflow FROM crews;"""
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return crews


def update_crew(crew: Crew) -> None:
    current = """SELECT id, discord_id, tag, name, rank, overflow FROM crews
    where discord_id = %s
    ;"""
    history = """INSERT INTO crews_history (crew_id, old_discord_id, old_tag, old_name, old_rank, old_overflow, 
    new_discord_id, new_tag, new_name, new_rank, new_overflow, update_time) 
    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, current_timestamp)"""
    update = """UPDATE crews 
    SET tag = %s, name = %s, rank = %s,overflow = %s
    WHERE discord_id = %s;"""
    conn = None
    try:
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(current, (crew.role_id,))
        old = cur.fetchone()
        cur.execute(history,
                    (old[0], old[1], old[2], old[3], old[4], old[5], crew.role_id, crew.abbr, crew.name, None,
                     crew.overflow))
        cur.execute(update, (crew.abbr, crew.name, None, crew.overflow, crew.role_id))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()


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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()


def update_member_crew(member: discord.Member, new_crew: Crew) -> None:
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
        cur.execute(delete_current, (member.id,))
        current = cur.fetchone()
        if current:
            cur.execute(old_crew, (current[0], current[1], current[2],))
        if new_crew:
            new_id = crew_id_from_role_id(new_crew.role_id, cur)
            cur.execute(add_member_crew, (member.id, new_id,))
        conn.commit()
        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()


def cooldown_finished() -> List[int]:
    finished = """ 
        select member_id from 
            (SELECT EXTRACT(epoch FROM age(current_timestamp, gained))/3600 as hours,member_id, roles.name 
                from current_member_roles,roles 
                where roles.id = current_member_roles.role_id and roles.id = 786492456027029515) 
                as b where hours > 24;"""
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
    return [(c[0], c[1]) for c in current]


def remove_expired_cooldown(user_id: int):
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
        lf = logfile()
        traceback.print_exception(type(error), error, error.__traceback__, file=lf)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        lf.close()
    finally:
        if conn is not None:
            conn.close()
