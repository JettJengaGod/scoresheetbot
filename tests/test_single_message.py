"""Tests that commands answer in a single message: notes go with the main reply, and the outcome of a
confirmation goes in the message that asked for it."""
import unittest
import unittest.mock

import discord

from src.battle import BattleType
from src.constants import *
from src.helpers import MESSAGE_LIMIT, answer_prompt, join_lines, send_sheet
from tests import mocks
from tests.harness import MODES, FakeContext, FakeMessage, find_command, invoke
from tests.test_cb_flow import CrewBattleFlowTest


def contents(ctx):
    return [m['content'] for m in ctx.sent if m['content'] != 'Done.']


class SendSheetTest(unittest.IsolatedAsyncioTestCase):
    def battle(self, over=False, confirms=(False, False)):
        battle = unittest.mock.MagicMock(battle_type=BattleType.RANKED, confirms=list(confirms))
        battle.embed.return_value = discord.Embed(title='Sheet', description='The sheet')
        battle.battle_over.return_value = over
        battle.team1.name, battle.team2.name = 'Holy Knights', 'FSGood'
        battle.team1.leader, battle.team2.leader = {'<@1>'}, {'<@2>'}
        return battle

    def channel(self):
        channel = unittest.mock.MagicMock()
        channel.send = unittest.mock.AsyncMock(side_effect=lambda *a, **k: FakeMessage(*a, k.get('embed')))
        return channel

    async def test_the_note_and_the_request_to_confirm_share_the_sheet_message(self):
        channel = self.channel()
        await send_sheet(channel, self.battle(over=True, confirms=(True, False)), content='A note')
        channel.send.assert_awaited_once()
        text = channel.send.await_args.args[0]
        self.assertEqual('A note\nPlease confirm: \n FSGood: <@2> please `/confirm`.', text)
        self.assertEqual('Sheet', channel.send.await_args.kwargs['embed'].title)

    async def test_a_sheet_with_nothing_to_say_has_no_text(self):
        channel = self.channel()
        await send_sheet(channel, self.battle())
        channel.send.assert_awaited_once_with(None, embed=unittest.mock.ANY)

    async def test_the_sheet_can_go_in_a_prompt(self):
        channel, prompt = self.channel(), FakeMessage('Are you sure?')
        self.assertIs(prompt, await send_sheet(channel, self.battle(), content='Done', prompt=prompt))
        channel.send.assert_not_awaited()
        prompt.edit.assert_awaited_once_with(content='Done', embed=unittest.mock.ANY)

    async def test_text_too_long_for_the_sheet_message_goes_first_on_its_own(self):
        channel = self.channel()
        lines = ['x' * 99] * (MESSAGE_LIMIT // 100 + 1)
        await send_sheet(channel, self.battle(), content='\n'.join(lines))
        self.assertEqual(3, channel.send.await_count)  # the text, split, then the sheet
        self.assertEqual(None, channel.send.await_args_list[-1].args[0])


class AnswerPromptTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_outcome_replaces_the_question(self):
        ctx, prompt = unittest.mock.MagicMock(), FakeMessage('Are you sure?')
        await answer_prompt(ctx, prompt, 'Done.')
        prompt.edit.assert_awaited_once_with(content='Done.')

    async def test_an_embed_can_be_replaced_or_removed(self):
        ctx, prompt = unittest.mock.MagicMock(), FakeMessage('Are you sure?')
        await answer_prompt(ctx, prompt, 'Done.', embed=None)
        prompt.edit.assert_awaited_once_with(content='Done.', embed=None)
        prompt.edit.reset_mock()
        await answer_prompt(ctx, prompt, embed=discord.Embed(title='Result', description='short'))
        self.assertEqual('Result', prompt.edit.await_args.kwargs['embed'].title)

    async def test_an_embed_too_long_for_one_message_continues_after_it(self):
        ctx, prompt = unittest.mock.MagicMock(), FakeMessage('Are you sure?')
        ctx.send = unittest.mock.AsyncMock()
        long = discord.Embed(title='Result', description='\n'.join(['line'] * 1000))
        await answer_prompt(ctx, prompt, embed=long)
        prompt.edit.assert_awaited_once()
        self.assertGreater(ctx.send.await_count, 0)

    def test_join_lines_skips_empty_lines(self):
        self.assertEqual('a\nb', join_lines(None, 'a', '', 'b'))


class CommandsTest(CrewBattleFlowTest):
    """Commands that used to send several messages."""

    # The crew battle scripts are run by CrewBattleFlowTest itself.
    test_mock_battle = test_ranked_battle = test_guards = None

    def prompts(self, *answers):
        """Answers confirmations in turn, and keeps the prompts they were asked on."""
        asked = []

        async def answer(confirm, cancel, message, *args):
            asked.append(message)
            return answers[len(asked) - 1]

        return asked, unittest.mock.patch('src.scoreSheetBot.wait_for_reaction_on_message', side_effect=answer)

    async def test_confirming_a_ranked_battle_sends_the_sheet_and_the_outcome_together(self):
        history = mocks.MockTextChannel(name=SCORESHEET_HISTORY, id=601, guild=self.guild)
        output = mocks.MockTextChannel(name=OUTPUT, id=602, guild=self.guild)
        def posted(content=None, embed=None, **kwargs):
            message = FakeMessage(content, embed)
            message.jump_url = f'https://discord.com/channels/1/2/{message.id}'
            return message

        for channel in (history, output):
            channel.send = unittest.mock.AsyncMock(side_effect=posted)
        self.guild.channels = [history, output]
        services = dict(add_finished_battle=unittest.mock.MagicMock(return_value=77),
                        battle_weight_changes=unittest.mock.DEFAULT,
                        battle_elo_changes=unittest.mock.MagicMock(return_value=(1500, 20, 1480, -20, 0, 0, 50, 50)),
                        extra_slot_used=unittest.mock.MagicMock(return_value=False),
                        battles_since_sunday=unittest.mock.MagicMock(return_value=3),
                        mod_slot=unittest.mock.DEFAULT, set_extra_used=unittest.mock.DEFAULT)
        for mode in MODES:
            with self.subTest(mode=mode):
                self.setUp()
                self.guild.channels = [history, output]
                with unittest.mock.patch.multiple('src.scoreSheetBot', **services):
                    for author, name, args in [(self.hk_lead, 'battle', (self.fsg_lead, 1)),
                                               (self.hk_lead, 'send', (self.hk_player,)),
                                               (self.fsg_lead, 'send', (self.fsg_player,)),
                                               (self.hk_lead, 'end', ('mario', 3, 'fox', 0))]:
                        await invoke(self.cog, name, self.ctx(mode, author), *args)
                    first = self.ctx(mode, self.hk_lead)
                    await invoke(self.cog, 'confirm', first)
                    second = self.ctx(mode, self.fsg_lead)
                    await invoke(self.cog, 'confirm', second)
                [half] = [m for m in first.sent if m['content'] != 'Done.']
                self.assertTrue(half['embed'])
                self.assertIn('Please confirm', half['content'])
                [done] = [m for m in second.sent if m['content'] != 'Done.']
                self.assertTrue(done['embed'])
                self.assertIn('has been confirmed by both sides', done['content'])
                self.assertEqual(2, done['content'].count('got a slot back'))

    async def test_clear_asks_once_and_answers_in_the_same_message(self):
        await invoke(self.cog, 'mock', self.ctx(MODES[0], self.nobody), 'Red', 'Blue', 2)
        asked, patch = self.prompts(True)
        ctx = self.ctx(MODES[0], self.nobody)
        with patch:
            await invoke(self.cog, 'clear', ctx)
        self.assertEqual(1, len(contents(ctx)))
        self.assertIn('bannable offence', contents(ctx)[0])
        asked[0].edit.assert_awaited_once_with(content=f'{self.nobody.mention} cleared the crew battle.')

    async def test_a_canceled_forfeit_says_so_in_the_prompt(self):
        await invoke(self.cog, 'mock', self.ctx(MODES[0], self.nobody), 'Red', 'Blue', 2)
        await invoke(self.cog, 'send', self.ctx(MODES[0], self.nobody), self.hk_player, 'Red')
        asked, patch = self.prompts(False)
        ctx = self.ctx(MODES[0], self.nobody)
        with patch:
            await invoke(self.cog, 'forfeit', ctx, 'Red')
        self.assertEqual(1, len(contents(ctx)))
        asked[0].edit.assert_awaited_once_with(content=f'{self.nobody.mention}: forfeit canceled or timed out!')

    async def test_char_answers_in_one_message(self):
        ctx = self.ctx(MODES[0], self.nobody)
        await invoke(self.cog, 'char', ctx, 'ness2')
        [text] = contents(ctx)
        self.assertIn('What you put:', text)
        self.assertIn('All alts in order:', text)

    async def test_a_members_crew_is_named_in_the_same_message_as_the_answer(self):
        hk = mocks.HK
        for name in ('crew', 'logo'):
            with self.subTest(command=name):
                ctx = self.ctx(MODES[0], self.hk_player)
                await invoke(self.cog, name, ctx)
                [message] = [m for m in ctx.sent if m['content'] != 'Done.']
                self.assertEqual(f'{self.hk_player.display_name} is in {hk.name}.', message['content'])
                self.assertTrue(message['embed'])

    async def test_slot_commands_answer_in_one_message(self):
        staff = mocks.MockMember(name='staff', id=40, display_name='Staff', roles=[mocks.admin, mocks.hk_role])
        services = dict(extra_slots=unittest.mock.MagicMock(return_value=(1, 5, 2)),
                        cur_slot_set=unittest.mock.MagicMock(return_value=4),
                        set_return_slots=unittest.mock.MagicMock(return_value=(1, 2, 5)))
        for name, args, lines in (('slots', (), 2), ('setslots', (4,), 3), ('setreturnslots', (1,), 3),
                                  ('fixunflair', (), 5)):
            with self.subTest(command=name):
                ctx = self.ctx(MODES[0], staff)
                with unittest.mock.patch.multiple('src.scoreSheetBot', **services):
                    await invoke(self.cog, name, ctx, *args)
                [text] = contents(ctx)
                self.assertEqual(lines, len(text.split('\n')), text)

    async def test_a_called_coin_lands_in_the_message_that_asked(self):
        asked, patch = self.prompts(True)
        ctx = self.ctx(MODES[0], self.hk_lead)
        with patch, unittest.mock.patch('src.scoreSheetBot.random.getrandbits', return_value=1), \
                unittest.mock.patch('src.scoreSheetBot.discord.File') as image:
            await invoke(self.cog, 'coin', ctx, self.fsg_lead)
        self.assertEqual(1, len(contents(ctx)))
        asked[0].edit.assert_awaited_once_with(
            content=f'{self.fsg_lead.display_name} chose heads and won the flip!\nYour coin flip landed on heads',
            attachments=[image.return_value])


if __name__ == '__main__':
    unittest.main()
