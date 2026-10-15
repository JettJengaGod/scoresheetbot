"""Tests for syncing the database's record of the main server's members with Discord."""
import types
import unittest
import unittest.mock

import discord

from src import member_sync
from src.constants import OVERFLOW_ROLE
from tests.harness import make_cog

GUILD = 1


def role(role_id, name):
    return types.SimpleNamespace(id=role_id, name=name, is_default=lambda: role_id == GUILD)


EVERYONE, LEADER, OLD, HK, FSG, OVERFLOW = (role(GUILD, '@everyone'), role(10, 'Leader'), role(11, 'Old'),
                                            role(20, 'Holy Knights'), role(21, 'FSGood'),
                                            role(30, OVERFLOW_ROLE))


def member(member_id, *roles, name=None):
    name = name or f'member{member_id}'
    return types.SimpleNamespace(id=member_id, name=name, display_name=name, roles=[EVERYONE, *roles])


def guild(*roles, member_count=None):
    return types.SimpleNamespace(id=GUILD, roles=[EVERYONE, *roles], member_count=member_count)


class PlanTest(unittest.TestCase):
    def plan(self, members, db_members=None, db_roles=(), db_crews=None, crew_ids=None, server=None):
        server = server or guild(LEADER, HK, FSG, OVERFLOW)
        return member_sync.plan(server, {m.id: m for m in members}, ['Holy Knights', 'FSGood'],
                                db_members or {}, set(db_roles), db_crews or {}, crew_ids or {20: 200, 21: 210})

    def test_new_members_are_added_and_marked_in_the_server(self):
        sync = self.plan([member(1, LEADER)])
        self.assertEqual([(1, 'member1', 'member1')], sync.new_members)
        self.assertEqual([1], sync.joined)
        self.assertEqual([(1, 10)], sync.gained)

    def test_roles_are_made_to_match_and_deleted_roles_retired(self):
        db_members = {1: ('member1', True), 2: ('member2', True)}
        # Member 1 lost Leader; Old was deleted from the server; member 2 left, and keeps Leader.
        db_roles = {(1, 10), (1, 11), (2, 10), (2, 11)}
        sync = self.plan([member(1), member(2, LEADER)][:1], db_members, db_roles)
        self.assertEqual([(1, 10), (1, 11), (2, 11)], sync.lost)
        self.assertEqual(2, sync.retired)
        self.assertEqual([2], sync.left)
        self.assertEqual([], sync.gained)

    def test_members_already_marked_are_left_alone(self):
        db_members = {1: ('member1', True), 2: ('member2', False), 3: ('member3', None)}
        sync = self.plan([member(1), member(3)], db_members)
        self.assertEqual(([], [], [3]), (sync.left, sync.renamed, sync.joined))

    def test_nicknames_are_updated(self):
        sync = self.plan([member(1, name='new')], {1: ('old', True)})
        self.assertEqual([(1, 'new')], sync.renamed)

    def test_crews_are_made_to_match_the_crew_roles(self):
        members = [member(1, HK), member(2), member(3, FSG), member(4, OVERFLOW), member(5, HK)]
        db_crews = {1: 200, 2: 210, 3: 200, 4: 999}
        sync = self.plan(members, {m.id: (m.name, True) for m in members}, db_crews=db_crews)
        # Member 1 is right, 2 was unflaired, 3 moved, 4 is in the overflow server, 5 was flaired.
        self.assertEqual([(2, None), (3, 210), (5, 200)], sync.crews)

    def test_a_crew_role_with_no_crew_in_the_database_is_left_alone(self):
        sync = self.plan([member(1, HK)], {1: ('member1', True)}, db_crews={1: 210}, crew_ids={21: 210})
        self.assertEqual([], sync.crews)
        self.assertEqual({'Holy Knights'}, sync.unknown_crews)

    def test_the_summary_says_how_many_could_not_be_found(self):
        sync = self.plan([member(1)], server=guild(member_count=3))
        self.assertIn('Found 1 of the 3 members', sync.summary())
        self.assertIn('2 could not be found', sync.summary())


class FindMembersTest(unittest.IsolatedAsyncioTestCase):
    async def test_full_searches_are_narrowed(self):
        names = [f'a{i:04}' for i in range(1500)] + ['bob']
        searched = []

        async def search(_, query):
            searched.append(query)
            matches = [types.SimpleNamespace(id=n) for n in names if n.startswith(query)]
            return matches[:member_sync.SEARCH_LIMIT]

        with unittest.mock.patch('src.member_sync.search_members', side_effect=search):
            found = await member_sync.all_members(object())
        self.assertCountEqual(names, found)
        self.assertIn('a0', searched)
        self.assertNotIn('b0', searched)

    async def test_members_by_id_asks_in_chunks(self):
        server = unittest.mock.MagicMock()
        server.query_members = unittest.mock.AsyncMock(
            side_effect=lambda user_ids, **_: [types.SimpleNamespace(id=i) for i in user_ids if i % 2])
        found = await member_sync.members_by_id(server, range(250))
        self.assertEqual(3, server.query_members.await_count)
        self.assertEqual(125, len(found))

    async def test_members_the_search_missed_are_looked_up_by_id_before_being_marked_as_left(self):
        cog = make_cog()
        cog.bot.intents = discord.Intents.default()
        cog.cache.scs = guild(member_count=2)
        cog.cache.crews = []
        state = ({1: ('member1', True), 2: ('member2', True), 3: ('member3', False)}, set(), {}, {})
        with unittest.mock.patch('src.member_sync.member_sync_state', return_value=state), \
                unittest.mock.patch('src.member_sync.all_members',
                                    unittest.mock.AsyncMock(return_value={1: member(1)})), \
                unittest.mock.patch('src.member_sync.members_by_id',
                                    unittest.mock.AsyncMock(return_value={})) as by_id, \
                unittest.mock.patch('src.member_sync.apply_member_sync') as apply:
            sync = await member_sync.sync_members(cog, apply=False)
            by_id.assert_awaited_once_with(cog.cache.scs, [2])
            apply.assert_not_called()
            self.assertEqual([2], sync.left)
            await member_sync.sync_members(cog, apply=True)
            apply.assert_called_once()


if __name__ == '__main__':
    unittest.main()
