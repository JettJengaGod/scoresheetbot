from typing import Iterable
from helpers import *


class GuardFailure(commands.CheckFailure):
    """A guard refused to run the command and has already told the user why."""


async def refuse(ctx: Context, message: str):
    """Tells the user why a command was refused (privately for a slash command) and stops it."""
    await ctx.send(message, ephemeral=True)
    raise GuardFailure(message)


def guard(predicate):
    """Makes a decorator out of `predicate(ctx)`, which runs before the command for prefix and slash alike.

    Guards run in the order they are written above a command, top first. They are kept in their own list
    behind a single check because discord.py reverses a command's check list each time its cog is created.
    """

    def decorator(func):
        if not hasattr(func, '__guards__'):
            func.__guards__ = []

            async def run_guards(ctx: Context) -> bool:
                for each in func.__guards__:
                    await each(ctx)
                return True

            commands.check(run_guards)(func)
        func.__guards__.insert(0, predicate)
        return func

    return decorator


@guard
async def ss_channel(ctx: Context):
    """Errors if not in the correct channel."""
    if '⚔' not in ctx.channel.name:
        await refuse(ctx, 'Cannot use this bot in this channel, try a channel with `⚔` in the channel name.')


@guard
async def gambit_channel(ctx: Context):
    """Errors if not in the correct channel."""
    if 'gambit-bot-commands' not in ctx.channel.name:
        await refuse(ctx, f'Please use gambit commands in <#{GAMBIT_BOT_ID}>.')


@guard
async def main_only(ctx: Context):
    """Errors if not in the main server."""
    if SCS not in ctx.guild.name:
        await refuse(ctx, 'This command can only be used in the main SCS Server.')


@guard
async def testing_only(ctx: Context):
    """Errors if not in the correct channel."""
    if 'testing_grounds' not in ctx.channel.name:
        await refuse(ctx, 'This is a testing only command. You can only run it in a testing_grounds channel.')


@guard
async def has_sheet(ctx: Context):
    """Errors if no battle has started."""
    if ctx.cog.battle_map.get(key_string(ctx)) is None:
        await refuse(ctx, 'Battle is not started.')


@guard
async def no_battle(ctx: Context):
    """Errors if a battle has already started."""
    if ctx.cog.battle_map.get(key_string(ctx)) is not None:
        await refuse(ctx, 'A battle is already going in this channel.')


@guard
async def is_lead(ctx: Context):
    """Ensures caller is leader, or advisor."""
    battle = ctx.cog.battle_map.get(key_string(ctx))
    if battle and battle.battle_type in (BattleType.MOCK, BattleType.REG):
        return
    if not (any(role.name in ['Leader', 'Advisor', 'SCS Admin', 'v2 Minion'] for role in ctx.author.roles)):
        await refuse(ctx, 'Only a leader or advisor or admin can run this command.')


def role_call(required: Iterable):
    """Checks if someone is in a roles list."""

    @guard
    async def predicate(ctx: Context):
        if not check_roles(ctx.author, required):
            message = f'You need to be one of {required} to run {ctx.command.name}'
            await response_message(ctx, message)
            raise GuardFailure(message)

    return predicate


def banned_channels(disallowed: Iterable):
    """Checks the command is not being used in one of the given channels."""

    @guard
    async def predicate(ctx: Context):
        if ctx.channel.name in disallowed:
            text = f'{ctx.command.name} is banned in this channel.'
            message = await response_message(ctx, text)
            await message.delete(delay=5)
            raise GuardFailure(text)

    return predicate


@guard
async def flairing_required(ctx: Context):
    """Errors outside the flairing channel for non staff, or while flairing is disabled."""
    if not (check_roles(ctx.author, STAFF_LIST)):
        if ctx.channel.name != FLAIRING_CHANNEL_NAME:
            flairing_channel = discord.utils.get(ctx.guild.channels, name=FLAIRING_CHANNEL_NAME)
            await refuse(ctx, f'Flairing commands can only be used in {flairing_channel.mention}.')
    if not ctx.cog.cache.flairing_allowed:
        await refuse(ctx, f'Flaring is currently disabled, please wait for a mod to re-enable it.')
