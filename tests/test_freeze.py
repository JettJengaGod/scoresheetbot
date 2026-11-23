"""Tests for flairing freezes: `freeze` sets when a crew's freeze ends, and a frozen crew can't flair."""
import unittest
import unittest.mock
from datetime import date

from freezegun import freeze_time

from src.constants import FLAIRING_CHANNEL_NAME
from src.helpers import parse_freeze_end
from tests import mocks
from tests.harness import MODES, PREFIX, SLASH, FakeContext, invoke, invoke_slash, make_cog


@freeze_time('2026-11-23 12:00:00')
class ParseFreezeEndTest(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(date(2026, 12, 31), parse_freeze_end('2026-12-31'))
        self.assertEqual(date(2026, 12, 31), parse_freeze_end('12/31/2026'))
        self.assertEqual(date(2027, 1, 2), parse_freeze_end('1/2/27'))

    def test_a_month_and_day_is_the_next_one_to_come(self):
        self.assertEqual(date(2026, 12, 31), parse_freeze_end('12/31'))
        self.assertEqual(date(2027, 3, 1), parse_freeze_end('3/1'))
        self.assertEqual(date(2027, 11, 23), parse_freeze_end('11/23'))

    def test_lengths(self):
        self.assertEqual(date(2026, 12, 7), parse_freeze_end('2W'))
        self.assertEqual(date(2026, 11, 26), parse_freeze_end('3d'))
        self.assertEqual(date(2027, 1, 23), parse_freeze_end('2M'))

    def test_past_dates_and_nonsense_are_refused(self):
        for text in ('2026-11-23', '2020-01-01', '13/45', 'HK', '0D'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_freeze_end(text)


@freeze_time('2026-11-23 12:00:00')
class FreezeCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.guild = self.cog.cache.scs
        self.channel = mocks.MockTextChannel(name='staff-chat', id=5, guild=self.guild)
        self.staff = mocks.MockMember(id=1, display_name='Staff', roles=[mocks.admin])
        self.hk = self.cog.cache.crews_by_tag['hk']
        self.addCleanup(setattr, self.hk, 'freeze', '')

    async def freeze(self, everything, mode=PREFIX, confirm=True):
        ctx = FakeContext(self.cog, self.staff, self.channel, self.guild, mode)
        with unittest.mock.patch.multiple(
                'src.scoreSheetBot', freeze_crew=unittest.mock.DEFAULT,
                wait_for_reaction_on_message=unittest.mock.AsyncMock(return_value=confirm)) as patched:
            if mode == SLASH:
                crew, _, until = everything.rpartition(' ')
                await invoke_slash(self.cog, 'freeze', ctx, crew=crew, until=until)
            else:
                await invoke(self.cog, 'freeze', ctx, everything=everything)
        return ctx, patched['freeze_crew']

    async def test_freezes_until_a_date(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.hk.freeze = ''
                ctx, freeze_crew = await self.freeze('Holy Knights 12/31', mode)
                freeze_crew.assert_called_once_with(self.hk, date(2026, 12, 31))
                self.assertEqual('12/31/2026', self.hk.freeze, 'flairing is blocked straight away')
                self.assertIn('Holy Knights is flairing frozen till 12/31/2026.',
                              [sent['content'] for sent in ctx.sent])

    async def test_freezes_for_a_length(self):
        _, freeze_crew = await self.freeze('HK 2W')
        freeze_crew.assert_called_once_with(self.hk, date(2026, 12, 7))

    async def test_changes_the_end_of_a_freeze(self):
        self.hk.freeze = '12/01/2026'
        ctx, freeze_crew = await self.freeze('HK 2027-01-15')
        self.assertIn('already flairing frozen till 12/01/2026', ctx.sent[0]['content'])
        freeze_crew.assert_called_once_with(self.hk, date(2027, 1, 15))
        self.assertEqual('01/15/2027', self.hk.freeze)

    async def test_unfreezes_a_frozen_crew(self):
        self.hk.freeze = '12/01/2026'
        _, freeze_crew = await self.freeze('HK')
        freeze_crew.assert_called_once_with(self.hk, None)
        self.assertEqual('', self.hk.freeze)

    async def test_freezes_indefinitely_without_an_end(self):
        _, freeze_crew = await self.freeze('HK')
        freeze_crew.assert_called_once_with(self.hk, date(2069, 4, 20))

    async def test_nothing_changes_when_not_confirmed(self):
        _, freeze_crew = await self.freeze('HK 12/31', confirm=False)
        freeze_crew.assert_not_called()
        self.assertEqual('', self.hk.freeze)

    async def test_an_end_that_has_passed_is_refused(self):
        ctx, freeze_crew = await self.freeze('HK 1/1/2026')
        freeze_crew.assert_not_called()
        self.assertIn('has already passed', ctx.sent[0]['content'])

    async def test_only_staff_can_freeze(self):
        self.staff.roles = [mocks.leader, mocks.hk_role]
        ctx, freeze_crew = await self.freeze('HK 12/31')
        freeze_crew.assert_not_called()
        self.assertIn('You need to be one of', ctx.sent[0]['content'])


class FrozenCrewFlairTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.cog.cache.flairing_allowed = True
        self.guild = self.cog.cache.scs
        self.channel = mocks.MockTextChannel(name=FLAIRING_CHANNEL_NAME, id=5, guild=self.guild)
        self.target = mocks.MockMember(id=7, display_name='Target')
        self.hk = self.cog.cache.crews_by_tag['hk']
        self.hk.freeze = '12/31/2026'
        self.addCleanup(setattr, self.hk, 'freeze', '')

    async def flair(self, author, member, new_crew=None):
        ctx = FakeContext(self.cog, author, self.channel, self.guild, PREFIX)
        await invoke(self.cog, 'flair', ctx, member, new_crew=new_crew)
        return [sent['content'] for sent in ctx.sent]

    async def test_a_frozen_crews_leader_cant_flair(self):
        leader = mocks.MockMember(id=2, display_name='Lead', roles=[mocks.leader, mocks.hk_role])
        # Naming their own crew doesn't get round it.
        for new_crew in (None, 'HK'):
            with self.subTest(new_crew=new_crew):
                sent = await self.flair(leader, self.target, new_crew)
                self.assertEqual(['<@!2>: Holy Knights is flairing frozen till 12/31/2026 and can\'t flair people!'], sent)

    async def test_staff_can_still_flair_for_a_frozen_crew(self):
        staff = mocks.MockMember(id=3, display_name='Staff', roles=[mocks.admin, mocks.hk_role])
        # Flairing themselves stops at the next check, which shows the freeze let them through.
        sent = await self.flair(staff, staff)
        self.assertEqual(['<@!3>: Stop flairing yourself, stop flairing yourself.'], sent)
