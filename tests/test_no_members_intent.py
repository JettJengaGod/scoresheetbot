"""Tests for running without the server members intent: fetching members and the crew data from the database."""
import unittest
import unittest.mock

import discord

from src import no_members_intent
from src.constants import ADVISOR, CREW_STAFF, LEADER, MUTED
from src.crew import Crew
from tests import mocks
from tests.harness import make_cog

ABSENT = 404


class NoMembersIntentTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.cog.bot.intents = discord.Intents.default()
        self.cog._member_changed = unittest.mock.AsyncMock()
        self.scs, self.overflow = self.cog.cache.scs, self.cog.cache.overflow_server
        # Each server's member cache, and the members Discord has, by id.
        self.cached = {}
        self.discord = {}
        for number, guild in enumerate((self.scs, self.overflow)):
            guild.id = 100 + number
            self.cached[guild.id] = {}
            self.discord[guild.id] = {}
            guild.get_member = self.cached[guild.id].get
            guild.fetch_member = unittest.mock.AsyncMock(side_effect=self.fetch(guild))
            guild._add_member = self.add(guild)

    def fetch(self, guild):
        def fetch_member(member_id):
            if member_id not in self.discord[guild.id]:
                if member_id == ABSENT or guild is self.overflow:
                    raise discord.NotFound(unittest.mock.MagicMock(status=404), 'Unknown Member')
                self.discord[guild.id][member_id] = mocks.MockMember(id=member_id, display_name=str(member_id))
            return self.discord[guild.id][member_id]
        return fetch_member

    def add(self, guild):
        def add_member(member):
            self.cached[guild.id][member.id] = member
        return add_member

    def on_discord(self, guild, member_id, roles=(), name=None):
        member = mocks.MockMember(id=member_id, display_name=name or str(member_id), roles=list(roles))
        self.discord[guild.id][member_id] = member
        return member

    async def test_author_and_members_in_options_are_cached_in_every_server(self):
        for member_id in (1, 2, 3, 444444444444444444):
            self.on_discord(self.overflow, member_id)
        ctx = unittest.mock.MagicMock(author=mocks.MockMember(id=1), guild=self.scs)
        ctx.interaction.namespace = [('user', mocks.MockMember(id=2)), ('members', '<@3> <@!444444444444444444>'),
                                     ('team', 'Red'), ('size', 5)]
        await no_members_intent.cache_command_members(self.cog, ctx)
        for guild in (self.scs, self.overflow):
            self.assertCountEqual([1, 2, 3, 444444444444444444], self.cached[guild.id])

    async def test_someone_not_in_the_server_is_none(self):
        self.assertIsNone(await self.cog._fresh_member(self.scs, ABSENT))
        self.assertNotIn(ABSENT, self.cached[self.scs.id])
        self.assertEqual(7, (await self.cog._fresh_member(self.scs, 7)).id)
        self.assertIn(7, self.cached[self.scs.id])

    async def test_someone_gone_from_the_main_server_is_marked_as_left_in_production(self):
        with unittest.mock.patch('src.no_members_intent.update_member_status') as status, \
                unittest.mock.patch.dict('os.environ', {'VERSION': 'PROD'}):
            await no_members_intent.fetch_member(self.cog, self.overflow, ABSENT)
            status.assert_not_called()
            await no_members_intent.fetch_member(self.cog, self.scs, ABSENT)
            status.assert_called_once_with((), (ABSENT,))
        with unittest.mock.patch('src.no_members_intent.update_member_status') as status:
            await no_members_intent.fetch_member(self.cog, self.scs, ABSENT)
            status.assert_not_called()

    async def test_changes_are_recorded_like_a_member_update(self):
        role = mocks.MockRole(name='Some role')
        first = self.on_discord(self.scs, 7)
        await no_members_intent.fetch_member(self.cog, self.scs, 7)
        self.cog._member_changed.assert_awaited_once_with(None, first)

        self.cog._member_changed.reset_mock()
        self.on_discord(self.scs, 7)
        await no_members_intent.fetch_member(self.cog, self.scs, 7)
        self.cog._member_changed.assert_not_awaited()

        promoted = self.on_discord(self.scs, 7, roles=[role])
        await no_members_intent.fetch_member(self.cog, self.scs, 7)
        self.cog._member_changed.assert_awaited_once_with(first, promoted)

        self.cog._member_changed.reset_mock()
        renamed = self.on_discord(self.scs, 7, roles=[role], name='New name')
        await no_members_intent.fetch_member(self.cog, self.scs, 7)
        self.cog._member_changed.assert_awaited_once_with(promoted, renamed)

    async def test_a_failure_to_record_changes_does_not_stop_the_command(self):
        self.cog._member_changed.side_effect = RuntimeError('database down')
        with self.assertLogs(level='ERROR'):
            self.assertEqual(7, (await no_members_intent.fetch_member(self.cog, self.scs, 7)).id)

    async def test_crew_members_are_the_database_members_still_on_the_crew(self):
        muted = mocks.MockRole(name=MUTED)
        self.on_discord(self.scs, 1)
        self.on_discord(self.scs, 2, roles=[muted])
        self.on_discord(self.scs, 3)
        on_crew = {1: 'Holy Knights', 2: 'Holy Knights', 3: 'Other Crew'}
        cr = Crew(name='Holy Knights', abbr='HK')
        with unittest.mock.patch('src.no_members_intent.db_crew_members', return_value=[1, 2, 3, ABSENT]), \
                unittest.mock.patch('src.no_members_intent.crew', side_effect=lambda m, _: on_crew[m.id]):
            self.assertEqual([1, 2], [m.id for m in await no_members_intent.crew_members(self.cog, cr)])
            self.assertEqual([2], [m.id for m in await no_members_intent.muted_crew_members(self.cog, cr)])
        self.assertEqual({}, self.cached[self.overflow.id])

    async def test_an_overflow_crew_also_fetches_its_members_in_the_overflow_server(self):
        self.on_discord(self.scs, 1)
        self.on_discord(self.overflow, 1)
        cr = Crew(name='Holy Knights', abbr='HK', overflow=True)

        def crew(member, _):
            # The overflow crew is read off the member's roles in the overflow server, so it must be cached.
            return 'Holy Knights' if member.id in self.cached[self.overflow.id] else None

        with unittest.mock.patch('src.no_members_intent.db_crew_members', return_value=[1]), \
                unittest.mock.patch('src.no_members_intent.crew', side_effect=crew):
            self.assertEqual([1], [m.id for m in await no_members_intent.crew_members(self.cog, cr)])

    async def test_the_cog_uses_the_member_list_with_the_intent_and_the_database_without(self):
        cr = Crew(name='Holy Knights', abbr='HK')
        with unittest.mock.patch('src.scoreSheetBot.crew_members', return_value=['listed']), \
                unittest.mock.patch('src.scoreSheetBot.overlap_members', return_value=['muted']), \
                unittest.mock.patch('src.no_members_intent.crew_members',
                                    unittest.mock.AsyncMock(return_value=['fetched'])), \
                unittest.mock.patch('src.no_members_intent.muted_crew_members',
                                    unittest.mock.AsyncMock(return_value=['fetched muted'])):
            self.assertEqual(['fetched'], await self.cog._crew_members(cr))
            self.assertEqual(['fetched muted'], await self.cog._muted_crew_members(cr))
            self.cog.bot.intents = discord.Intents.all()
            self.assertEqual(['listed'], await self.cog._crew_members(cr))
            self.assertEqual(['muted'], await self.cog._muted_crew_members(cr))

    async def test_with_the_intent_the_cache_is_used(self):
        self.cog.bot.intents = discord.Intents.all()
        self.cached[self.scs.id][7] = 'cached'
        self.assertEqual('cached', await self.cog._fresh_member(self.scs, 7))
        self.scs.fetch_member.assert_not_awaited()


class MemberChangedTest(unittest.IsolatedAsyncioTestCase):
    """Recording a member's changes in the database, for a member update or a fetch without the intent."""

    def setUp(self):
        self.cog = make_cog()
        self.cog.cache.categories = []
        self.member = mocks.MockMember(id=7, display_name='Seven')

    async def record(self, before):
        with unittest.mock.patch.multiple('src.scoreSheetBot', record_nicknames=unittest.mock.DEFAULT,
                                          update_member_roles=unittest.mock.DEFAULT,
                                          crew=unittest.mock.MagicMock(return_value=None),
                                          crew_correct=unittest.mock.MagicMock(return_value=True),
                                          set_categories=unittest.mock.AsyncMock()) as patched, \
                unittest.mock.patch.dict('os.environ', {'VERSION': 'PROD'}):
            await self.cog._member_changed(before, self.member)
        return patched

    async def test_with_no_earlier_copy_everything_is_recorded(self):
        patched = await self.record(None)
        patched['record_nicknames'].assert_called_once_with([(7, 'Seven')])
        patched['update_member_roles'].assert_called_once_with(self.member)

    async def test_only_what_changed_is_recorded(self):
        before = mocks.MockMember(id=7, display_name='Seven')
        before.roles = list(self.member.roles)
        patched = await self.record(before)
        patched['record_nicknames'].assert_not_called()
        patched['update_member_roles'].assert_not_called()


class CrewsFromDbTest(unittest.TestCase):
    def test_counts_leaders_advisors_and_staff_come_from_the_database(self):
        cache = mocks.cache()
        hk, fsg = Crew(name='Holy Knights', abbr='HK'), Crew(name='FSGood', abbr='FSG')
        # Whatever the partial member list gave is replaced.
        hk.member_count, hk.leaders = 1, ['stale']
        cache.crews_by_name = {hk.name: hk, fsg.name: fsg}
        rows = [('Holy Knights', 1, 'lead', [LEADER]), ('Holy Knights', 2, 'adv', [ADVISOR, CREW_STAFF]),
                ('Holy Knights', 3, 'member', []), ('FSGood', 4, 'other', [LEADER]), ('Disbanded', 5, 'x', [])]
        with unittest.mock.patch('src.no_members_intent.crew_rosters', return_value=rows):
            no_members_intent.crews_from_db(cache)
        self.assertEqual((3, ['lead'], [1], ['adv'], ['adv']),
                         (hk.member_count, hk.leaders, hk.leader_ids, hk.advisors, hk.crew_staff))
        self.assertEqual((1, ['other'], [4], [], []),
                         (fsg.member_count, fsg.leaders, fsg.leader_ids, fsg.advisors, fsg.crew_staff))


if __name__ == '__main__':
    unittest.main()
