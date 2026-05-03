"""
Tests for src/db_helpers.py using MockConnection and MockCursor.

All tests patch both `psycopg2.connect` (so no real DB connection is made) and
`src.db_config.config` (so no database.ini file is required).  Each test then
pre-loads the MockCursor with the exact rows that the function under test would
normally receive from PostgreSQL, allowing us to verify both the SQL that was
sent and the value returned to the caller.
"""
import datetime
import unittest
from unittest.mock import patch, MagicMock

from tests.mocks import (
    MockConnection,
    MockMember,
    MockRole,
    MockGuild,
    HK,
    FSGood,
)

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

# Matches the shape returned by db_config.config() when reading database.ini
MOCK_DB_PARAMS = {
    'user': 'test_user',
    'password': 'test_password',
    'host': 'localhost',
    'port': '5432',
    'database': 'test_db',
    'sslmode': 'disable',
}


def _make_conn(results=None):
    """
    Return a (conn, cursor) pair whose cursor is pre-loaded with *results*.

    *results* must be a list of values, each consumed by one fetchone /
    fetchall / fetchmany call, in order.
    """
    conn = MockConnection()
    if results:
        conn.mock_cursor.set_results(results)
    return conn, conn.mock_cursor


def _db_patches(conn):
    """
    Context-manager stack: patches config() → MOCK_DB_PARAMS and
    psycopg2.connect() → *conn*.
    """
    p_config = patch('src.db_config.config', return_value=MOCK_DB_PARAMS)
    p_connect = patch('psycopg2.connect', return_value=conn)
    return p_config, p_connect


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class DbHelpersTestBase(unittest.TestCase):
    """Provides self.conn and active patches for each test."""

    def setUp(self):
        self.conn = MockConnection()
        self.cursor = self.conn.mock_cursor

        self._p_config = patch('src.db_config.config', return_value=MOCK_DB_PARAMS)
        self._p_connect = patch('psycopg2.connect', return_value=self.conn)

        self.mock_config = self._p_config.start()
        self.mock_connect = self._p_connect.start()

    def tearDown(self):
        self._p_config.stop()
        self._p_connect.stop()

    # convenience -----------------------------------------------------------

    def set_results(self, *rows):
        """Pre-load cursor with one result per positional arg."""
        self.cursor.set_results(list(rows))

    def executed_queries(self):
        """Return the list of (sql, params) tuples the cursor recorded."""
        return self.cursor.queries


# ===========================================================================
# Tests for utility / id-lookup helpers
# ===========================================================================

class TestCrewIdFromName(DbHelpersTestBase):

    def test_returns_id_when_crew_found(self):
        """crew_id_from_name should return the integer id from the first column."""
        from src.db_helpers import crew_id_from_name
        self.set_results((42,))
        result = crew_id_from_name('Holy Knights', self.cursor)
        self.assertEqual(result, 42)

    def test_returns_none_when_crew_not_found(self):
        """crew_id_from_name should return None if the crew doesn't exist."""
        from src.db_helpers import crew_id_from_name
        # fetchone returns None by default on an empty MockCursor
        result = crew_id_from_name('Unknown Crew', self.cursor)
        self.assertIsNone(result)

    def test_executes_correct_query(self):
        """crew_id_from_name must query the crews table by name."""
        from src.db_helpers import crew_id_from_name
        crew_id_from_name('Holy Knights', self.cursor)
        queries = self.executed_queries()
        self.assertEqual(len(queries), 1)
        sql, params = queries[0]
        self.assertIn('crews', sql)
        self.assertIn('name', sql)
        self.assertEqual(params, ('Holy Knights',))


class TestCrewIdFromRoleId(DbHelpersTestBase):

    def test_returns_id_when_found(self):
        from src.db_helpers import crew_id_from_role_id
        self.set_results((7,))
        result = crew_id_from_role_id(999, self.cursor)
        self.assertEqual(result, 7)

    def test_returns_none_when_not_found(self):
        from src.db_helpers import crew_id_from_role_id
        # fetchone → None
        result = crew_id_from_role_id(999, self.cursor)
        self.assertIsNone(result)


class TestCharIdFromName(DbHelpersTestBase):

    def test_returns_character_id(self):
        from src.db_helpers import char_id_from_name
        self.set_results((15,))
        result = char_id_from_name('Mario', self.cursor)
        self.assertEqual(result, 15)

    def test_queries_fighters_table(self):
        from src.db_helpers import char_id_from_name
        self.set_results((1,))
        char_id_from_name('Link', self.cursor)
        sql, params = self.cursor.queries[0]
        self.assertIn('fighters', sql)
        self.assertEqual(params, ('Link',))


# ===========================================================================
# Tests for member-role helpers
# ===========================================================================

class TestFindMemberRoles(DbHelpersTestBase):

    def _make_member(self, guild_id=430361913369690113, member_id=111):
        member = MockMember(id=member_id)
        member.guild = MockGuild(id=guild_id)
        member.guild.id = guild_id
        return member

    def test_returns_list_of_role_ids(self):
        from src.db_helpers import find_member_roles
        # fetchall will return a list of rows; each row is (role_id,)
        self.set_results([(1001,), (1002,), (1003,)])
        member = self._make_member()
        result = find_member_roles(member)
        self.assertEqual(result, [1001, 1002, 1003])

    def test_returns_empty_list_when_no_roles(self):
        from src.db_helpers import find_member_roles
        # fetchall with no pre-loaded results → []
        member = self._make_member()
        result = find_member_roles(member)
        self.assertEqual(result, [])

    def test_uses_member_id_and_guild_id(self):
        from src.db_helpers import find_member_roles
        self.set_results([])
        member = self._make_member(guild_id=9999, member_id=8888)
        find_member_roles(member)
        sql, params = self.cursor.queries[0]
        self.assertIn(str(member.id), str(params))
        self.assertIn(str(member.guild.id), str(params))


class TestAllMemberRoles(DbHelpersTestBase):

    def test_returns_role_ids(self):
        from src.db_helpers import all_member_roles
        self.set_results([(5,), (6,)])
        result = all_member_roles(42)
        self.assertEqual(result, [5, 6])

    def test_passes_member_id_as_string(self):
        from src.db_helpers import all_member_roles
        self.set_results([])
        all_member_roles(999)
        sql, params = self.cursor.queries[0]
        self.assertEqual(params, (str(999),))


# ===========================================================================
# Tests for crew management helpers
# ===========================================================================

class TestIdFromCrew(DbHelpersTestBase):

    def test_returns_crew_id_by_role_id(self):
        """id_from_crew prefers role_id lookup; returns it if found."""
        from src.db_helpers import id_from_crew
        # First fetchone: crew_id_from_role_id → (10,)
        self.set_results((10,))
        result = id_from_crew(HK)
        self.assertEqual(result, 10)

    def test_falls_back_to_name_when_role_id_missing(self):
        """If role_id lookup returns None, id_from_crew should try the name."""
        from src.db_helpers import id_from_crew
        # First fetchone: role_id lookup → None
        # Second fetchone: name lookup → (25,)
        self.set_results(None, (25,))
        result = id_from_crew(HK)
        self.assertEqual(result, 25)


class TestNewCrew(DbHelpersTestBase):

    def test_inserts_crew_row(self):
        """new_crew should execute an INSERT into crews."""
        from src.db_helpers import new_crew
        new_crew(HK)
        sql, params = self.cursor.queries[0]
        self.assertIn('INSERT', sql.upper())
        self.assertIn('crews', sql)

    def test_passes_crew_attributes(self):
        from src.db_helpers import new_crew
        new_crew(HK)
        _, params = self.cursor.queries[0]
        self.assertIn(HK.role_id, params)
        self.assertIn(HK.name, params)
        self.assertIn(HK.abbr, params)


# ===========================================================================
# Tests for add_thanks
# ===========================================================================

class TestAddThanks(DbHelpersTestBase):

    def _make_member(self, user_id=111222333444555666, display_name='TestUser'):
        member = MockMember(id=user_id, display_name=display_name)
        return member

    def test_returns_formatted_string(self):
        """add_thanks should return a string with the username and count."""
        from src.db_helpers import add_thanks
        member = self._make_member(display_name='Bob')
        # Only the two SELECTs call fetchone; the INSERT and UPDATE do not.
        # MockCursor pops from fetch_results only when fetchone() is invoked,
        # so we only need to load the two SELECT results.
        self.set_results(
            (3, 'Bob'),   # SELECT count, username …
            (42,),        # SELECT SUM(count) …
        )
        result = add_thanks(member)
        self.assertIn('Bob', result)
        self.assertIn('3', result)
        self.assertIn('42', result)

    def test_executes_four_queries(self):
        """add_thanks should execute exactly four SQL statements."""
        from src.db_helpers import add_thanks
        member = self._make_member()
        self.set_results((1, 'TestUser'), (5,))
        add_thanks(member)
        self.assertEqual(len(self.cursor.queries), 4)

    def test_passes_user_id_and_display_name(self):
        from src.db_helpers import add_thanks
        member = self._make_member(user_id=123456789, display_name='Alice')
        self.set_results((1, 'Alice'), (1,))
        add_thanks(member)
        # First query: INSERT with (0, user_id_str, display_name)
        _, params = self.cursor.queries[0]
        self.assertIn(str(member.id), params)
        self.assertIn(member.display_name, params)


# ===========================================================================
# Tests for simple read helpers (no complex setup needed)
# ===========================================================================

class TestPowerRankings(DbHelpersTestBase):

    def test_returns_list_of_tuples(self):
        from src.db_helpers import power_rankings
        rows = [('Holy Knights', 5, 10, 1), ('FSGood', 3, 8, 2)]
        self.set_results(rows)
        result = power_rankings()
        self.assertEqual(result, rows)

    def test_returns_empty_on_no_data(self):
        from src.db_helpers import power_rankings
        result = power_rankings()
        self.assertEqual(result, [])


class TestWisdomRankings(DbHelpersTestBase):

    def test_returns_ranked_list(self):
        from src.db_helpers import wisdom_rankings
        rows = [(1, 'Holy Knights', 1500), (2, 'FSGood', 1400)]
        self.set_results(rows)
        result = wisdom_rankings()
        self.assertEqual(result, rows)


class TestCurrentLeagueName(DbHelpersTestBase):

    def test_returns_name_date_and_reset(self):
        from src.db_helpers import current_league_name
        today = datetime.date.today()
        self.set_results(('Spring League', today, False))
        name, start, reset = current_league_name()
        self.assertEqual(name, 'Spring League')
        self.assertEqual(start, today)
        self.assertFalse(reset)

    def test_returns_defaults_when_no_row(self):
        """If no row exists, current_league_name should return empty defaults."""
        from src.db_helpers import current_league_name
        # fetchone returns None (default MockCursor behaviour)
        name, start, reset = current_league_name()
        self.assertEqual(name, '')
        self.assertIsNone(start)
        self.assertTrue(reset)


class TestAllBattleIds(DbHelpersTestBase):

    def test_returns_fetched_ids(self):
        from src.db_helpers import all_battle_ids
        rows = [(1,), (2,), (3,)]
        self.set_results(rows)
        result = all_battle_ids()
        self.assertEqual(result, rows)

    def test_returns_empty_when_no_battles(self):
        from src.db_helpers import all_battle_ids
        result = all_battle_ids()
        self.assertEqual(result, [])


class TestBattleInfo(DbHelpersTestBase):

    def test_returns_crew_names_and_metadata(self):
        from src.db_helpers import battle_info
        # battle_info calls finished.date(), so the mock row must contain a
        # datetime.datetime, not a datetime.date.
        finished_dt = datetime.datetime(2024, 6, 15, 12, 0, 0)
        self.set_results(('Holy Knights', 'FSGood', finished_dt, 'http://link'))
        result = battle_info(1)
        self.assertEqual(result[0], 'Holy Knights')
        self.assertEqual(result[1], 'FSGood')
        self.assertEqual(result[3], 'http://link')

    def test_passes_battle_id(self):
        from src.db_helpers import battle_info
        finished_dt = datetime.datetime(2024, 6, 15, 12, 0, 0)
        self.set_results(('A', 'B', finished_dt, ''))
        battle_info(99)
        _, params = self.cursor.queries[0]
        self.assertIn(99, params)


# ===========================================================================
# Tests for destiny / utility write helpers
# ===========================================================================

class TestDestinyPair(DbHelpersTestBase):

    def test_executes_two_updates(self):
        from src.db_helpers import destiny_pair
        destiny_pair(1, 2)
        self.assertEqual(len(self.cursor.queries), 2)

    def test_updates_both_crew_ids(self):
        from src.db_helpers import destiny_pair
        destiny_pair(10, 20)
        first_sql, first_params = self.cursor.queries[0]
        second_sql, second_params = self.cursor.queries[1]
        self.assertIn('UPDATE', first_sql.upper())
        self.assertIn(10, first_params + second_params)
        self.assertIn(20, first_params + second_params)


class TestDestinyOpt(DbHelpersTestBase):

    def test_executes_one_update(self):
        from src.db_helpers import destiny_opt
        destiny_opt(5, True)
        self.assertEqual(len(self.cursor.queries), 1)

    def test_passes_opt_out_flag(self):
        from src.db_helpers import destiny_opt
        destiny_opt(7, False)
        _, params = self.cursor.queries[0]
        self.assertIn(False, params)
        self.assertIn(7, params)


class TestAddCharacter(DbHelpersTestBase):

    def test_inserts_character(self):
        from src.db_helpers import add_character
        add_character('Pikachu')
        sql, params = self.cursor.queries[0]
        self.assertIn('INSERT', sql.upper())
        self.assertIn('Pikachu', params)


class TestRemoveMemberRole(DbHelpersTestBase):

    def test_deletes_role_and_records_history(self):
        """
        remove_member_role should DELETE current role then INSERT history if a
        gained timestamp was returned.
        """
        from src.db_helpers import remove_member_role
        # DELETE ... RETURNING gained → (datetime,)
        gained_ts = datetime.datetime(2024, 1, 1)
        self.set_results((gained_ts,))
        remove_member_role(111, 222)
        queries = self.cursor.queries
        # DELETE + INSERT history
        self.assertEqual(len(queries), 2)
        delete_sql, _ = queries[0]
        insert_sql, _ = queries[1]
        self.assertIn('DELETE', delete_sql.upper())
        self.assertIn('INSERT', insert_sql.upper())

    def test_no_history_when_role_not_found(self):
        """If DELETE returns no row, history insert should be skipped."""
        from src.db_helpers import remove_member_role
        # fetchone → None (role was not present)
        remove_member_role(111, 222)
        queries = self.cursor.queries
        # Only the DELETE should have run
        self.assertEqual(len(queries), 1)


class TestAddMemberRole(DbHelpersTestBase):

    def test_inserts_member_role(self):
        from src.db_helpers import add_member_role
        add_member_role(333, 444)
        sql, params = self.cursor.queries[0]
        self.assertIn('INSERT', sql.upper())
        self.assertIn('current_member_roles', sql)
        self.assertIn(333, params)
        self.assertIn(444, params)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == '__main__':
    unittest.main()
