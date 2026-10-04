"""Pins the full command surface of the bot and checks every prefix command has a slash command.

The snapshot lists every command with its parameters, aliases and guards, plus the slash command that
runs it. The prefix half was recorded from the prefix-only bot, so a command that is dropped, renamed
or loses a guard while being converted shows up as a diff here.
"""
import ast
import inspect
import json
import os
import re
import typing
import unittest
import unittest.mock
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

import src.cache
from src import scoreSheetBot
from src.slash import ALLOWED_IN_DMS, CB_COMMANDS, PREFIX_ONLY, STAFF_GROUPS
from tests.harness import assert_snapshot, is_hybrid, make_cog

COMMAND_DECORATORS = ('command', 'group', 'hybrid_command', 'hybrid_group')
# Decorators that describe a command to Discord rather than restrict who can run it.
NON_GUARDS = ('app_commands.', 'commands.cooldown')
OPTION_TYPES = {
    discord.AppCommandOptionType.string: 'str',
    discord.AppCommandOptionType.integer: 'int',
    discord.AppCommandOptionType.user: 'Member',
    discord.AppCommandOptionType.channel: 'TextChannel',
    discord.AppCommandOptionType.role: 'Role',
    discord.AppCommandOptionType.attachment: 'Attachment',
}
PLACEHOLDER = '…'  # what discord.py uses for a missing description


def type_name(annotation) -> str:
    if annotation is inspect.Parameter.empty:
        return 'str'
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [type_name(a) for a in typing.get_args(annotation) if a is not type(None)]
        return ' | '.join(args)
    if isinstance(annotation, commands.Greedy):
        return f'Greedy[{type_name(annotation.converter)}]'
    return getattr(annotation, '__name__', str(annotation))


def guards_by_command() -> Dict[str, List[str]]:
    """Reads the guard decorators of every command from the cog's source, outermost first."""
    with open(os.path.abspath(scoreSheetBot.__file__), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    cog = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ScoreSheetBot')
    names, parents, guards = {}, {}, {}
    for func in cog.body:
        if not isinstance(func, ast.AsyncFunctionDef):
            continue
        func_guards = []
        for decorator in func.decorator_list:
            call = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(call, ast.Attribute) and call.attr in COMMAND_DECORATORS:
                names[func.name] = func.name
                if isinstance(decorator, ast.Call):
                    for keyword in decorator.keywords:
                        if keyword.arg == 'name':
                            names[func.name] = keyword.value.value
                if isinstance(call.value, ast.Name) and call.value.id != 'commands':
                    parents[func.name] = call.value.id
            else:
                source = ast.unparse(decorator)
                if not source.startswith(NON_GUARDS):
                    func_guards.append(source)
        guards[func.name] = func_guards

    def qualified(func_name):
        if func_name in parents:
            return f'{qualified(parents[func_name])} {names[func_name]}'
        return names[func_name]

    return {qualified(func_name): guards[func_name] for func_name in names}


def slash_kind(cog, command) -> str:
    if is_hybrid(command):
        return 'hybrid'
    return 'typed' if command.qualified_name in cog.slash.typed else 'twin'


def slash_options(slash: app_commands.Command) -> List[dict]:
    return [{'name': p.name, 'type': OPTION_TYPES[p.type], 'required': p.required} for p in slash.parameters]


def slash_entry(cog, command):
    slash = cog.slash.by_prefix_name.get(command.qualified_name)
    if slash is None:
        return None
    return {'path': slash.qualified_name, 'kind': slash_kind(cog, command), 'options': slash_options(slash)}


def inventory(cog) -> Dict[str, dict]:
    guards = guards_by_command()
    out = {}
    for command in cog.walk_commands():
        params = []
        for name, param in command.clean_params.items():
            params.append({
                'name': name,
                'type': type_name(param.annotation),
                'required': param.default is inspect.Parameter.empty,
                'rest': param.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL),
            })
        out[command.qualified_name] = {
            'aliases': sorted(command.aliases),
            'category': command.help,
            'guards': guards[command.qualified_name],
            'is_group': isinstance(command, commands.Group),
            'params': params,
            'slash': slash_entry(cog, command),
        }
    return out


def root(slash):
    while slash.parent is not None:
        slash = slash.parent
    return slash


def payload_of(slash) -> dict:
    """What would be sent to Discord for `slash`. Newer discord.py versions need the command tree for this."""
    if 'tree' in inspect.signature(slash.to_dict).parameters:
        bot = commands.Bot(command_prefix=',', intents=discord.Intents.none())
        return slash.to_dict(bot.tree)
    return slash.to_dict()


def text_size(payload: dict) -> int:
    """Characters Discord counts towards a command's size limit: names, descriptions and choice values."""
    size = len(payload['name']) + len(payload['description'])
    for choice in payload.get('choices', []):
        size += len(str(choice['name'])) + len(str(choice['value']))
    return size + sum(text_size(option) for option in payload.get('options', []))


class CommandInventoryTest(unittest.TestCase):
    def setUp(self):
        self.cog = make_cog()
        self.prefix = {command.qualified_name: command for command in self.cog.walk_commands()}
        self.slash = self.cog.slash.by_prefix_name

    def test_command_surface_unchanged(self):
        assert_snapshot(self, 'command_inventory', inventory(self.cog))

    def test_every_prefix_command_has_a_slash_command(self):
        self.assertEqual(set(), PREFIX_ONLY - set(self.prefix), 'PREFIX_ONLY names a command that does not exist')
        self.assertEqual(set(self.prefix) - PREFIX_ONLY, set(self.slash))

    def test_generated_and_hybrid_slash_commands_take_the_same_arguments(self):
        for name, command in self.prefix.items():
            if name not in self.slash or isinstance(command, commands.Group):
                continue
            if slash_kind(self.cog, command) == 'typed':
                continue
            with self.subTest(command=name):
                # An Optional argument without a default is still optional to a prefix command.
                expected = [(n, type_name(p.annotation), p.default is inspect.Parameter.empty
                             and type(None) not in typing.get_args(p.annotation))
                            for n, p in command.clean_params.items()]
                actual = [(o['name'], o['type'], o['required']) for o in slash_options(self.slash[name])]
                self.assertCountEqual(expected, actual)

    def test_staff_commands_are_grouped_and_stay_guarded(self):
        grouped = [name for _, names in STAFF_GROUPS.values() for name in names]
        self.assertEqual(len(grouped), len(set(grouped)), 'a command is in two staff groups')
        guards = guards_by_command()
        for name in grouped:
            with self.subTest(command=name):
                self.assertTrue(any(g.startswith('role_call') for g in guards[name]), 'not a restricted command')
                self.assertTrue(self.slash[name].qualified_name.startswith('staff '))
        for name in set(self.slash) - set(grouped):
            if name.startswith('gamb'):
                continue
            with self.subTest(command=name):
                restricted = [g for g in guards[name] if g.startswith('role_call') and 'LEADER' not in g]
                self.assertEqual([], restricted, 'staff-only command is not under /staff')

    def test_crew_battle_commands_are_under_cb(self):
        self.assertEqual(len(CB_COMMANDS), len(set(CB_COMMANDS)))
        for name in CB_COMMANDS:
            with self.subTest(command=name):
                self.assertEqual(f'cb {name}', self.slash[name].qualified_name)
                self.assertFalse(is_hybrid(self.prefix[name]), 'a hybrid would also register a top level command')
        # Every command in the cb help category is in the group, bar the two character lookups.
        category = {name for name, command in self.prefix.items() if command.help == 'cb'}
        self.assertEqual({'char', 'chars'}, category - set(CB_COMMANDS))
        self.assertEqual(set(), set(CB_COMMANDS) - category)

    def test_every_command_has_its_own_help_text(self):
        """Catches a command decorated with another command's help entry, or with none."""
        seen = {}
        for name, command in self.prefix.items():
            if name in PREFIX_ONLY or name == 'help':
                continue
            with self.subTest(command=name):
                self.assertTrue(command.brief, 'no brief')
                self.assertTrue(command.description, 'no description')
                self.assertNotIn(command.description, seen, f'same help text as {seen.get(command.description)}')
                seen[command.description] = name

    def test_discord_limits(self):
        valid_name = re.compile(r'^[-_a-z0-9]{1,32}$')
        roots = {id(root(slash)): root(slash) for slash in self.slash.values()}
        self.assertLessEqual(len(roots), 100)
        for top in roots.values():
            payload = payload_of(top)
            with self.subTest(command=top.name):
                self.assertLessEqual(text_size(payload), 8000)
                json.dumps(payload)
            if isinstance(top, app_commands.Group):
                for group in [top] + [c for c in top.commands if isinstance(c, app_commands.Group)]:
                    self.assertLessEqual(len(group.commands), 25, group.qualified_name)
        for name, slash in self.slash.items():
            with self.subTest(command=name):
                self.assertRegex(slash.name, valid_name)
                self.assertTrue(1 <= len(slash.description) <= 100, slash.description)
                self.assertNotEqual(PLACEHOLDER, slash.description)
                self.assertLessEqual(len(slash.parameters), 25)
                for option in slash.parameters:
                    self.assertRegex(option.name, valid_name)
                    self.assertTrue(1 <= len(option.description) <= 100, option.name)
                    self.assertNotEqual(PLACEHOLDER, option.description, f'{option.name} has no description')
                required = [o['required'] for o in payload_of(slash).get('options', [])]
                self.assertEqual(sorted(required, reverse=True), required, 'required options must come first')

    def test_commands_are_server_only_except_help(self):
        for name, slash in self.slash.items():
            with self.subTest(command=name):
                self.assertEqual(name not in ALLOWED_IN_DMS, bool(root(slash).guild_only))


class RealBotTest(unittest.IsolatedAsyncioTestCase):
    """Loads the cog into a real, unconnected bot, the way `main` does."""

    async def asyncSetUp(self):
        self.bot = commands.Bot(command_prefix=',', intents=discord.Intents.all(), case_insensitive=True)
        self.bot.remove_command('help')
        self.cog = scoreSheetBot.ScoreSheetBot(self.bot, src.cache.Cache())
        await self.bot.add_cog(self.cog)
        self.cog.auto_cache.cancel()

    def leaves(self, slash, path=''):
        path = f'{path} {slash.name}'.strip()
        if isinstance(slash, app_commands.Group):
            return [leaf for child in slash.commands for leaf in self.leaves(child, path)]
        return [path]

    async def test_every_slash_command_is_registered_in_the_tree(self):
        registered = sorted(leaf for top in self.bot.tree.get_commands() for leaf in self.leaves(top))
        expected = sorted(slash.qualified_name for slash in self.cog.slash.by_prefix_name.values())
        self.assertEqual(expected, registered)
        self.assertLessEqual(len(self.bot.tree.get_commands()), 100)

    async def test_prefix_commands_are_still_registered(self):
        for name in self.cog.slash.by_prefix_name:
            with self.subTest(command=name):
                command = self.bot.get_command(name)
                self.assertIsNotNone(command)
                self.assertIs(command.cog, self.cog)
        self.assertIs(self.bot.get_command('s'), self.bot.get_command('send'), 'aliases still work')

    async def test_slash_bookkeeping_can_be_kept_on_a_real_context(self):
        ctx = commands.Context(message=unittest.mock.MagicMock(), bot=self.bot, view=unittest.mock.MagicMock(),
                               prefix=',')
        ctx.slash_attachments = ['file']
        ctx.slash_replied = True
        ctx.send = unittest.mock.AsyncMock()
        self.assertEqual(['file'], ctx.slash_attachments)

    async def test_unloading_the_cog_removes_its_slash_commands(self):
        await self.bot.remove_cog(self.cog.qualified_name)
        self.assertEqual([], self.bot.tree.get_commands())


if __name__ == '__main__':
    unittest.main()
