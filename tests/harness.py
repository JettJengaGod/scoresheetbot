"""Helpers for driving bot commands in tests without a Discord connection.

`invoke` runs a command the way discord.py would (checks, cog hooks, callback, error handler)
against a `FakeContext` that records everything the command sends. The same script can be run in
prefix mode and in slash mode, which is how functional parity between the two is asserted.
"""
import contextlib
import inspect
import json
import os
import re
import unittest.mock
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands

from src.scoreSheetBot import ScoreSheetBot
from tests import mocks

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
UPDATE_SNAPSHOTS = bool(os.getenv('UPDATE_SNAPSHOTS'))

PREFIX = 'prefix'
SLASH = 'slash'
MODES = (PREFIX, SLASH)


class FakeMessage:
    """Stands in for both the invoking message and messages the bot sends."""
    _ids = iter(range(1000, 10 ** 9))

    def __init__(self, content: Optional[str] = None, embed: Optional[discord.Embed] = None, attachments=(),
                 author=None):
        self.id = next(self._ids)
        self.content = content
        self.embeds = [embed] if embed else []
        self.attachments = list(attachments)
        self.author = author
        self.mentions = []
        self.delete = unittest.mock.AsyncMock()
        self.add_reaction = unittest.mock.AsyncMock()
        self.clear_reactions = unittest.mock.AsyncMock()
        self.edit = unittest.mock.AsyncMock()
        self.pin = unittest.mock.AsyncMock()


class FakeContext:
    """A recording replacement for `commands.Context`.

    In slash mode `interaction` is set, which is what the bot's helpers key off to decide whether
    there is an invoking message to delete or whether a reply can be ephemeral.
    """

    def __init__(self, cog: ScoreSheetBot, author, channel, guild, mode: str = PREFIX, attachments=()):
        self.cog = cog
        self.bot = cog.bot
        self.author = author
        self.channel = channel
        self.guild = guild
        self.mode = mode
        self.message = FakeMessage(author=author, attachments=attachments)
        self.interaction = unittest.mock.MagicMock(name='interaction') if mode == SLASH else None
        self.command = None
        self.invoked_subcommand = None
        self.prefix = ','
        self.sent: List[Dict[str, Any]] = []
        self.deferred = False

    async def send(self, content=None, *, embed=None, ephemeral=False, **kwargs) -> FakeMessage:
        self.sent.append({'content': content, 'embed': embed.to_dict() if embed else None})
        return FakeMessage(content, embed, author=self.bot.user)

    async def defer(self, *, ephemeral=False):
        self.deferred = True

    async def invoke(self, command, *args, **kwargs):
        return await command.callback(self.cog, self, *args, **kwargs)

    @property
    def me(self):
        return self.guild.me


def make_cog() -> ScoreSheetBot:
    """A real ScoreSheetBot cog wired to a mock bot and the mock cache."""
    cache = mocks.cache()
    cache.scs.name = mocks.SCS
    bot = mocks.MockBot()
    bot.emojis = []
    bot.guilds = [cache.scs, cache.overflow_server]
    bot.command_prefix = ','
    cog = ScoreSheetBot(bot, cache)
    return cog


def find_command(cog: ScoreSheetBot, name: str) -> commands.Command:
    for command in cog.walk_commands():
        if command.qualified_name == name:
            return command
    raise KeyError(name)


@contextlib.contextmanager
def no_external_services():
    """Patches the DB lookups the cog hooks make on every command and silences error logging."""
    with unittest.mock.patch.multiple(
            'src.scoreSheetBot',
            disabled_channels=lambda: [],
            command_lookup=lambda name: (name, False),
            open=unittest.mock.mock_open(),
            create=True), \
            unittest.mock.patch('src.scoreSheetBot.traceback.print_exception'):
        yield


async def invoke(cog: ScoreSheetBot, name: str, ctx: FakeContext, *args, **kwargs) -> None:
    """Runs command `name` in discord.py's order: checks, before hook, callback; errors go to the handler."""
    command = find_command(cog, name)
    ctx.command = command
    with no_external_services():
        try:
            for check in command.checks:
                passed = check(ctx)
                if inspect.isawaitable(passed):
                    passed = await passed
                if not passed:
                    raise commands.CheckFailure(f'The check functions for command {name} failed.')
            await cog.cog_before_invoke(ctx)
            await command.callback(cog, ctx, *args, **kwargs)
        except Exception as error:  # the bot reports every failure to the channel through this handler
            await cog.on_command_error(ctx, error)


def _normalize(value):
    """Removes run-to-run noise: random battle colours and the memory addresses in mock reprs."""
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items() if k != 'color'}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, str):
        return re.sub(r" id='\d+'>", '>', value)
    return value


def assert_snapshot(test: 'unittest.TestCase', name: str, actual) -> None:
    """Compares `actual` with tests/data/<name>.json; set UPDATE_SNAPSHOTS=1 to (re)record it."""
    path = os.path.join(DATA_DIR, f'{name}.json')
    actual = _normalize(json.loads(json.dumps(actual, default=str)))
    if UPDATE_SNAPSHOTS or not os.path.exists(path):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(actual, f, indent=1, ensure_ascii=False, sort_keys=True)
            f.write('\n')
        if not UPDATE_SNAPSHOTS:
            test.fail(f'Snapshot {name}.json did not exist and was recorded; review it and re-run.')
        return
    with open(path, encoding='utf-8') as f:
        expected = json.load(f)
    test.maxDiff = None
    test.assertEqual(expected, actual)
