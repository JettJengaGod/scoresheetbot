# scoreSheetBot.py
import os
import sys
import traceback

import discord
import functools
from discord.ext import commands
from dotenv import load_dotenv
from typing import Dict
from src.battle import Battle, Character, StateError
from src.help import help

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')


def has_sheet(func):
    """Decorator that returns if no battle has started."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        battle = self.battle_map.get(str(ctx.guild) + str(ctx.channel))
        if battle is None:
            await ctx.send('Battle is not started.')
            return
        # kwargs['battle'] = battle
        return await func(self, *args, **kwargs)

    return wrapper


class ScoreSheetBot(commands.Cog):
    def __init__(self, bot: commands.bot):
        self.bot = bot
        self.battle_map: Dict[str, Battle] = {}

    def _current(self, ctx) -> Battle:
        return self.battle_map[str(ctx.guild) + str(ctx.channel)]

    def _set_current(self, ctx, battle: Battle):
        self.battle_map[str(ctx.guild) + str(ctx.channel)] = battle

    def _clear_current(self, ctx):
        self.battle_map[str(ctx.guild) + str(ctx.channel)] = None

    @commands.command(**help['start'])
    async def start(self, ctx, team1: str, team2: str, size: int):
        self._set_current(ctx, Battle(team1, team2, size))
        await ctx.send(self._current(ctx))

    @commands.command(**help['add'])
    @has_sheet
    async def add(self, ctx, team: str, player: str, battle=None):
        self._current(ctx).add_player(team, player)
        await ctx.send(self._current(ctx))

    @commands.command(**help['end_game'])
    @has_sheet
    async def end_game(self, ctx, char1: str, stocks1: int, char2: str, stocks2: int):
        self._current(ctx).finish_match(stocks1, stocks2, Character(str(char1)),
                                        Character(str(char2)))
        await ctx.send(self._current(ctx))
        if self._current(ctx).battle_over():
            self._clear_current(ctx)

    @commands.command(**help['resize'])
    @has_sheet
    async def resize(self, ctx, new_size: int):
        self._current(ctx).resize(new_size)
        await ctx.send(self._current(ctx))

    @commands.command(**help['resize'])
    @has_sheet
    async def undo(self, ctx):
        self._current(ctx).undo()
        await ctx.send(self._current(ctx))

    """TESTING COMMANDS DON'T MODIFY """

    @commands.command(**help['start'])
    async def s(self, ctx):
        team1, team2, size = 'a', 'b', 2
        self._set_current(ctx, Battle(team1, team2, size))
        await ctx.send(self._current(ctx))

    @commands.command(**help['add'])
    @has_sheet
    async def a(self, ctx):
        self._current(ctx).add_player('a', 'Player1')
        self._current(ctx).add_player('b', 'Player2')
        await ctx.send(self._current(ctx))

    @commands.command(**help['echo'])
    async def echo(self, ctx, thing):
        print(thing)
        await ctx.send(thing)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.
        Parameters
        ------------
        ctx: commands.Context
            The context used for command invocation.
        error: commands.CommandError
            The Exception raised.
        """

        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return

        # This prevents any cogs with an overwritten cog_command_error being handled here.
        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        ignored = ()

        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)

        # Anything in ignored will return and prevent anything happening.
        # if isinstance(error, ignored):
        #     return

        if isinstance(error, commands.DisabledCommand):
            await ctx.send(f'{ctx.command} has been disabled.')
        elif isinstance(error, commands.CommandNotFound):
            await ctx.author.send(f'{ctx.command} was not found, try "!help" for a list of commands.')

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.author.send(f'{ctx.command} can not be used in Private Messages.')
            except discord.HTTPException:
                pass

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
        elif isinstance(error, StateError):
            await ctx.send(f'"{ctx.command}" did not work because:{error.message}')
        else:
            # All other Errors not returned come here. And we can just print the default TraceBack.
            print(error)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def main():
    bot = commands.Bot(command_prefix='!')
    bot.add_cog(ScoreSheetBot(bot))
    bot.run(TOKEN)


if __name__ == '__main__':
    main()
