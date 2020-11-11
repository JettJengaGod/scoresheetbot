# scoreSheetBot.py
import os
import sys
import traceback

import discord
import functools
from discord.ext import commands
from dotenv import load_dotenv
from typing import Dict, Optional, Union
from src.battle import Battle, Character, StateError
from src.help import help
from src.character import string_to_emote, all_emojis, string_to_emote2
from src.helpers import split_on_length_and_separator, is_usable_emoji
import src.roles

Context = discord.ext.commands.context

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
cache = src.roles.CrewCache()


def ss_channel(func):
    """Decorator that errors if not in the correct channel."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        if 'scoresheet_bot' not in ctx.channel.name:
            await ctx.send('Cannot use this bot in this channel, try a scoresheet_bot channel.')
            return
        return await func(self, *args, **kwargs)

    return wrapper


def has_sheet(func):
    """Decorator that errors if no battle has started."""

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


def no_battle(func):
    """Decorator that errors if no battle has started."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        battle = self.battle_map.get(str(ctx.guild) + str(ctx.channel))
        if battle is not None:
            await ctx.send('A battle is already going in this channel.')
            return
        # kwargs['battle'] = battle
        return await func(self, *args, **kwargs)

    return wrapper


def is_lead(func):
    """Decorator that ensures caller is leader, or advisor."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        user = ctx.author
        if not (any(role.name in ['Leader', 'Advisor', 'SCS Admin', 'v2 Minion'] for role in user.roles)):
            await ctx.send('Only a a leader or advisor or admin can run this command.')
            return
        return await func(self, *args, **kwargs)

    return wrapper


def crew(user: discord.Member) -> str:
    for role in user.roles:
        if role.name in cache.crews():
            return role.name
    return None


class ScoreSheetBot(commands.Cog):
    def __init__(self, bot: commands.bot):
        self.bot = bot
        self.battle_map: Dict[str, Battle] = {}

    def _current(self, ctx) -> Battle:
        return self.battle_map[str(ctx.guild) + str(ctx.channel)]

    def _battle_crew(self, ctx: Context, user: discord.member) -> Optional[str]:
        for role in user.roles:
            if role.name in (self._current(ctx).team1.name, self._current(ctx).team2.name):
                return role.name
        return None

    def _reject_outsiders(self, ctx: Context):
        if not self._battle_crew(ctx, ctx.author):
            raise Exception('You are not in this battle, stop trying to mess with it.')

    def _set_current(self, ctx: Context, battle: Battle):
        self.battle_map[str(ctx.guild) + str(ctx.channel)] = battle

    def _clear_current(self, ctx):
        self.battle_map[str(ctx.guild) + str(ctx.channel)] = None

    @commands.command(**help['battle'])
    @no_battle
    @is_lead
    @ss_channel
    async def battle(self, ctx: Context, user: discord.Member, size: int):
        user_crew = crew(ctx.author)
        opp_crew = crew(user)
        if not user_crew:
            await ctx.send(f'{ctx.author.name}\'s crew didn\'t show up correctly. '
                           f'They might be in an overflow crew or no crew. '
                           f'Please contact an admin if this is incorrect.')
            return
        if not opp_crew:
            await ctx.send(f'{user.name}\'s crew didn\'t show up correctly. '
                           f'They might be in an overflow crew or no crew. '
                           f'Please contact an admin if this is incorrect.')
            return
        if crew(ctx.author) != crew(user):
            self._set_current(ctx, Battle(crew(ctx.author), crew(user), size))
            await ctx.send(embed=self._current(ctx).embed())
        else:
            await ctx.send('You can\'t battle your own crew')

    @commands.command(**help['send'])
    @has_sheet
    @ss_channel
    @is_lead
    async def send(self, ctx: Context, user: discord.Member):
        self._reject_outsiders(ctx)
        current_crew = self._battle_crew(ctx, ctx.author)
        if current_crew == self._battle_crew(ctx, user):
            self._current(ctx).add_player(self._battle_crew(ctx, ctx.author), user.display_name)
            await ctx.send(embed=self._current(ctx).embed())
        else:
            await ctx.send(f'{user.display_name} is not on {current_crew} please choose someone else.')

    @commands.command(**help['replace'])
    @has_sheet
    @ss_channel
    @is_lead
    async def replace(self, ctx: Context, user: discord.Member):
        self._reject_outsiders(ctx)
        current_crew = self._battle_crew(ctx, ctx.author)
        if current_crew == self._battle_crew(ctx, user):
            self._current(ctx).replace_player(self._battle_crew(ctx, ctx.author), user.display_name)
            await ctx.send(embed=self._current(ctx).embed())
        else:
            await ctx.send(f'{user.display_name} is not on {current_crew}, please choose someone else.')

    @commands.command(**help['end'])
    @has_sheet
    @ss_channel
    async def end(self, ctx: Context, char1: Union[str, discord.Emoji], stocks1: int, char2: Union[str, discord.Emoji],
                  stocks2: int):
        self._reject_outsiders(ctx)

        self._current(ctx).finish_match(stocks1, stocks2,
                                        Character(str(char1), self.bot, is_usable_emoji(char1, self.bot)),
                                        Character(str(char2), self.bot, is_usable_emoji(char2, self.bot)))
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help['resize'])
    @is_lead
    @has_sheet
    @ss_channel
    async def resize(self, ctx: Context, new_size: int):
        self._reject_outsiders(ctx)
        self._current(ctx).resize(new_size)
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help['undo'])
    @has_sheet
    @ss_channel
    @is_lead
    async def undo(self, ctx):
        self._reject_outsiders(ctx)
        self._current(ctx).undo()
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help['confirm'])
    @has_sheet
    @ss_channel
    @is_lead
    async def confirm(self, ctx):
        self._reject_outsiders(ctx)

        if self._current(ctx).battle_over():
            self._current(ctx).confirm(self._battle_crew(ctx, ctx.author))
            await ctx.send(embed=self._current(ctx).embed())
            if self._current(ctx).confirmed():
                await ctx.send('The battle has been confirmed by both sides.')
                self._clear_current(ctx)
        else:
            ctx.send('The battle is not over yet, wait till then to confirm.')

    @commands.command(**help['clear'])
    @has_sheet
    @ss_channel
    @is_lead
    async def clear(self, ctx):
        if not any(role.name in ['Leader', 'Advisor'] for role in ctx.author.roles):
            self._reject_outsiders(ctx)
        self._clear_current(ctx)
        await ctx.send('Cleared the crew battle.')

    @commands.command(**help['status'])
    @has_sheet
    @ss_channel
    async def status(self, ctx):
        await ctx.send(embed=self._current(ctx).embed())

    """TESTING COMMANDS DON'T MODIFY """

    @commands.command(**help['char'])
    @ss_channel
    async def char(self, ctx: Context, emoji):
        if is_usable_emoji(emoji, self.bot):
            await ctx.send(emoji)
        else:
            await ctx.send(string_to_emote2(emoji, self.bot))

    @commands.command(**help['crew'])
    @ss_channel
    async def crew(self, ctx):
        await ctx.send(crew(ctx.author))

    @commands.command(**help['char'])
    @ss_channel
    async def who(self, ctx: Context, user: discord.Member):

        await ctx.send(crew(user))

    @commands.command(**help['chars'])
    @ss_channel
    async def chars(self, ctx):
        emojis = all_emojis()
        out = []
        for emoji in emojis:
            out.append(f'{emoji[0]}: {emoji[1]}\n')

        out = "".join(out)
        out = split_on_length_and_separator(out, 1999, ']')
        for split in out:
            await ctx.send(embed=discord.Embed(description=split))

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error):
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
            await ctx.send(f'{str(error)}, try "!help" for a list of commands.')

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.send(f'{ctx.command} can not be used in Private Messages.')
            except discord.HTTPException:
                pass

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
        elif isinstance(error, StateError):
            await ctx.send(f'"{ctx.command}" did not work because:{error.message}')
        else:
            # All other Errors not returned come here. And we can just print the default TraceBack.
            await ctx.send(str(error))
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def main():
    bot = commands.Bot(command_prefix=',')
    bot.add_cog(ScoreSheetBot(bot))
    bot.run(TOKEN)


if __name__ == '__main__':
    main()
