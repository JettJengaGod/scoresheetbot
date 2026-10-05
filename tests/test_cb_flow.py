"""Characterization tests for the crew battle commands.

Each script is run once per invocation mode (prefix and slash) and compared with a snapshot recorded
from the prefix commands, so the two paths have to keep producing the same output.
"""
import unittest
import unittest.mock

from src.constants import *
from tests import mocks
from tests.harness import MODES, FakeContext, assert_snapshot, invoke, make_cog

ARENA = '⚔-arena-1'


class CrewBattleFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.guild = self.cog.cache.scs
        self.channel = mocks.MockTextChannel(name=ARENA, id=555, guild=self.guild)
        verified = mocks.MockRole(name=VERIFIED)
        self.hk_lead = mocks.MockMember(name='hk_lead', id=11, display_name='HK Lead',
                                        roles=[mocks.hk_role, mocks.leader, verified])
        self.hk_player = mocks.MockMember(name='hk_player', id=12, display_name='HK_Player',
                                          roles=[mocks.hk_role, verified])
        self.hk_unverified = mocks.MockMember(name='hk_unverified', id=13, display_name='HK Unverified',
                                              roles=[mocks.hk_role])
        self.fsg_lead = mocks.MockMember(name='fsg_lead', id=21, display_name='FSG Lead',
                                         roles=[mocks.fsg_role, mocks.leader, verified])
        self.fsg_player = mocks.MockMember(name='fsg_player', id=22, display_name='FSG Player',
                                           roles=[mocks.fsg_role, verified])
        self.nobody = mocks.MockMember(name='nobody', id=31, display_name='Nobody')

    def ctx(self, mode, author, channel=None) -> FakeContext:
        return FakeContext(self.cog, author, channel or self.channel, self.guild, mode)

    async def run_script(self, mode, script):
        """Runs (author, command, args) steps and returns what each step sent."""
        out = []
        for author, name, args in script:
            ctx = self.ctx(mode, author)
            await invoke(self.cog, name, ctx, *args)
            out.append({'command': name, 'sent': ctx.sent})
        return out

    async def check_script(self, snapshot, script, confirms=()):
        for mode in MODES:
            with self.subTest(mode=mode):
                self.setUp()
                with unittest.mock.patch('src.scoreSheetBot.wait_for_reaction_on_message',
                                         unittest.mock.AsyncMock(side_effect=list(confirms))):
                    assert_snapshot(self, snapshot, await self.run_script(mode, script))

    async def test_mock_battle(self):
        a, b = self.nobody, self.fsg_player
        await self.check_script('cb_mock_battle', [
            (a, 'mock', ('Red', 'Blue', 0)),
            (a, 'mock', ('Red', 'Blue', 2)),
            (a, 'mock', ('Red', 'Blue', 2)),
            (a, 'send', (self.hk_player,)),
            (a, 'send', (self.hk_player, 'Red')),
            (b, 'send', (self.fsg_player, 'Blue')),
            (a, 'arena', ('ABCDE',)),
            (a, 'arena', ()),
            (a, 'stream', ('jett',)),
            (a, 'stream', ()),
            (a, 'end', ('mario', 3, 'fox', 1)),
            (a, 'send', (self.hk_unverified,)),
            (b, 'timerstock', ()),
            (a, 'ext', ()),
            (a, 'use_ext', ()),
            (a, 'use_ext', ()),
            (a, 'undo', ()),
            (a, 'resize', (3,)),
            (a, 'resize', (10000,)),
            (a, 'status', ()),
            (a, 'confirm', ()),
            (a, 'replace', (self.hk_lead,)),
            (a, 'end', ('mario', 0, 'fox', 2)),
            (a, 'forfeit', ()),
            (a, 'confirm', ()),
            (a, 'clear', ()),
            (a, 'clear', ()),
            (a, 'status', ()),
        ], confirms=[False, True])

    async def test_ranked_battle(self):
        hk, fsg = self.hk_lead, self.fsg_lead
        await self.check_script('cb_ranked_battle', [
            (hk, 'battle', (self.fsg_lead, 0)),
            (hk, 'battle', (self.hk_player, 5)),
            (hk, 'battle', (self.fsg_lead, 5)),
            (hk, 'send', (self.hk_unverified,)),
            (hk, 'send', (self.fsg_player,)),
            (hk, 'send', (self.hk_player,)),
            (fsg, 'send', (self.fsg_player,)),
            (self.hk_player, 'end', ('mario', 3, 'fox', 0)),
            (self.nobody, 'end', ('mario', 3, 'fox', 0)),
            (hk, 'end', ('mario', 2, 'fox', 0)),
            (fsg, 'send', (self.fsg_player,)),
            (fsg, 'send', (self.fsg_lead,)),
            (hk, 'timerstock', ()),
            (hk, 'replace', (self.hk_lead,)),
            (hk, 'undo', ()),
            (hk, 'resize', (6,)),
            (hk, 'confirm', ()),
        ])

    async def test_guards(self):
        other_channel = mocks.MockTextChannel(name='general', id=556, guild=self.guild)
        for mode in MODES:
            with self.subTest(mode=mode):
                self.setUp()
                out = []
                for author, channel, name, args in [
                    (self.hk_lead, other_channel, 'battle', (self.fsg_lead, 5)),
                    (self.hk_player, self.channel, 'battle', (self.fsg_lead, 5)),
                    (self.hk_lead, self.channel, 'send', (self.hk_player,)),
                    (self.hk_lead, self.channel, 'status', ()),
                    (self.hk_lead, self.channel, 'battle', (self.fsg_lead, 5)),
                    (self.hk_lead, self.channel, 'battle', (self.fsg_lead, 5)),
                    (self.hk_player, self.channel, 'send', (self.hk_player,)),
                    (self.hk_lead, other_channel, 'status', ()),
                    (self.nobody, self.channel, 'lock', (None,)),
                ]:
                    ctx = self.ctx(mode, author, channel)
                    await invoke(self.cog, name, ctx, *args)
                    out.append({'command': name, 'sent': ctx.sent})
                assert_snapshot(self, 'cb_guards', out)


if __name__ == '__main__':
    unittest.main()
