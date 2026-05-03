"""Tests for ScoreSheetBot commands.

Commands are discord.ext.commands.Command objects. To test them, we call the
underlying callback directly via `cmd.callback(cog_instance, ctx, ...)`.
This runs the decorator chain and the actual command logic with proper `self`.

Tests are organized by command group:
- Mock battle lifecycle (start, send, end, undo, confirm, clear)
- Battle start variants (battle, reg)
- In-battle utility commands (arena, stream, resize, status, timer, ext)
- Flairing commands (flair, unflair, promote, demote)
"""
import unittest
import unittest.mock
from unittest.mock import patch, AsyncMock, MagicMock

from tests import mocks
from src.scoreSheetBot import ScoreSheetBot
from src.battle import Battle, BattleType, PLAYER_STOCKS
from src.character import Character
from src.constants import *
from src.helpers import key_string

SSB = 'src.scoreSheetBot'


class SSBTestBase(unittest.IsolatedAsyncioTestCase):
    """Base test class with common setup for ScoreSheetBot tests."""

    def setUp(self):
        self.patches = [
            patch(f'{SSB}.update_channel_open', new_callable=AsyncMock),
            patch(f'{SSB}.unlock', new_callable=AsyncMock),
        ]
        for p in self.patches:
            p.start()

        self.bot = mocks.MockBot()
        self.ssb = ScoreSheetBot(bot=self.bot, cache=mocks.cache())

    def tearDown(self):
        for p in self.patches:
            p.stop()

    async def invoke(self, cmd_name, *args, **kwargs):
        """Invoke a command's callback directly on the SSB cog instance."""
        cmd = getattr(self.ssb, cmd_name)
        return await cmd.callback(self.ssb, *args, **kwargs)

    def make_ctx(self, channel_name='⚔test', guild_name=SCS, author_roles=None):
        """Create a MockContext that passes common decorator checks."""
        ctx = mocks.MockContext()
        ctx.channel = mocks.MockTextChannel(name=channel_name)
        ctx.guild = mocks.MockGuild()
        ctx.guild.name = guild_name
        ctx.command = MagicMock()
        ctx.command.name = 'test'
        ctx.message = mocks.MockMessage()
        ctx.message.author = ctx.author
        if author_roles:
            ctx.author.roles = author_roles
        return ctx

    def make_leader_ctx(self):
        """Create a ctx with author having Leader role (passes @is_lead)."""
        return self.make_ctx(author_roles=[mocks.MockRole(name=LEADER)])

    async def start_mock_battle(self, ctx=None, t1='Team1', t2='Team2', size=5):
        """Helper: start a mock battle and return the ctx used."""
        if ctx is None:
            ctx = self.make_ctx()
        await self.invoke('mock', ctx, t1, t2, size)
        return ctx

    async def send_both_players(self, ctx, p1_name='Player1', p2_name='Player2'):
        """Helper: send players for both teams in a mock battle."""
        p1 = mocks.MockMember(name=p1_name, display_name=p1_name)
        p2 = mocks.MockMember(name=p2_name, display_name=p2_name)
        await self.invoke('send', ctx, p1, 'Team1')
        await self.invoke('send', ctx, p2, 'Team2')
        return p1, p2


# =============================================================================
# Mock Battle Lifecycle Tests
# =============================================================================

class TestMockBattleLifecycle(SSBTestBase):
    """Tests for starting, playing, and ending a mock crew battle."""

    async def test_mock_creates_battle(self):
        ctx = await self.start_mock_battle()
        battle = self.ssb._current(ctx)
        self.assertIsNotNone(battle)
        self.assertEqual(battle.team1.name, 'Team1')
        self.assertEqual(battle.team2.name, 'Team2')
        self.assertEqual(battle.battle_type, BattleType.MOCK)

    async def test_mock_rejects_size_zero(self):
        ctx = self.make_ctx()
        await self.invoke('mock', ctx, 'A', 'B', 0)
        self.assertIsNone(self.ssb._current(ctx))
        ctx.send.assert_any_call('Please enter a size greater than 0.')

    async def test_mock_rejects_negative_size(self):
        ctx = self.make_ctx()
        await self.invoke('mock', ctx, 'A', 'B', -1)
        self.assertIsNone(self.ssb._current(ctx))

    async def test_no_battle_decorator_blocks_double_start(self):
        ctx = await self.start_mock_battle()
        await self.invoke('mock', ctx, 'A', 'B', 5)
        # Original battle should still be there
        self.assertEqual(self.ssb._current(ctx).team1.name, 'Team1')

    async def test_ss_channel_decorator_blocks_wrong_channel(self):
        ctx = self.make_ctx(channel_name='general')
        await self.invoke('mock', ctx, 'A', 'B', 5)
        self.assertIsNone(self.ssb._current(ctx))

    async def test_send_player_mock(self):
        ctx = await self.start_mock_battle()
        player = mocks.MockMember(name='Alice', display_name='Alice')
        await self.invoke('send', ctx, player, 'Team1')
        battle = self.ssb._current(ctx)
        self.assertIsNotNone(battle.team1.current_player)
        self.assertIn('Alice', battle.team1.current_player.name)

    async def test_send_requires_team_in_mock(self):
        ctx = await self.start_mock_battle()
        player = mocks.MockMember(name='Alice', display_name='Alice')
        # No team specified and author not in team leaders
        await self.invoke('send', ctx, player)
        ctx.send.assert_any_call(
            'During a mock you need to send with a teamname, like this `,send @playername teamname`.')

    async def test_end_match_mock(self):
        ctx = await self.start_mock_battle()
        await self.send_both_players(ctx)
        battle = self.ssb._current(ctx)
        await self.invoke('end', ctx, 'mario', 3, 'link', 0)
        self.assertEqual(len(battle.matches), 1)
        self.assertIsNone(battle.team2.current_player)

    async def test_undo_match_mock(self):
        ctx = await self.start_mock_battle()
        await self.send_both_players(ctx)
        battle = self.ssb._current(ctx)
        await self.invoke('end', ctx, 'mario', 3, 'link', 0)
        self.assertEqual(len(battle.matches), 1)
        await self.invoke('undo', ctx)
        self.assertEqual(len(battle.matches), 0)

    async def test_confirm_mock_clears_battle(self):
        ctx = await self.start_mock_battle(size=1)
        await self.send_both_players(ctx)
        await self.invoke('end', ctx, 'mario', 3, 'link', 0)
        battle = self.ssb._current(ctx)
        self.assertTrue(battle.battle_over())
        await self.invoke('confirm', ctx)
        self.assertIsNone(self.ssb._current(ctx))

    async def test_confirm_before_battle_over(self):
        ctx = await self.start_mock_battle()
        await self.send_both_players(ctx)
        await self.invoke('confirm', ctx)
        ctx.send.assert_any_call('The battle is not over yet, wait till then to confirm.')

    @patch(f'{SSB}.wait_for_reaction_on_message', new_callable=AsyncMock, return_value=True)
    async def test_clear_mock_battle(self, mock_react):
        ctx = await self.start_mock_battle()
        await self.invoke('clear', ctx)
        self.assertIsNone(self.ssb._current(ctx))


# =============================================================================
# Battle Start Command Tests (battle, reg)
# =============================================================================

class TestBattleStart(SSBTestBase):
    """Tests for starting ranked and reg battles."""

    def _make_crew_members(self):
        author = mocks.MockMember(name='Leader1', display_name='Leader1',
                                  roles=[mocks.hk_role, mocks.MockRole(name=LEADER)])
        opponent = mocks.MockMember(name='Opp1', display_name='Opp1',
                                    roles=[mocks.fsg_role])
        return author, opponent

    async def test_battle_starts_ranked(self):
        author, opponent = self._make_crew_members()
        ctx = self.make_ctx(author_roles=author.roles)
        ctx.author = author
        ctx.guild.roles = self.ssb.cache.scs.roles
        await self.invoke('battle', ctx, opponent, 5)
        battle = self.ssb._current(ctx)
        self.assertIsNotNone(battle)
        self.assertEqual(battle.team1.name, mocks.HK.name)
        self.assertEqual(battle.team2.name, mocks.FSGood.name)

    async def test_battle_rejects_same_crew(self):
        author = mocks.MockMember(name='L1', display_name='L1',
                                  roles=[mocks.hk_role, mocks.MockRole(name=LEADER)])
        opponent = mocks.MockMember(name='L2', display_name='L2',
                                    roles=[mocks.hk_role])
        ctx = self.make_ctx(author_roles=author.roles)
        ctx.author = author
        await self.invoke('battle', ctx, opponent, 5)
        ctx.send.assert_any_call("You can't battle your own crew.")

    async def test_battle_rejects_zero_size(self):
        author, opponent = self._make_crew_members()
        ctx = self.make_ctx(author_roles=author.roles)
        ctx.author = author
        await self.invoke('battle', ctx, opponent, 0)
        ctx.send.assert_any_call('Please enter a size greater than 0.')

    async def test_reg_starts_battle(self):
        author = mocks.MockMember(name='Leader1', display_name='Leader1',
                                  roles=[mocks.hk_role, mocks.MockRole(name=LEADER)])
        ctx = self.make_ctx(author_roles=author.roles)
        ctx.author = author
        await self.invoke('reg', ctx, everything='NewCrew 5')
        battle = self.ssb._current(ctx)
        self.assertIsNotNone(battle)
        self.assertEqual(battle.team1.name, mocks.HK.name)
        self.assertEqual(battle.team2.name, 'NewCrew')
        self.assertEqual(battle.battle_type, BattleType.REG)

    async def test_reg_rejects_bad_format(self):
        author = mocks.MockMember(name='Leader1', display_name='Leader1',
                                  roles=[mocks.hk_role, mocks.MockRole(name=LEADER)])
        ctx = self.make_ctx(author_roles=author.roles)
        ctx.author = author
        await self.invoke('reg', ctx, everything='NoCrew NoSize')
        self.assertIsNone(self.ssb._current(ctx))


# =============================================================================
# In-Battle Utility Commands
# =============================================================================

class TestInBattleCommands(SSBTestBase):
    """Tests for commands that operate on an active battle."""

    async def test_has_sheet_decorator_blocks_no_battle(self):
        ctx = self.make_ctx()
        await self.invoke('status', ctx)
        ctx.send.assert_any_call('Battle is not started.')

    async def test_status_shows_battle(self):
        ctx = await self.start_mock_battle()
        await self.invoke('status', ctx)
        self.assertTrue(ctx.send.called)

    async def test_arena_set_and_get(self):
        ctx = await self.start_mock_battle()
        await self.invoke('arena', ctx, 'ABC123')
        ctx.send.assert_any_call('Updated the id to ABC123')
        self.assertEqual(self.ssb._current(ctx).id, 'ABC123')

    async def test_arena_get_default(self):
        ctx = await self.start_mock_battle()
        await self.invoke('arena', ctx, '')
        battle = self.ssb._current(ctx)
        ctx.send.assert_any_call(f'The lobby id is {battle.id}')

    async def test_stream_set(self):
        ctx = await self.start_mock_battle()
        await self.invoke('stream', ctx, 'https://twitch.tv/test')
        ctx.send.assert_any_call('Updated the stream to https://twitch.tv/test')
        self.assertEqual(self.ssb._current(ctx).stream, 'https://twitch.tv/test')

    async def test_stream_auto_prefix(self):
        ctx = await self.start_mock_battle()
        await self.invoke('stream', ctx, 'mystream')
        self.assertEqual(self.ssb._current(ctx).stream, 'https://twitch.tv/mystream')

    async def test_resize_battle(self):
        ctx = await self.start_mock_battle()
        await self.invoke('resize', ctx, 7)
        battle = self.ssb._current(ctx)
        self.assertEqual(battle.team1.num_players, 7)
        self.assertEqual(battle.team2.num_players, 7)

    async def test_resize_rejects_too_large(self):
        ctx = await self.start_mock_battle()
        await self.invoke('resize', ctx, 10000)
        ctx.send.assert_any_call('Too big. Pls stop')
        self.assertEqual(self.ssb._current(ctx).team1.num_players, 5)

    async def test_timer(self):
        ctx = await self.start_mock_battle()
        await self.invoke('timer', ctx)
        call_args = ctx.send.call_args_list[-1]
        self.assertIn('since the crew battle started', call_args[0][0])

    async def test_ext_status(self):
        ctx = await self.start_mock_battle()
        await self.invoke('ext', ctx)
        call_args = ctx.send.call_args_list[-1]
        self.assertIn('Extension', call_args[0][0])

    async def test_use_ext_mock(self):
        ctx = await self.start_mock_battle()
        await self.invoke('use_ext', ctx, 'Team1')
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any('used their extension' in s for s in call_strs))

    async def test_use_ext_twice_rejected(self):
        ctx = await self.start_mock_battle()
        await self.invoke('use_ext', ctx, 'Team1')
        await self.invoke('use_ext', ctx, 'Team1')
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any('already used' in s for s in call_strs))

    async def test_countdown_rejects_over_10(self):
        ctx = self.make_ctx()
        await self.invoke('countdown', ctx, 11)
        ctx.send.assert_any_call('You can only countdown from 10 or less!')

    async def test_replace_player_mock(self):
        ctx = await self.start_mock_battle()
        p1 = mocks.MockMember(name='Alice', display_name='Alice')
        await self.invoke('send', ctx, p1, 'Team1')
        replacement = mocks.MockMember(name='Bob', display_name='Bob')
        await self.invoke('replace', ctx, replacement, 'Team1')
        battle = self.ssb._current(ctx)
        self.assertIn('Bob', battle.team1.current_player.name)

    async def test_timerstock_mock(self):
        ctx = await self.start_mock_battle()
        await self.send_both_players(ctx)
        battle = self.ssb._current(ctx)
        stocks_before = battle.team1.stocks
        await self.invoke('timerstock', ctx, 'Team1')
        self.assertEqual(battle.team1.stocks, stocks_before - 1)


# =============================================================================
# Full Mock Battle Flow (Integration)
# =============================================================================

class TestMockBattleIntegration(SSBTestBase):
    """End-to-end test of a full mock crew battle lifecycle."""

    async def test_full_mock_battle(self):
        ctx = await self.start_mock_battle(size=1)
        battle = self.ssb._current(ctx)
        self.assertIsNotNone(battle)

        await self.send_both_players(ctx)
        self.assertTrue(battle.match_ready())

        await self.invoke('end', ctx, 'mario', 3, 'link', 0)
        self.assertTrue(battle.battle_over())
        self.assertEqual(battle.team2.stocks, 0)

        await self.invoke('confirm', ctx)
        self.assertIsNone(self.ssb._current(ctx))

    async def test_mock_battle_with_undo_and_redo(self):
        ctx = await self.start_mock_battle(size=1)
        await self.send_both_players(ctx)
        battle = self.ssb._current(ctx)

        await self.invoke('end', ctx, 'mario', 3, 'link', 0)
        self.assertEqual(len(battle.matches), 1)

        await self.invoke('undo', ctx)
        self.assertEqual(len(battle.matches), 0)
        self.assertEqual(battle.team1.stocks, PLAYER_STOCKS)
        self.assertEqual(battle.team2.stocks, PLAYER_STOCKS)

        await self.invoke('end', ctx, 'mario', 0, 'link', 3)
        self.assertTrue(battle.battle_over())
        self.assertEqual(battle.team1.stocks, 0)


# =============================================================================
# Flairing Commands
# =============================================================================

class TestFlairingCommands(SSBTestBase):
    """Tests for flair, unflair, promote, demote commands."""

    def _staff_ctx(self):
        admin_role = mocks.MockRole(name=ADMIN)
        return self.make_ctx(channel_name=FLAIRING_CHANNEL_NAME,
                             author_roles=[admin_role, mocks.hk_role])

    async def test_flair_rejects_bot(self):
        ctx = self._staff_ctx()
        bot_member = mocks.MockMember(name='Bot', bot=True)
        bot_member.roles = [mocks.MockRole(name=BOT)]
        await self.invoke('flair', ctx, bot_member, new_crew=mocks.HK.name)
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any("can't flair a bot" in s for s in call_strs))

    async def test_flair_rejects_no_power(self):
        ctx = self.make_ctx(channel_name=FLAIRING_CHANNEL_NAME,
                            author_roles=[mocks.MockRole(name=ADMIN)])
        ctx.author.roles = []
        member = mocks.MockMember(name='Newbie')
        await self.invoke('flair', ctx, member, new_crew=mocks.HK.name)
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any('cannot flair' in s.lower() for s in call_strs))

    async def test_promote_rejects_non_crew_member(self):
        ctx = self._staff_ctx()
        member = mocks.MockMember(name='NoCrew', roles=[])
        await self.invoke('promote', ctx, member)
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any('not in a crew' in s for s in call_strs))

    async def test_demote_rejects_non_leader_role(self):
        ctx = self._staff_ctx()
        member = mocks.MockMember(name='Regular', roles=[mocks.hk_role])
        await self.invoke('demote', ctx, member)
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any("can't be demoted" in s for s in call_strs))

    async def test_flairing_off_blocks_flair(self):
        self.ssb.cache.flairing_allowed = False
        leader_role = mocks.MockRole(name=LEADER)
        ctx = self.make_ctx(channel_name=FLAIRING_CHANNEL_NAME,
                            author_roles=[leader_role, mocks.hk_role])
        member = mocks.MockMember(name='Test')
        await self.invoke('flair', ctx, member, new_crew=mocks.HK.name)
        call_strs = [str(c) for c in ctx.send.call_args_list]
        self.assertTrue(any('disabled' in s for s in call_strs))


# =============================================================================
# Internal / Helper Method Tests
# =============================================================================

class TestInternalMethods(SSBTestBase):
    """Tests for internal ScoreSheetBot methods."""

    def test_current_returns_none_when_no_battle(self):
        ctx = self.make_ctx()
        self.assertIsNone(self.ssb._current(ctx))

    async def test_set_current_stores_battle(self):
        ctx = self.make_ctx()
        battle = Battle('A', 'B', 5, BattleType.MOCK)
        await self.ssb._set_current(ctx, battle)
        self.assertEqual(self.ssb._current(ctx), battle)

    async def test_clear_current_removes_battle(self):
        ctx = self.make_ctx()
        battle = Battle('A', 'B', 5, BattleType.MOCK)
        await self.ssb._set_current(ctx, battle)
        await self.ssb._clear_current(ctx)
        self.assertIsNone(self.ssb._current(ctx))

    async def test_reject_outsiders_allows_mock(self):
        ctx = self.make_ctx()
        battle = Battle('A', 'B', 5, BattleType.MOCK)
        await self.ssb._set_current(ctx, battle)
        # Should not raise for mock battles
        await self.ssb._reject_outsiders(ctx)

    def test_cache_property(self):
        self.assertIsNotNone(self.ssb.cache)
        self.assertIsNotNone(self.ssb.cache.scs)

    async def test_sync_command(self):
        ctx = self.make_ctx(author_roles=[mocks.MockRole(name=ADMIN)])
        self.bot.tree = AsyncMock()
        await self.invoke('sync', ctx)
        self.bot.tree.sync.assert_called_once()
        ctx.send.assert_called_with('Command tree synced.')
