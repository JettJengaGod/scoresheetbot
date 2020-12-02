from typing import List, Iterable, Set, Union, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scoreSheetBot import ScoreSheetBot
from fuzzywuzzy import process
import discord
from discord.ext import commands
from .battle import *
import time
from .constants import *
from .crew import Crew

Context = discord.ext.commands.Context


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


def crew(user: discord.Member, bot: 'ScoreSheetBot') -> Optional[str]:
    roles = user.roles
    if any((role.name == OVERFLOW_ROLE for role in roles)):
        overflow_user = bot.cache.overflow_members[user.name]
        roles = overflow_user.roles

    for role in roles:
        if role.name in bot.cache.crews:
            return role.name
    raise ValueError(f'{user.mention} has no crew or something is wrong.')


async def track_cycle(user: discord.Member, scs: discord.Guild) -> int:
    track = -1
    if check_roles(user, [TRUE_LOCKED]):
        return 3
    for i in range(len(TRACK)):
        if check_roles(user, [TRACK[i]]):
            track = i
    if 0 <= track < 2:
        old_track = discord.utils.get(scs.roles, name=TRACK[track])
        await user.remove_roles(old_track, reason='Left a crew, moved up the track.')
    if track < 2:
        new_track = discord.utils.get(scs.roles, name=TRACK[track + 1])
        await user.add_roles(new_track, reason='User left a crew, moved up the track.')
    return track


def power_level(user: discord.Member):
    if check_roles(user, STAFF_LIST):
        return 3
    if check_roles(user, [LEADER]):
        return 2
    if check_roles(user, [ADVISOR]):
        return 1
    return 0


def compare_crew_and_power(author: discord.Member, target: discord.Member, bot: 'ScoreSheetBot') -> None:
    author_crew = crew(author, bot)
    target_crew = crew(target, bot)
    if author_crew is not target_crew:
        raise Exception(f'{author.display_name} on {author_crew} cannot unflair {target.display_name} on {target_crew}')
    author_pl = power_level(author)
    target_pl = power_level(target)
    if author_pl == 3:
        return
    if author_pl == 2:
        if target_pl == author_pl:
            raise Exception(
                f'A majority of leaders must approve this unflairing. Tag the Doc Keeper role for assistance.')
        return

    if author_pl == 1:
        if target_pl >= author_pl:
            raise Exception(
                f'{author.mention} does not have enough power to unflair {target.mention} from {author_crew}.')
        return

    raise Exception('You must be an advisor, leader or staff to unflair people.')


def member_lookup(name: str, bot: 'ScoreSheetBot') -> Optional[discord.Member]:
    if name.startswith('<') and name.endswith('>'):
        id = int(name[3:-1])
        user = bot.cache.scs.get_member(id)
        if user:
            return user
        raise ValueError(f'{name} doesn\'nt seem t obe on this server.')
    true_name = process.extractOne(name, bot.cache.main_members.keys(), score_cutoff=70)
    if true_name:
        return bot.cache.main_members[true_name[0]]
    else:
        raise Exception(f'{name} does not match any member in the server.')


def crew_lookup(crew: str, bot: 'ScoreSheetBot') -> Optional[Crew]:
    true_crew = process.extractOne(crew, bot.cache.crews_by_name.keys(), score_cutoff=70)
    if true_crew:
        return bot.cache.crews_by_name[true_crew[0]]
    else:
        raise Exception(f'{crew} does not match any crew in the server.')


def ambiguous_lookup(name: str, bot: 'ScoreSheetBot') -> Union[discord.Member, Crew]:
    if name.startswith('<') and name.endswith('>'):
        id = int(name[3:-1])
        user = bot.cache.scs.get_member(id)
        if user:
            return user
        raise ValueError(f'{name} doesn\'nt seem t obe on this server.')
    true_name = process.extractOne(name, bot.cache.main_members.keys())
    true_crew = process.extractOne(name, bot.cache.crews_by_name.keys())
    if true_crew[1] >= true_name[1]:
        return bot.cache.crews_by_name[true_crew[0]]
    else:
        return bot.cache.main_members[true_name[0]]


def strip_non_ascii(text: str) -> str:
    encoded_string = text.encode("ascii", "ignore")
    decode_string = encoded_string.decode()
    return decode_string


async def flair(member: discord.Member, flairing_crew: Crew, bot: 'ScoreSheetBot'):
    if check_roles(member, [TRUE_LOCKED]):
        raise ValueError(f'{member.display_name} cannot be flaired because they are {TRUE_LOCKED}.')
    if flairing_crew.overflow:
        await member.add_roles(bot.cache.roles.overflow)
        overflow_crew = discord.utils.get(bot.cache.overflow_server.roles, name=flairing_crew.name)
        overflow_member = discord.utils.get(bot.cache.overflow_server.members, id=member.id)
        await overflow_member.add_roles(overflow_crew)
        await member.edit(nick=f'{flairing_crew.abbr} | {member.name}')
    else:
        main_crew = discord.utils.get(bot.cache.scs.roles, name=flairing_crew.name)
        await member.add_roles(main_crew)
    if check_roles(member, [TRACK[2]]):
        await member.remove_roles(bot.cache.roles.track3)
        await member.add_roles(bot.cache.roles.true_locked)
        pepper = discord.utils.get(bot.cache.scs.members, id=456156481067286529)
        flairing_info = discord.utils.get(bot.cache.scs.channels, name='flairing_info')
        await flairing_info.send(f'{pepper.mention} {member.mention} is {TRUE_LOCKED}.')


async def unflair(member: discord.Member, author: discord.member, bot: 'ScoreSheetBot'):
    user_crew = crew(member, bot)
    if check_roles(member, [bot.cache.roles.overflow.name]):
        user = discord.utils.get(bot.cache.overflow_server.members, id=member.id)
        await member.edit(nick=member.name)
        role = discord.utils.get(bot.cache.overflow_server.roles, name=user_crew)
        overflow_adv = discord.utils.get(bot.cache.overflow_server.roles, name=ADVISOR)
        overflow_leader = discord.utils.get(bot.cache.overflow_server.roles, name=LEADER)
        await user.remove_roles(role, overflow_adv, overflow_leader, reason=f'Unflaired by {author.name}')
        await member.remove_roles(bot.cache.roles.overflow, reason=f'Unflaired by {author.name}')
    else:
        role = discord.utils.get(bot.cache.scs.roles, name=user_crew)
        await member.remove_roles(role, reason=f'Unflaired by {author.name}')
    if await track_cycle(member, bot.cache.scs) == 2:
        pepper = discord.utils.get(bot.cache.scs.members, id=456156481067286529)
        flairing_info = discord.utils.get(bot.cache.scs.channels, name='flairing_info')
        await flairing_info(f'{pepper.mention} {member.mention} is locked on next join.')
    await member.remove_roles(bot.cache.roles.advisor, bot.cache.roles.leader,
                              reason=f'Unflaired by {author.name}')
