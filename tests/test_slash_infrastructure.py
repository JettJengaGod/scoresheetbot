"""Tests for the pieces prefix and slash commands share: guards, confirmations, paging and cog hooks."""
import asyncio
import types
import unittest
import unittest.mock

import discord

from src.constants import *
from src.decorators import GuardFailure
from src.helpers import (AuthorView, Paged, PaginatorView, delete_invocation, response_message, wait_choice,
                         wait_for_reaction_on_message)
from tests import mocks
from tests.harness import (MODES, PREFIX, SLASH, FakeContext, FakeMessage, find_command, invoke, make_cog,
                           no_external_services)


def press(user_id: int) -> unittest.mock.MagicMock:
    """An interaction as produced by `user_id` pressing a button."""
    interaction = unittest.mock.MagicMock()
    interaction.user.id = user_id
    interaction.response.edit_message = unittest.mock.AsyncMock()
    interaction.response.send_message = unittest.mock.AsyncMock()
    return interaction


async def answer(message: FakeMessage, button: int, user_id: int) -> unittest.mock.MagicMock:
    """Waits for a view to be attached to `message`, then presses one of its buttons."""
    while not message.edit.await_args:
        await asyncio.sleep(0)
    view = message.edit.await_args.kwargs['view']
    interaction = press(user_id)
    if await view.interaction_check(interaction):
        await view.children[button].callback(interaction)
    return interaction


class ConfirmationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.author = mocks.MockMember(id=1, display_name='Author')
        self.message = FakeMessage('Are you sure?')

    async def ask(self, button, user_id=1, timeout=30.0):
        waiting = asyncio.create_task(
            wait_for_reaction_on_message(YES, NO, self.message, self.author, None, timeout))
        interaction = await answer(self.message, button, user_id)
        return waiting, interaction

    async def test_confirm(self):
        waiting, interaction = await self.ask(0)
        self.assertTrue(await waiting)
        interaction.response.edit_message.assert_awaited_once_with(view=None)

    async def test_cancel(self):
        waiting, _ = await self.ask(1)
        self.assertFalse(await waiting)

    async def test_other_people_cannot_answer(self):
        waiting, interaction = await self.ask(0, user_id=2, timeout=0.05)
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.await_args.kwargs['ephemeral'])
        self.assertFalse(await waiting, 'nobody allowed answered, so it should time out')

    async def test_timeout_removes_buttons(self):
        result = await wait_for_reaction_on_message(YES, NO, self.message, self.author, None, 0.01)
        self.assertFalse(result)
        self.assertEqual(self.message.edit.await_args.kwargs, {'view': None})

    async def test_buttons_use_the_given_emoji(self):
        view = AuthorView(self.author, 30)
        view.add_answer(YES, discord.ButtonStyle.green, True)
        self.assertEqual(str(view.children[0].emoji), YES)

    async def test_choice(self):
        for button, expected in ((0, 0), (2, 2), (3, -1)):
            with self.subTest(button=button):
                message = FakeMessage('Pick one')
                waiting = asyncio.create_task(wait_choice(3, message, self.author, None, 30))
                await answer(message, button, 1)
                self.assertEqual(expected, await waiting)

    async def test_choice_timeout_and_too_many_options(self):
        self.assertEqual(-1, await wait_choice(2, self.message, self.author, None, 0.01))
        self.assertEqual(-1, await wait_choice(5, self.message, self.author, None, 0.01))


class PaginatorTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.author = mocks.MockMember(id=1)
        self.ctx = FakeContext(self.cog, self.author, mocks.MockTextChannel(), self.cog.cache.scs)

    def test_paged_numbers_entries_across_pages(self):
        pages = Paged([f'item{i}' for i in range(12)], title='Things', thumbnail='https://example.com/a.png').get_pages()
        self.assertEqual(2, len(pages))
        self.assertTrue(pages[0].description.startswith('1. item0\n2. item1'))
        self.assertEqual('11. item10\n12. item11', pages[1].description)
        self.assertEqual('Things', pages[1].title)
        self.assertEqual('https://example.com/a.png', pages[1].thumbnail.url)

    def test_paged_with_no_data_still_has_a_page(self):
        self.assertEqual(1, len(Paged([], title='Empty').get_pages()))

    async def test_single_page_has_no_buttons(self):
        view = PaginatorView(Paged(['a'], title='One').get_pages())
        view.message = FakeMessage()
        with unittest.mock.patch.object(self.ctx, 'send', unittest.mock.AsyncMock()) as send:
            await view.start(self.ctx)
        self.assertNotIn('view', send.await_args.kwargs)

    async def test_paging(self):
        pages = Paged([f'item{i}' for i in range(25)], title='Things').get_pages()
        view = PaginatorView(pages)
        with unittest.mock.patch.object(self.ctx, 'send', unittest.mock.AsyncMock()) as send:
            await view.start(self.ctx)
        self.assertIs(send.await_args.kwargs['view'], view)
        self.assertTrue(view.prev_page.disabled)
        self.assertFalse(view.next_page.disabled)

        interaction = press(1)
        await view.next_page.callback(interaction)
        self.assertEqual(1, view.current_page)
        self.assertIs(interaction.response.edit_message.await_args.kwargs['embed'], pages[1])
        await view.last_page.callback(press(1))
        self.assertEqual(2, view.current_page)
        self.assertTrue(view.next_page.disabled)
        await view.next_page.callback(press(1))
        self.assertEqual(2, view.current_page)
        await view.first_page.callback(press(1))
        self.assertEqual(0, view.current_page)

    async def test_only_the_invoker_can_page(self):
        view = PaginatorView(Paged(list('abcdefghijkl'), title='Things').get_pages())
        with unittest.mock.patch.object(self.ctx, 'send', unittest.mock.AsyncMock()):
            await view.start(self.ctx)
        self.assertTrue(await view.interaction_check(press(1)))
        self.assertFalse(await view.interaction_check(press(2)))


class InvocationMessageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.author = mocks.MockMember(id=1)

    def ctx(self, mode):
        return FakeContext(self.cog, self.author, mocks.MockTextChannel(), self.cog.cache.scs, mode)

    async def test_prefix_invocation_is_deleted(self):
        ctx = self.ctx(PREFIX)
        await delete_invocation(ctx, delay=3)
        ctx.message.delete.assert_awaited_once_with(delay=3)

    async def test_slash_has_no_invocation_to_delete(self):
        ctx = self.ctx(SLASH)
        await delete_invocation(ctx)
        ctx.message.delete.assert_not_awaited()

    async def test_response_message_is_the_same_in_both_modes(self):
        sent = []
        for mode in MODES:
            ctx = self.ctx(mode)
            await response_message(ctx, 'hello')
            sent.append(ctx.sent)
        self.assertEqual(sent[0], sent[1])
        self.assertEqual(f'{self.author.mention}: hello', sent[0][0]['content'])


class CogHookTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.author = mocks.MockMember(id=1)
        self.channel = mocks.MockTextChannel(name='⚔-arena', id=777)

    def ctx(self, mode):
        return FakeContext(self.cog, self.author, self.channel, self.cog.cache.scs, mode)

    async def test_slash_commands_are_deferred_and_prefix_commands_are_not(self):
        for mode, deferred in ((PREFIX, False), (SLASH, True)):
            ctx = self.ctx(mode)
            await invoke(self.cog, 'invite', ctx)
            self.assertEqual(deferred, ctx.deferred, mode)

    async def test_guard_failure_is_not_deferred_and_reported_once(self):
        ctx = FakeContext(self.cog, self.author, mocks.MockTextChannel(name='general'), self.cog.cache.scs, SLASH)
        await invoke(self.cog, 'status', ctx)
        self.assertFalse(ctx.deferred)
        self.assertEqual(1, len(ctx.sent))

    async def test_disabled_channel_and_deactivated_command_block_both_modes(self):
        for mode in MODES:
            for patched, expected in (
                    ({'disabled_channels': lambda: [777]}, 'Jettbot is disabled for this channel'),
                    ({'command_lookup': lambda name: (name, True)}, 'invite is deactivated'),
            ):
                with self.subTest(mode=mode, expected=expected):
                    ctx = self.ctx(mode)
                    ctx.command = self.cog.bot.get_command('invite')
                    ctx.command.name = 'invite'
                    with no_external_services(), unittest.mock.patch.multiple('src.scoreSheetBot', **patched):
                        with self.assertRaises(GuardFailure):
                            await self.cog.cog_before_invoke(ctx)
                    self.assertIn(expected, ctx.sent[0]['content'])
                    self.assertFalse(ctx.deferred)
                    self.assertEqual(mode == PREFIX, ctx.message.delete.await_count == 1)

    async def test_error_handler_unwraps_slash_errors(self):
        ctx = self.ctx(SLASH)
        ctx.command = find_command(self.cog, 'send')
        inner = ValueError('boom')
        wrapped = types.SimpleNamespace(original=types.SimpleNamespace(original=inner))
        with no_external_services():
            await self.cog.on_command_error(ctx, wrapped)
        self.assertEqual(f'{self.author.mention}: send failed because:boom', ctx.sent[0]['content'])

    async def test_error_handler_stays_quiet_for_guard_failures(self):
        ctx = self.ctx(PREFIX)
        ctx.command = find_command(self.cog, 'send')
        with no_external_services():
            await self.cog.on_command_error(ctx, GuardFailure('already reported'))
        self.assertEqual([], ctx.sent)


if __name__ == '__main__':
    unittest.main()


class NoMembersIntentTest(unittest.IsolatedAsyncioTestCase):
    """Without the members intent, the members a command is about are fetched into the cache."""

    def setUp(self):
        self.cog = make_cog()
        self.cog.bot.intents = discord.Intents.default()
        self.fetched = {}
        self.guilds = [self.cog.cache.scs, self.cog.cache.overflow_server]
        for guild in self.guilds:
            guild.id = len(self.fetched) + 100
            self.fetched[guild.id] = []
            guild.fetch_member = unittest.mock.AsyncMock(side_effect=self.fetch(guild))
            guild._add_member = unittest.mock.MagicMock()

    def fetch(self, guild):
        def fetch_member(member_id):
            if member_id == 404:
                raise discord.NotFound(unittest.mock.MagicMock(status=404), 'Unknown Member')
            self.fetched[guild.id].append(member_id)
            return mocks.MockMember(id=member_id)
        return fetch_member

    async def test_author_and_members_in_options_are_cached_in_every_server(self):
        ctx = unittest.mock.MagicMock(author=mocks.MockMember(id=1), guild=self.cog.cache.scs)
        ctx.interaction.namespace = [('user', mocks.MockMember(id=2)), ('members', '<@3> <@!444444444444444444>'),
                                     ('team', 'Red'), ('size', 5)]
        await self.cog._cache_command_members(ctx)
        for guild in self.guilds:
            self.assertCountEqual([1, 2, 3, 444444444444444444], self.fetched[guild.id])
            self.assertEqual(4, guild._add_member.call_count)

    async def test_someone_not_in_the_server_is_none(self):
        guild = self.cog.cache.scs
        self.assertIsNone(await self.cog._fresh_member(guild, 404))
        guild._add_member.assert_not_called()
        self.assertEqual(7, (await self.cog._fresh_member(guild, 7)).id)
        guild._add_member.assert_called_once()

    async def test_with_the_intent_the_cache_is_used(self):
        self.cog.bot.intents = discord.Intents.all()
        guild = self.cog.cache.scs
        guild.get_member = unittest.mock.MagicMock(return_value='cached')
        self.assertEqual('cached', await self.cog._fresh_member(guild, 7))
        guild.fetch_member.assert_not_awaited()
