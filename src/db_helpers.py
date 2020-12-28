import psycopg2
from db_config import config
import discord


def add_thanks(user: discord.Member) -> str:
    """ insert a new vendor into the vendors table """
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
        print(error)
    finally:
        if conn is not None:
            conn.close()
    return ret


def thank_board(user: discord.Member) -> discord.Embed:
    """ insert a new vendor into the vendors table """
    board = """select count, userid, username, 
        RANK() OVER (ORDER BY count DESC) thank_rank from thank;"""
    solo = f"SELECT * from (SELECT *, RANK () OVER (ORDER BY count DESC) " \
           f"thank_rank FROM thank) total where userid = '{user.id}';";
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
        print(error)
    finally:
        if conn is not None:
            conn.close()
    return discord.Embed(title='Top thankers!', color=discord.Color.gold(), description='\n'.join(desc))
