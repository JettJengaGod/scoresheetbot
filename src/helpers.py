from typing import List, Iterable, Set, Union, Optional

import time
import discord
from discord.ext import commands
from .battle import *
from .scoreSheetBot import ScoreSheetBot

Context = discord.ext.commands.Context
OVERFLOW_CACHE_TIME = 1_000_000


def key_string(ctx: Context) -> str:
    return str(ctx.guild) + '|' + str(ctx.channel)


def channel_from_key(key: str) -> str:
    return key[key.index("|") + 1:]


def escape(string: str, special: Set[str] = None) -> str:
    if not special:
        special = ['\\', '>', '`', '_', '*', '|']
    out = string[:]
    for char in special:
        if char in out:
            out = out.replace(char, '\\' + char)
    return out


def split_embed(embed: discord.Embed, length: int) -> List[discord.Embed]:
    ret = []
    desc = embed.description
    desc_split = split_on_length_and_separator(desc, length, '\n')
    ret.append(discord.Embed(title=embed.title, color=embed.color, description=desc_split.pop(0)))

    for split in desc_split:
        ret.append(discord.Embed(color=embed.color, description=split))
    return ret


def split_on_length_and_separator(string: str, length: int, separator: str) -> List[str]:
    ret = []
    while len(string) > length:
        idx = length - 1
        while string[idx] != separator:
            if idx == 0:
                raise ValueError
            idx -= 1
        ret.append(string[:idx + 1])
        string = string[idx + 1:]
    ret.append(string)
    return ret


def is_usable_emoji(text: str, bot):
    if text.startswith('<:'):
        text = text[2:]
        if text.endswith('>'):
            text = text[:-1]
        name = text[:text.index(':')]
        emoji_id = text[text.index(':') + 1:]
        return discord.utils.get(bot.emojis, name=name).available
    return False


def check_roles(user: discord.member, roles: Iterable) -> bool:
    return any((role.name in roles for role in user.roles))


async def send_sheet(channel: Union[discord.TextChannel, Context], battle: Battle):
    embed_split = split_embed(embed=battle.embed(), length=2000)
    for embed in embed_split:
        await channel.send(embed=embed)


async def crew(user: discord.Member, bot: ScoreSheetBot) -> Optional[str]:
    roles = user.roles
    if any((role.name == 'SCS Overflow Crew' for role in roles)):
        if not bot.overflow_cache or (time.time_ns() - bot.overflow_updated) > OVERFLOW_CACHE_TIME:
            bot.overflow_cache = await discord.utils.get(bot.bot.guilds, name='SCS Overflow Server').fetch_members(
                limit=None).flatten()
            bot.overflow_updated = time.time_ns()
        overflow_user = discord.utils.get(bot.overflow_cache, id=user.id)
        roles = overflow_user.roles

    for role in roles:
        if role.name in bot.cache.crews():
            return role.name
    raise Exception(f'{user.mention} has no crew or something is wrong.')
