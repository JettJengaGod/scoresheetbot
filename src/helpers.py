from typing import List, Iterable, Set, Union, Optional

import discord
from discord.ext import commands
from .battle import *
from .scoreSheetBot import ScoreSheetBot
import time

Context = discord.ext.commands.Context
from .constants import *


def key_string(ctx: Context) -> str:
    return str(ctx.guild) + '|' + str(ctx.channel)


def channel_from_key(key: str) -> str:
    return key[key.index("|") + 1:]


def escape(string: str) -> str:
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
        emoji = discord.utils.get(bot.emojis, name=name)
        if emoji:
            return emoji.available
    return False


def check_roles(user: discord.Member, roles: Iterable) -> bool:
    return any((role.name in roles for role in user.roles))


async def send_sheet(channel: Union[discord.TextChannel, Context], battle: Battle):
    embed_split = split_embed(embed=battle.embed(), length=2000)
    for embed in embed_split:
        await channel.send(embed=embed)


def crew(user: discord.Member, bot: ScoreSheetBot) -> Optional[str]:
    roles = user.roles
    if any((role.name == OVERFLOW_ROLE for role in roles)):
        if not bot.overflow_cache or (time.time_ns() - bot.overflow_updated) > OVERFLOW_CACHE_TIME:
            bot.overflow_cache = discord.utils.get(bot.bot.guilds, name=OVERFLOW_SERVER).members
            bot.overflow_updated = time.time_ns()
        overflow_user = discord.utils.get(bot.overflow_cache, id=user.id)
        roles = overflow_user.roles

    for role in roles:
        if role.name in bot.cache.crews():
            return role.name
    raise Exception(f'{user.mention} has no crew or something is wrong.')


async def track_cycle(user: discord.Member, scs: discord.Guild) -> int:
    track = -1
    for i in range(len(TRACK)):
        if check_roles(user, [TRACK[i]]):
            track = i
    if track >= 0:
        old_track = discord.utils.get(scs.roles, name=TRACK[track])
        await user.remove_roles(old_track, reason='Left a crew, moved up the track.')
    if track < 2:
        new_track = discord.utils.get(scs.roles, name=TRACK[track + 1])
        await user.add_roles(new_track, reason='User left a crew, moved up the track.')
    return track


def compare_crew_and_power(author: discord.Member, target: discord.Member, bot: 'ScoreSheetBot'):
    author_crew = crew(author, bot)
    target_crew = crew(target, bot)
    if author_crew is not target_crew:
        raise Exception(f'{author.display_name} on {author_crew} cannot unflair {target.display_name} on {target_crew}')

    if check_roles(author, [LEADER]):
        if check_roles(target, [LEADER]):
            raise Exception(
                f'A majority of leaders must approve this unflairing. Tag the Doc Keeper role for assistance.')
        return

    if check_roles(author, [ADVISOR]):
        if check_roles(target, [LEADER, ADVISOR]):
            raise Exception(
                f'{author.mention} does not have enough power to unflair {target.mention} from {author_crew}.')
        return

    raise Exception('You must be an advisor, leader or staff to unflair people.')
