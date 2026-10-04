"""Pins the full command surface of the bot.

The snapshot lists every command with its parameters, aliases and guards. It was recorded from the
prefix-only bot, so a command that is dropped, renamed or loses a guard while being converted to a
slash command shows up as a diff here.
"""
import ast
import inspect
import os
import typing
import unittest
from typing import Dict, List

from discord.ext import commands

from src import scoreSheetBot
from tests.harness import assert_snapshot, make_cog

COMMAND_DECORATORS = ('command', 'group', 'hybrid_command', 'hybrid_group')
# Decorators that describe a command to Discord rather than restrict who can run it.
NON_GUARDS = ('app_commands.', 'commands.cooldown')


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
        }
    return out


class CommandInventoryTest(unittest.TestCase):
    def test_prefix_commands_unchanged(self):
        assert_snapshot(self, 'command_inventory', inventory(make_cog()))


if __name__ == '__main__':
    unittest.main()
