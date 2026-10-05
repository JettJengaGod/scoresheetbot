"""Runs every command once as a prefix command and once as a slash command and compares what they send.

The database, Google Sheets and the network are replaced with mocks, so most commands run on made-up
data. That is enough here: the point is that both ways of invoking a command walk the same code and
say the same things, not that the answers are meaningful.
"""
import asyncio
import inspect
import json
import random
import socket
import typing
import unittest
import unittest.mock

import discord
from discord.ext import commands
from freezegun import freeze_time

import src.db_helpers
import src.sheet_helpers
from src.constants import *
from tests import mocks
from tests.harness import MODES, PREFIX, SLASH, FakeContext, _normalize, invoke, make_cog

# Commands the sweep leaves out, and what covers them instead.
SKIPPED = {
    'recache': 'rebuilds the cache from Google; the slash twin is checked by the inventory test',
    'sync': 'talks to Discord; covered in test_slash_front_ends',
    'predict': 'draws bracket images',
    'predictions': 'draws bracket images',
}
MODULES = ('src.scoreSheetBot', 'src.helpers')


def service_functions():
    """Every database and sheet function, by name."""
    names = set()
    for module in (src.db_helpers, src.sheet_helpers):
        for name, value in vars(module).items():
            if inspect.isfunction(value) and value.__module__ == module.__name__:
                names.add(name)
    return names


class ParitySweepTest(unittest.IsolatedAsyncioTestCase):
    def build(self, mode):
        """A fresh cog with a battle running, and a staff member who also leads one of the crews."""
        cog = make_cog(every_slash_command=True)
        guild = cog.cache.scs
        channel = mocks.MockTextChannel(name='⚔-gambit-bot-commands', id=555, guild=guild)
        roles = [mocks.hk_role, mocks.leader, mocks.admin, mocks.MockRole(name=VERIFIED)]
        author = mocks.MockMember(name='author', id=11, display_name='Author', roles=roles)
        other = mocks.MockMember(name='other', id=21, display_name='Other',
                                 roles=[mocks.fsg_role, mocks.leader, mocks.MockRole(name=VERIFIED)])
        guild.members = [author, other]
        return cog, FakeContext(cog, author, channel, guild, mode), other

    def argument(self, parameter: inspect.Parameter, ctx, other):
        annotation = parameter.annotation
        options = [a for a in typing.get_args(annotation) if a is not type(None)] or [annotation]
        if discord.Member in options:
            return other
        if discord.TextChannel in options:
            return ctx.channel
        if int in options:
            return 3
        return 'HK'

    async def run_command(self, name, mode, with_battle):
        random.seed(0)
        cog, ctx, other = self.build(mode)
        patched = {function: unittest.mock.MagicMock(name=function) for function in service_functions()}
        answers = dict(wait_for_reaction_on_message=unittest.mock.AsyncMock(return_value=True),
                       wait_choice=unittest.mock.AsyncMock(return_value=0))
        with unittest.mock.patch.multiple('src.scoreSheetBot', create=True, sleep=unittest.mock.AsyncMock(),
                                          **{**patched, **answers}), \
                unittest.mock.patch.multiple('src.helpers', create=True, **{**patched, **answers}), \
                unittest.mock.patch.object(cog, '_cache_process', unittest.mock.AsyncMock()), \
                unittest.mock.patch.object(socket.socket, 'connect', side_effect=OSError('no network in tests')):
            if with_battle:
                await invoke(cog, 'mock', FakeContext(cog, ctx.author, ctx.channel, ctx.guild, PREFIX),
                             'Holy Knights', 'FSGood', 2)
            command = cog.bot.get_command(name)
            arguments = [self.argument(p, ctx, other) for p in command.clean_params.values()
                         if p.kind is not inspect.Parameter.KEYWORD_ONLY]
            keywords = {n: self.argument(p, ctx, other) for n, p in command.clean_params.items()
                        if p.kind is inspect.Parameter.KEYWORD_ONLY}
            await asyncio.wait_for(invoke(cog, name, ctx, *arguments, **keywords), timeout=10)
        sent = _normalize(json.loads(json.dumps(ctx.sent, default=str)))
        if mode == SLASH and sent and sent[-1] == {'content': 'Done.', 'embed': None}:
            sent = sent[:-1]  # only a slash command has to say something when it has nothing to say
        return sent

    @freeze_time('2026-01-15 12:00:00')
    async def test_every_command_sends_the_same_in_both_modes(self):
        cog = make_cog(every_slash_command=True)
        swept = 0
        for name in sorted(cog.slash.by_prefix_name):
            if name in SKIPPED or name in cog.slash.typed:
                continue  # typed front ends take different arguments; test_slash_front_ends covers them
            for with_battle in (False, True):
                with self.subTest(command=name, with_battle=with_battle):
                    prefix = await self.run_command(name, PREFIX, with_battle)
                    slash = await self.run_command(name, SLASH, with_battle)
                    self.assertEqual(prefix, slash)
                    swept += 1
        self.assertGreater(swept, 190)

    def test_skips_are_real_commands(self):
        self.assertEqual(set(), set(SKIPPED) - set(make_cog(every_slash_command=True).slash.by_prefix_name))


if __name__ == '__main__':
    unittest.main()
