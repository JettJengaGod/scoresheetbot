import functools
from typing import Iterable
from helpers import *


def ss_channel(func):
    """Decorator that errors if not in the correct channel."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        if 'ultimate_cb' not in ctx.channel.name and 'scoresheet_bot' not in ctx.channel.name:
            await ctx.send('Cannot use this bot in this channel, try a scoresheet_bot channel.')
            return
        return await func(self, *args, **kwargs)

    return wrapper


def testing_only(func):
    """Decorator that errors if not in the correct channel."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        if 'testing_grounds' not in ctx.channel.name:
            await ctx.send('This is a testing only command. You can only run it in a testing_grounds channel.')
            return
        return await func(self, *args, **kwargs)

    return wrapper


def has_sheet(func):
    """Decorator that errors if no battle has started."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        battle = self.battle_map.get(str(ctx.guild) + '|' + str(ctx.channel))
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
        battle = self.battle_map.get(str(ctx.guild) + '|' + str(ctx.channel))
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

        battle = self.battle_map.get(str(ctx.guild) + '|' + str(ctx.channel))
        mock = False
        if battle and battle.mock:
            mock = True
        if not mock:
            user = ctx.author
            if not (any(role.name in ['Leader', 'Advisor', 'SCS Admin', 'v2 Minion'] for role in user.roles)):
                await ctx.send('Only a leader or advisor or admin can run this command.')
                return
        return await func(self, *args, **kwargs)

    return wrapper


def role_call(required: Iterable):
    """Decorator that checks if someone is in a roles list."""

    def wrapper(func):
        @functools.wraps(func)
        async def wrapped_f(self, *args, **kwargs):
            ctx = args[0]
            if not check_roles(ctx.author, required):
                await ctx.send(f'You need to be one of {required} to run this command')
                return
            return await func(self, *args, **kwargs)

        return wrapped_f

    return wrapper


def cache_update(func):
    """Decorator that updates cache regularly."""

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        ctx = args[0]
        self.cache.update(self)
        return await func(self, *args, **kwargs)

    return wrapper
