import os
from datetime import date, timedelta
from typing import List, Iterable, Set, Union, Optional, TYPE_CHECKING, TextIO, Tuple, Dict, Sequence, ValuesView

import matplotlib.pyplot as plt

plt.rcdefaults()
import numpy as np
from dateutil.relativedelta import relativedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from character import string_to_emote
from db_helpers import add_member_and_crew, crew_correct, all_crews, update_crew, cooldown_finished, \
    remove_expired_cooldown, cooldown_current, find_member_crew, new_crew, auto_unfreeze, new_member_gcoins, \
    current_gambit, member_bet, member_gcoins, make_bet, slots, all_member_roles, update_member_crew, \
    remove_member_role, mod_slot, record_unflair, add_member_role, ba_standings, player_stocks, player_record, \
    player_mvps, player_chars, ba_record, ba_elo, ba_chars, db_crew_members, crew_rankings, disband_crew_from_id, \
    battle_frontier_crews, elo_decay, reset_decay, first_crew_flair, track_finished_out, track_down_out, track_finished
from gambit import Gambit
from sheet_helpers import update_all_sheets

if TYPE_CHECKING:
    from scoreSheetBot import ScoreSheetBot
from fuzzywuzzy import process, fuzz
import asyncio
import discord
from statistics import stdev
from discord.ext import commands, menus
from battle import *
import time
from constants import *
from crew import Crew

Context = discord.ext.commands.Context


def key_string(ctx: Context) -> str:
    return str(ctx.guild) + '|' + str(ctx.channel.id)


def channel_id_from_key(key: str) -> int:
    return int(key[key.index("|") + 1:])


async def update_channel_open(prefix: str, channel: discord.TextChannel):
    if channel.name.startswith(YES) or channel.name.startswith(NO):
        new_name = prefix + channel.name[1:]
    else:
        new_name = prefix + channel.name
    try:
        await asyncio.wait_for(channel.edit(name=new_name), timeout=2)
    except asyncio.TimeoutError:
        return


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
    total_fields = len(embed.fields)
    if len(ret) <= total_fields // 25:
        ret.append(discord.Embed(colour=embed.colour))
    for i, split in enumerate(ret):
        top = min(total_fields, (i + 1) * 25)
        if i * 25 < total_fields:
            for f in embed.fields[i * 25:top]:
                split.add_field(name=f.name, value=f.value, inline=f.inline)

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


async def send_long(ctx: Context, message: str, sep: str):
    output = split_on_length_and_separator(message, length=2000, separator=sep)
    for put in output:
        await ctx.send(put)


async def send_long_embed(ctx: Context, message: discord.Embed):
    output = split_embed(message, length=2000)
    for put in output:
        await ctx.send(embed=put)


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


async def send_sheet(channel: Union[discord.TextChannel, Context], battle: Battle) -> discord.Message:
    embed_split = split_embed(embed=battle.embed(), length=2000)
    if battle.battle_over():
        if not all(battle.confirms):
            footer = ''
            footer += '\nPlease confirm: '
            if battle.battle_type == BattleType.MOCK:
                footer += 'anyone can confirm or clear a mock.'
            else:
                if not battle.confirms[0]:
                    footer += f'\n {battle.team1.name}: '
                    for leader in battle.team1.leader:
                        footer += f'{leader}, '
                    footer = footer[:-2]
                    footer += ' please `,confirm`.'
                if not battle.confirms[1]:
                    footer += f'\n {battle.team2.name}: '
                    for leader in battle.team2.leader:
                        footer += f'{leader}, '
                    footer = footer[:-2]
                    footer += ' please `,confirm`.'
            await channel.send(footer)
    first = None
    for embed in embed_split:
        if not first:
            first = await channel.send(embed=embed)
        else:
            await channel.send(embed=embed)
    return first


def crew(user: discord.Member, bot: 'ScoreSheetBot') -> Optional[str]:
    roles = user.roles
    if any((role.name == OVERFLOW_ROLE for role in roles)):
        overflow_user = discord.utils.get(bot.bot.guilds, name=OVERFLOW_SERVER).get_member(user.id)
        if overflow_user:
            roles = overflow_user.roles

    for role in roles:
        if role.name in bot.cache.crews:
            return role.name
    raise ValueError(f'{str(user)} has no crew or something is wrong.')


def crew_or_none(user: discord.Member, bot: 'ScoreSheetBot') -> Optional[str]:
    try:
        ret = crew(user, bot)
    except ValueError:
        ret = None
    return ret


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
    return track + 1


def power_level(user: discord.Member):
    if check_roles(user, STAFF_LIST):
        return 3
    if check_roles(user, [LEADER]):
        return 2
    if check_roles(user, [ADVISOR]):
        return 1
    return 0


def compare_crew_and_power(author: discord.Member, target: discord.Member, bot: 'ScoreSheetBot') -> None:
    author_pl = power_level(author)
    if author_pl == 3:
        return
    author_crew = crew(author, bot)
    target_crew = crew(target, bot)
    if author_crew is not target_crew:
        raise ValueError(
            f'{author.display_name} on {author_crew} cannot unflair {target.display_name} on {target_crew}')
    target_pl = power_level(target)
    if author_pl == 2:
        if check_roles(target, [LEADER]):
            raise ValueError(
                f'A majority of leaders must approve unflairing leader {target.mention}.'
                f' Tag the Doc Keeper role in {bot.cache.channels.flairing_questions} for assistance.')
        return

    if author_pl == 1:
        if target_pl >= author_pl:
            raise ValueError(
                f' cannot unflair {target.mention} as you are not powerful enough.')
        return

    raise ValueError('You must be an advisor, leader or staff to unflair others.')


def user_by_id(name: str, bot: 'ScoreSheetBot') -> discord.Member:
    if len(name) < 17:
        raise ValueError(f'{name} is not a mention or an id. Try again.')
    try:
        id = int(name.strip("<!@>"))
    except ValueError:
        raise ValueError(f'{name} is not a mention or an id. Try again.')
    user = bot.cache.scs.get_member(id)
    if user:
        return user
    raise ValueError(f'{name} doesn\'t seem to be on this server or your input is malformed. Try @user.')


def member_lookup(name: str, bot: 'ScoreSheetBot') -> Optional[discord.Member]:
    if len(name) >= 17:
        if (name.startswith('<') and name.endswith('>')) or name.isdigit():
            return user_by_id(name, bot)
    true_name = process.extractOne(name, bot.cache.main_members.keys(), scorer=fuzz.ratio, score_cutoff=30)
    if true_name:
        return bot.cache.main_members[true_name[0]]
    else:
        raise ValueError(f'{name} does not match any member in the server.')


def crew_lookup(crew_str: str, bot: 'ScoreSheetBot') -> Optional[Crew]:
    if crew_str.lower() in bot.cache.crews_by_tag:
        return bot.cache.crews_by_tag[crew_str.lower()]
    true_crew = process.extractOne(crew_str, bot.cache.crews_by_name.keys(), score_cutoff=40)
    if true_crew:
        return bot.cache.crews_by_name[true_crew[0]]
    else:
        raise ValueError(f'{crew_str} does not match any crew in the server.')


def ambiguous_lookup(name: str, bot: 'ScoreSheetBot') -> Union[discord.Member, Crew]:
    if name.lower() in bot.cache.crews_by_tag:
        return bot.cache.crews_by_tag[name.lower()]
    if len(name) >= 17:
        if (name.startswith('<') and name.endswith('>')) or name.isdigit():
            return user_by_id(name, bot)

    true_name = process.extractOne(name, bot.cache.main_members.keys(), scorer=fuzz.ratio)
    true_crew = process.extractOne(name, bot.cache.crews_by_name.keys(), scorer=fuzz.ratio)
    if not true_crew:
        if not true_name:
            raise ValueError(f'{name} didn\'t match a crew or a name')
        return bot.cache.main_members[true_name[0]]
    if not true_name:
        return bot.cache.crews_by_name[true_crew[0]]
    if true_crew[1] >= true_name[1]:
        return bot.cache.crews_by_name[true_crew[0]]
    else:
        return bot.cache.main_members[true_name[0]]


def strip_non_ascii(text: str) -> str:
    encoded_string = text.encode("ascii", "ignore")
    decode_string = encoded_string.decode()
    return decode_string


def add_join_cd(member: discord.Member, file: TextIO):
    file.write(f'{member.id} {time.time() + COOLDOWN_TIME_SECONDS}\n')


async def flair(member: discord.Member, flairing_crew: Crew, bot: 'ScoreSheetBot', staff: bool = False,
                reg: Optional[bool] = False):
    if check_roles(member, [TRUE_LOCKED]):
        raise ValueError(f'{member.mention} cannot be flaired because they are {TRUE_LOCKED}.')

    if check_roles(member, [JOIN_CD]):
        raise ValueError(f'{member.mention} cannot be flaired because they have {JOIN_CD}.')
    if not check_roles(member, [VERIFIED]):
        raise ValueError(f'{member.mention} does not have the DC Verified role. '
                         f'They can verify by typing dc.verify in any channel and then clicking the '
                         f'"Click me to verify!" link in the Double Counter dm.')
    if not staff:
        if check_roles(member, [FLAIR_VERIFY]):
            raise ValueError(f'{member.mention} needs to be verified before flairing. \n'
                             f'Please tag the Doc Keeper role in '
                             f'{bot.cache.channels.flairing_questions.mention} to confirm.')

    if check_roles(member, [FREE_AGENT]):
        await member.remove_roles(bot.cache.roles.free_agent, reason=f'Flaired for {flairing_crew.name}')
    if flairing_crew.overflow:
        await member.add_roles(bot.cache.roles.overflow)
        overflow_crew = discord.utils.get(bot.cache.overflow_server.roles, name=flairing_crew.name)
        overflow_member = discord.utils.get(bot.cache.overflow_server.members, id=member.id)
        await overflow_member.add_roles(overflow_crew)
        member_nick = nick_without_prefix(member.nick) if member.nick else nick_without_prefix(member.name)
        await member.edit(nick=f'{flairing_crew.abbr} | {member_nick}')
    else:
        main_crew = discord.utils.get(bot.cache.scs.roles, name=flairing_crew.name)
        await member.add_roles(main_crew)
    if check_roles(member, [TRACK[2]]):
        await member.remove_roles(bot.cache.roles.track3)
        await member.add_roles(bot.cache.roles.true_locked)
        cowy = discord.utils.get(bot.cache.scs.members, id=329321079917248514)
        flairing_info = bot.cache.channels.flairing_info
        await flairing_info.send(f'{cowy.mention} {member.mention} is {TRUE_LOCKED}.')
    if not reg:
        await member.add_roles(bot.cache.roles.join_cd)


async def unflair(member: discord.Member, author: discord.member, bot: 'ScoreSheetBot'):
    user_crew = crew(member, bot)

    flairing_info = bot.cache.channels.flairing_info
    if check_roles(member, [bot.cache.roles.overflow.name]):
        user = discord.utils.get(bot.cache.overflow_server.members, id=member.id)

        await member.edit(nick=nick_without_prefix(member.display_name))
        role = discord.utils.get(bot.cache.overflow_server.roles, name=user_crew)
        await user.remove_roles(role, reason=f'Unflaired by {author.name}')
        await member.remove_roles(bot.cache.roles.overflow, reason=f'Unflaired by {author.name}')
    else:
        role = discord.utils.get(bot.cache.scs.roles, name=user_crew)
        await member.remove_roles(role, reason=f'Unflaired by {author.name}')
    if await track_cycle(member, bot.cache.scs) == 2:
        cowy = discord.utils.get(bot.cache.scs.members, id=329321079917248514)
        await flairing_info.send(f'{cowy.mention} {member.mention} is locked on next join.')
    if check_roles(member, [LEADER]):
        cr = crew_lookup(user_crew, bot)
        if len(cr.leaders) == 1:
            await flairing_info.send(f'{bot.cache.roles.docs.mention}: {user_crew}\'s last leader just unflaired')
    await member.remove_roles(bot.cache.roles.advisor, bot.cache.roles.leader,
                              reason=f'Unflaired by {author.name}')


def nick_without_prefix(nick: str) -> str:
    if '|' in nick:
        index = nick.rindex('|') + 1
        while nick[index] == ' ':
            index += 1
        return nick[index:]
    else:
        return nick


def role_change(before: Set[discord.Role], after: Set[discord.Role], changer: discord.Member,
                changee: discord.Member, of_before: Optional[Set[discord.Role]] = None,
                of_after: Optional[Set[discord.Role]] = None) -> discord.Embed:
    removed = before - after
    added = after - before
    of_string = []
    if of_before and of_after:
        of_removed = of_before - of_after
        of_added = of_after - of_before
        of_string.append('\nOverflow:\nRoles Removed: ')
        for role in of_removed:
            of_string.append(f'{role.name}, ')
        if of_removed:
            of_string[-1] = of_string[-1][:-2]  # Trim extra comma and space
        of_string.append('\nRoles Added: ')
        for role in of_added:
            of_string.append(f'{role.name}, ')
        if of_added:
            of_string[-1] = of_string[-1][:-2]  # Trim extra comma and space
    header = f'Flairing Change: {str(changee)}'
    body = [f'Mention: {changee.mention}\n', f'ID: {changee.id}\n', 'Roles Removed: ']
    for role in removed:
        body.append(f'{role.name}, ')
    if removed:
        body[-1] = body[-1][:-2]  # Trim extra comma and space
    body.append('\nRoles Added: ')
    for role in added:
        body.append(f'{role.name}, ')
    if added:
        body[-1] = body[-1][:-2]  # Trim extra comma and space
    body.extend(of_string)
    body.append(f'\nChanges Made By: {str(changer)} {changer.id}')

    return discord.Embed(title=header, description=''.join(body), color=changee.color)


async def promote(member: discord.Member, bot: 'ScoreSheetBot', lead: bool = None) -> str:
    if check_roles(member, [LEADER]):
        return 'Leader'
    if check_roles(member, [ADVISOR]) or lead:
        await member.add_roles(bot.cache.roles.leader)
        await member.remove_roles(bot.cache.roles.advisor)
        return 'Leader'
    await member.add_roles(bot.cache.roles.advisor)
    return 'Advisor'


async def demote(member: discord.Member, bot: 'ScoreSheetBot') -> str:
    if check_roles(member, [LEADER]):
        await member.remove_roles(bot.cache.roles.leader)
        await member.add_roles(bot.cache.roles.advisor)
        return 'Leader to Advisor'
    if check_roles(member, [ADVISOR]):
        await member.remove_roles(bot.cache.roles.advisor)
        return 'Advisor to Member'
    return ''


async def response_message(ctx: Context, msg: str) -> discord.Message:
    msg = await ctx.send(f'{ctx.author.mention}: {msg}')
    await ctx.message.delete(delay=1)
    return msg


def crew_members(crew_input: Crew, bot: 'ScoreSheetBot') -> List[discord.Member]:
    members = []
    for member in discord.utils.get(bot.bot.guilds, name=SCS).members:
        try:
            cr = crew(member, bot)
        except ValueError:
            cr = None
        if cr == crew_input.name:
            members.append(member)
    return members


def split_possibilities(two_things: str, sep: Optional[str] = ' ') -> List[Tuple[str, str]]:
    split = two_things.split(sep)
    out = []
    for i in range(len(split)):
        out.append((' '.join(split[:i]), (' '.join(split[i:]))))
    return out


def best_of_possibilities(combined: str, bot: 'ScoreSheetBot', only_use_crews=False):
    pos = split_possibilities(combined)
    all_role_names = {} if only_use_crews else {role.name for role in bot.cache.scs.roles}
    all_role_names = set.union(set(bot.cache.crews), all_role_names)
    best = ['', '', 0]
    for sep in pos:
        if sep[0].lower() in bot.cache.crews_by_tag:
            sep = (bot.cache.crews_by_tag[sep[0].lower()].name, sep[1])

        if sep[1].lower() in bot.cache.crews_by_tag:
            sep = (sep[0], bot.cache.crews_by_tag[sep[1].lower()].name)
        first, second = search_two_roles_in_list(sep[0], sep[1], all_role_names)
        value = first[1] + second[1]
        if value > best[2]:
            best = [first[0], second[0], value]
    return best


def single_crew_plus_string(combined: str, bot: 'ScoreSheetBot'):
    pos = split_possibilities(combined)
    all_role_names = set(bot.cache.crews)
    best = ['', '', 0]
    for sep in pos:
        if sep[0].lower() in bot.cache.crews_by_tag:
            sep = (bot.cache.crews_by_tag[sep[0].lower()].name, sep[1])

        if sep[1].lower() in bot.cache.crews_by_tag:
            sep = (sep[0], bot.cache.crews_by_tag[sep[1].lower()].name)
        first, second = search_two_roles_in_list(sep[0], sep[1], all_role_names)
        value = max(first[1], second[1])
        if value > best[2]:
            best = [first[0], sep[1], value]
    return best


def members_with_str_role(role: str, bot: 'ScoreSheetBot') -> Tuple[str, List[discord.Member], List[int]]:
    all_role_names = {role.name for role in bot.cache.scs.roles}
    all_role_names = set.union(set(bot.cache.crews), all_role_names)

    actual = process.extractOne(role, all_role_names)[0]
    if role.lower() in bot.cache.crews_by_tag:
        actual = bot.cache.crews_by_tag[role.lower()].name
    out = []
    extra = []
    if actual in bot.cache.crews:
        cr = crew_lookup(actual, bot)
        db_members = db_crew_members(cr)
        mems = crew_members(cr, bot)
        for mem in mems:
            if mem.id in db_members:
                db_members.remove(mem.id)
            out.append(mem)
        extra = db_members

    else:
        for member in bot.cache.scs.members:
            role_names = {r.name for r in member.roles}
            if actual in role_names:
                out.append(member)
    return actual, out, extra


def search_two_roles_in_list(first_role: str, second_role: str, everything):
    first = process.extractOne(first_role, everything)
    second = process.extractOne(second_role, everything)
    return first, second


def overlap_members(first: str, second: str, bot: 'ScoreSheetBot') -> List[discord.Member]:
    crew_role = None
    other_role = None
    if first in bot.cache.crews:
        if second in bot.cache.crews:
            raise ValueError(f'Interpreted as {first} and {second}. '
                             f'You can\'t have members on two crews! Try to be more specific.')
        crew_role = first
        other_role = second
    if second in bot.cache.crews:
        crew_role = second
        other_role = first
    out = []
    if crew_role:
        for member in bot.cache.scs.members:
            try:
                if crew(member, bot) == crew_role:
                    for role in member.roles:
                        if role.name == other_role:
                            out.append(member)
            except ValueError:
                continue
    else:
        for member in bot.cache.scs.members:
            role_names = {role.name for role in member.roles}
            if first in role_names and second in role_names:
                out.append(member)
    return out


def noverlap_members(first: str, second: str, bot: 'ScoreSheetBot') -> List[discord.Member]:
    crew_role = None
    other_role = None
    if first in bot.cache.crews:
        if second in bot.cache.crews:
            raise ValueError(f'Interpreted as {first} and {second}. '
                             f'You can\'t have members on two crews! Try to be more specific.')
        crew_role = first
        other_role = second
    if second in bot.cache.crews:
        crew_role = second
        other_role = first
    out = []
    if crew_role:
        for member in bot.cache.scs.members:
            try:
                if crew(member, bot) == crew_role:
                    if not check_roles(member, [other_role]):
                        out.append(member)
            except ValueError:
                continue
    else:
        for member in bot.cache.scs.members:
            role_names = {role.name for role in member.roles}
            if first in role_names and second not in role_names:
                out.append(member)
    return out


async def wait_for_reaction_on_message(confirm: str, cancel: Optional[str],
                                       message: discord.Message, author: discord.Member, bot: discord.Client,
                                       timeout: float = 30.0) -> bool:
    await message.add_reaction(confirm)
    await message.add_reaction(cancel)

    def check(reaction, user):
        return user == author and str(reaction.emoji) == confirm or cancel

    while True:
        try:
            react, reactor = await bot.wait_for('reaction_add', timeout=timeout, check=check)
        except asyncio.TimeoutError:
            return False
        if react.message.id != message.id:
            continue
        if str(react.emoji) == confirm and reactor == author:
            return True
        elif str(react.emoji) == cancel and reactor == author:
            return False


async def handle_decay(bot: 'ScoreSheetBot'):
    cutoffs = [11, 15, 22, 31, 38, 100, 1000]
    elo_loss = [0, 25, 50, 100, 0, 0, 0]
    crews = bot.cache.crews_by_name.values()
    bf = battle_frontier_crews()
    last_played = {cr[0]: cr[2] for cr in bf}
    crews_to_message = []
    exempt = ['EFB', 'EVIL', 'S~R', 'JettFakes']
    for cr in crews:
        if cr.abbr in exempt:
            continue
        if cr.name in last_played:
            timing = last_played[cr.name]
        else:
            timing = None
        if not timing:
            first_flair = first_crew_flair(cr)
            first_flair = datetime(first_flair.year, first_flair.month, first_flair.day)
            timing = datetime(2021, 5, 9)
            if first_flair > timing:
                timing = first_flair
        if datetime(2021, 5, 9) > timing:
            timing = datetime(2021, 5, 9)
        timing = datetime(timing.year, timing.month, timing.day)
        time_since = datetime.now() - timing

        if time_since.days > cutoffs[cr.decay_level]:
            crews_to_message.append((cr, timing))
            elo_decay(cr, elo_loss[cr.decay_level])
        elif cr.decay_level > 0 and time_since.days < cutoffs[0]:
            reset_decay(cr)

    for cr, timing in crews_to_message:
        next_cutoff = timing + timedelta(days=cutoffs[cr.decay_level + 1])
        next_loss = elo_loss[cr.decay_level + 1]
        current_loss = elo_loss[cr.decay_level]
        message = f'This is an automated courtesy reminder that the last crew battle for {cr.name}' \
                  f' was on or before {timing.date().strftime("%m/%d/%y")}.\n'
        if cr.decay_level >= 1:
            message = f'Your crew {cr.name} has lost {current_loss} SCL Rating from inactivity. Your last cb was on ' \
                      f'{timing.date().strftime("%m/%d/%y")}.'
        message += f'If you do not play a cb by {next_cutoff.strftime("%m/%d/%y %H:%M")} EDT,' \
                   f' you will automatically lose {next_loss} SCL Rating from decay.'
        if cr.decay_level >= 2:
            message += '\nYour crew may also be subject to being disbanded ' \
                       'if it has been more than a month since your last ranked crew battle.'
        message += '\nIf you have any questions you can ask in <#492166249174925312>.'
        for leader_id in cr.leader_ids:
            leader = bot.bot.get_user(leader_id)
            try:
                if leader:
                    await leader.send(message)
            except discord.errors.Forbidden:
                await bot.cache.channels.flairing_questions.send(f'{leader.mention}: {message}')


def member_crew_to_db(member: discord.Member, bot: 'ScoreSheetBot'):
    try:
        crew_str = crew(member, bot)
    except ValueError:
        return
    member_crew = crew_lookup(crew_str, bot)
    server = bot.cache.overflow_server if member_crew.overflow else bot.cache.scs
    if not crew_correct(member, crew_str):
        add_member_and_crew(member, member_crew)


def crew_update(bot: 'ScoreSheetBot'):
    cached_crews: Dict[int, Crew] = {cr.role_id: cr for cr in bot.cache_value.crews_by_name.values() if
                                     cr.role_id != -1}
    db_crews = sorted(all_crews(), key=lambda x: x[2])
    rankings = crew_rankings()
    missing = []
    for db_crew in db_crews:
        if db_crew[0] in cached_crews:
            cached = cached_crews.pop(db_crew[0])
        else:
            missing.append(db_crew)
            continue
        formatted = (cached.role_id, cached.abbr, cached.name, None, cached.overflow)
        if formatted != db_crew[0:5]:
            update_crew(cached)
        bot.cache_value.crews_by_name[cached.name].dbattr(*db_crew[5:])
        if db_crew[2] in rankings:
            bot.cache_value.crews_by_name[cached.name].set_rankings(*rankings[db_crew[2]])
    for cr in cached_crews.values():
        update_crew(cr)


async def cooldown_handle(bot: 'ScoreSheetBot'):
    for user_id in cooldown_finished():
        member = bot.cache_value.scs.get_member(user_id)
        if member:
            if check_roles(member, ['24h Join Cooldown']):
                await member.remove_roles(bot.cache_value.roles.join_cd)
                await bot.cache_value.channels.flair_log.send(f'{str(member)}\'s join cooldown ended.')
            else:
                remove_expired_cooldown(user_id)
        else:
            remove_expired_cooldown(user_id)

    uids = {item[0] for item in cooldown_current()}
    for member in bot.cache_value.scs.members:
        if check_roles(member, ['24h Join Cooldown']) and member.id not in uids:
            await member.remove_roles(bot.cache_value.roles.join_cd)
            await bot.cache_value.channels.flair_log.send(f'{str(member)}\'s join cooldown ended.')


async def track_handle(bot: 'ScoreSheetBot'):
    # out_finished = track_finished_out()
    # for mem_id, months in out_finished:
    #     for i in range(min(months, 4)):
    #         track_down_out(mem_id)
    #
    in_finished = track_finished()

async def track_decrement(member: discord.Member, bot: 'ScoreSheetBot'):
    member_roles = member.roles
    for role in member_roles:
        if role.name in FULL_TRACK:
            current_track = FULL_TRACK.index(role.name)
            await member.remove_roles(role)
            msg = f'{member.display_name} moved from {role.name} to '
            if current_track > 0:
                new_role = discord.utils.get(bot.cache.scs.roles, name=FULL_TRACK[current_track - 1])
                await member.add_roles(new_role)
                msg += f'{new_role.name}.'
            else:
                msg += 'no track.'
            await bot.cache_value.channels.flair_log.send(msg)


def strfdelta(tdelta, fmt):
    d = {"days": tdelta.days}
    d["hours"], rem = divmod(tdelta.seconds, 3600)
    d["minutes"], d["seconds"] = divmod(rem, 60)
    return fmt.format(**d)


class Paged(menus.ListPageSource):
    def __init__(self, data, title: str, color: Optional[discord.Color] = discord.Color.purple(),
                 thumbnail: Optional[str] = '', per_page: Optional[int] = 10):
        super().__init__(data, per_page=per_page)
        self.title = title
        self.color = color
        self.thumbnail = thumbnail

    async def format_page(self, menu, entries) -> discord.Embed:
        offset = menu.current_page * self.per_page

        joined = '\n'.join(f'{i + 1}. {v}' for i, v in enumerate(entries, start=offset))
        embed = discord.Embed(description=joined, title=self.title, colour=self.color)
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        return embed


class PlayerStatsPaged(menus.ListPageSource):
    def __init__(self, member: discord.Member, bot: 'ScoreSheetBot'):
        weighted, taken, lost = player_stocks(member)
        total, wins = player_record(member)
        mvps = player_mvps(member)
        title = f'Crew Battle Stats for {str(member)}'
        cb_stats = discord.Embed(title=title, color=member.color)
        cb_stats.add_field(name='Crews record while participating', value=f'{wins}/{total - wins}', inline=True)

        cb_stats.add_field(name='MVPs', value=f'{mvps}', inline=True)
        cb_stats.add_field(name='Stocks', value=f'(See .weighted)', inline=False)
        cb_stats.add_field(name='Taken', value=f'{taken}', inline=True)
        cb_stats.add_field(name='Lost', value=f'{lost}', inline=True)
        cb_stats.add_field(name='Weighted Taken', value=f'{round(weighted, 2)}', inline=True)
        cb_stats.add_field(name='Ratio', value=f'{round(taken / max(lost, 1), 2)}', inline=True)
        cb_stats.add_field(name='Weighted Ratio', value=f'{round(weighted / max(lost, 1), 2)}', inline=True)
        pc = player_chars(member)
        cb_stats.add_field(name='Characters played', value='how many battles played in ', inline=False)
        for char in pc:
            emoji = string_to_emote(char[1], bot.bot)
            cb_stats.add_field(name=emoji, value=f'{char[0]}', inline=True)

        ba_stats = discord.Embed(title=f'Battle Arena Stats for {str(member)}', color=member.color)
        elo = ba_elo(member)
        if elo:

            wins, losses = ba_record(member)
            elo = ba_elo(member)
            ba_stats.add_field(name='record', value=f'{wins}/{losses}', inline=True)
            ba_stats.add_field(name='winrate', value=f'{round(wins / (losses + wins), 2) * 100}%', inline=True)

            ba_stats.add_field(name='Rating', value=f'{elo}', inline=False)
            # TODO Add ranking here

            ba_stats.add_field(name='Characters played', value='how many matches played in ', inline=False)
            chars = ba_chars(member)
            for char in chars:
                emoji = string_to_emote(char[1], bot.bot)
                ba_stats.add_field(name=emoji, value=f'{char[0]}', inline=True)
        else:
            ba_stats.description = 'This member has no battle arena history.'
        data = [cb_stats, ba_stats]
        super().__init__(data, per_page=1)

    async def format_page(self, menu, entries) -> discord.Embed:
        return entries


def battle_summary(bot: 'ScoreSheetBot', battle_type: BattleType) -> Optional[discord.Embed]:
    if battle_type == BattleType.MOCK:
        ty = 'Mock'
    elif battle_type == BattleType.MASTER:
        ty = 'Master Class'
    elif battle_type == BattleType.REG:
        ty = 'Registration'
    else:
        ty = 'Ranked'
    title = f'Current {ty} Battles'
    embed = discord.Embed(title=title, color=discord.Color.random())
    for key, battle in bot.battle_map.items():
        if battle:
            if battle.battle_type == battle_type:
                chan = discord.utils.get(bot.cache.scs.channels, id=channel_id_from_key(key))
                title = f'{battle.team1.name} vs {battle.team2.name}: ' \
                        f'{battle.team1.num_players} vs {battle.team2.num_players}'
                text = f'{battle.team1.stocks}-{battle.team2.stocks} {chan.mention}'
                if 'Not Set' not in battle.stream:
                    text += f' [stream]({battle.stream})'
                embed.add_field(name=title, value=text, inline=False)
    if len(embed.fields) == 0:
        return None
    return embed


async def overflow_anomalies(bot: 'ScoreSheetBot') -> Tuple[Set, Set]:
    overflow_role = set()
    for member in bot.cache.scs.members:
        if check_roles(member, OVERFLOW_ROLE):
            overflow_role.add(member.id)
    other_set = set()
    other_members = bot.cache.overflow_server.members
    for member in other_members:
        if any((role.name in bot.cache.crews for role in member.roles)):
            other_set.add(member.id)
            continue
    first = overflow_role - other_set
    for mem_id in first:
        mem = bot.cache.scs.get_member(mem_id)
        await mem.remove_roles(bot.cache.roles.overflow, bot.cache.roles.leader, bot.cache.roles.advisor)
        await mem.edit(nick=nick_without_prefix(mem.display_name))
        crew_name = find_member_crew(mem_id)
        out_str = f'{str(mem)} left the overflow server and lost their roles here.'
        if crew_name:
            cr = crew_lookup(crew_name, bot)
            if bot.cache.roles.join_cd.id in all_member_roles(mem_id):
                mod_slot(cr, 1)
                unflairs, remaining, total = record_unflair(mem_id, cr, True)

                out_str += (
                    f'\n{str(mem_id)} was on 24h cooldown so {cr.name} gets back a slot ({remaining}/{total})')
            # Else refund 1/3 slot
            else:
                unflairs, remaining, total = record_unflair(mem_id, cr, False)

                if unflairs == 3:
                    out_str += f'{cr.name} got a flair slot back for 3 unflairs. {remaining}/{total} left.'
                else:
                    out_str += f'{unflairs}/3 unflairs for returning a slot.'
            out_str += f'They were previously on {crew_name}'
        await bot.cache.channels.flair_log.send(out_str)
    second = other_set - overflow_role
    for mem_id in second:
        mem = bot.cache.overflow_server.get_member(mem_id)
        for role in mem.roles:
            if role.name in bot.cache.crews:
                out_str = \
                    (f'{str(mem)} no longer has the overflow role in the main server so they have been unflaired from'
                     f'{role.name}.')
                cr = crew_lookup(role.name, bot)
                if bot.cache.roles.join_cd.id in all_member_roles(mem_id):
                    mod_slot(cr, 1)
                    unflairs, remaining, total = record_unflair(mem_id, cr, True)

                    out_str += (
                        f'\n{str(mem_id)} was on 24h cooldown so {cr.name} gets back a slot ({remaining}/{total})')
                # Else refund 1/3 slot
                else:
                    unflairs, remaining, total = record_unflair(mem_id, cr, False)

                    if unflairs == 3:
                        out_str += f'{cr.name} got a flair slot back for 3 unflairs. {remaining}/{total} left.'
                    else:
                        out_str += f'{unflairs}/3 unflairs for returning a slot.'
                await mem.remove_roles(role)
                await bot.cache.channels.flair_log.send(out_str)

    return first, second


async def unlock(channel: discord.TextChannel) -> None:
    await channel.edit(sync_permissions=True)


def parseTime(timestr: str) -> date:
    parts = timestr.split(' ')
    current = datetime.now().date()
    for part in parts:
        increment = part[-1].lower()
        if increment not in ['w', 'd', 'm']:
            raise ValueError(f'{part} needs to be in the format numberIncrement, eg 1M or 2D or 3W.')
        number = int(part[:-1])
        if number <= 0:
            raise ValueError('need to have a number larger than 0')
        if increment == 'm':
            current += relativedelta(months=+number)
        if increment == 'w':
            current += relativedelta(weeks=+number)
        if increment == 'd':
            current += relativedelta(days=+number)
    return current


async def handle_unfreeze(bot: 'ScoreSheetBot'):
    unfrozen = auto_unfreeze()
    if unfrozen:
        for cr in unfrozen:
            await bot.cache.channels.flair_log.send(f'{cr[0]} finished their registration freeze.')


def closest_command(command: str, bot: 'ScoreSheetBot'):
    command_strs = [cmd.name for cmd in bot.get_commands()]
    actual, _ = process.extractOne(command, command_strs)
    return actual


async def join_gambit(member: discord.Member, bot: 'ScoreSheetBot') -> bool:
    msg = await member.send(f'{str(member)}: It appears you are not part of gambit, '
                            f'would you like to join gamibt?')
    if not await wait_for_reaction_on_message(YES, NO, msg, member, bot.bot):
        await member.send(f'Timed out or canceled! You need to respond within 30 seconds!')
        return False

    await member.send(f'Welcome to gambit! Here are {new_member_gcoins(member)} coins for your trouble.')
    # TODO add gambit guide right here
    return True


def validate_bet(member: discord.Member, on: Crew, amount: int, bot: 'ScoreSheetBot'):
    cg = current_gambit()
    if on.name not in [cg.team1, cg.team2]:
        raise ValueError(
            f'{on.name} not one of the two crews in the current gambit ({cg.team1}, {cg.team2}).')

    try:
        member_crew = crew(member, bot)
    except ValueError:
        member_crew = None
    if member_crew in [cg.team1, cg.team2]:
        raise ValueError(
            f'{member.mention} is on {member_crew}, a crew competing in the gambit and cannot participate.')

    current = member_gcoins(member)
    team, bet_amount = member_bet(member)
    if current == 0 and not team:
        return
    if amount > current:
        raise ValueError(f'{member.mention} only has {current} and cannot bet {amount}.')
    if team:
        if on.name != team:
            raise ValueError(f'{member.mention} already has a bet on {team} can\'t also bet on {on.name}')

    if amount <= 0:
        raise ValueError('You must bet a positive amount!')


async def confirm_bet(ctx: Context, on: Crew, amount: int, bot: 'ScoreSheetBot') -> bool:
    member = ctx.author
    current = member_gcoins(member)
    team, bet_amount = member_bet(member)
    if team:
        msg = await ctx.send(f'{str(member)} has {bet_amount} already on'
                             f' {team} do you want to increase that to {bet_amount + amount}?')
    else:
        if current == 0:
            amount = 0
        msg = await ctx.send(f'{member.mention} really bet {amount} on {on.name}?')
    if not await wait_for_reaction_on_message(YES, NO, msg, member, bot.bot):
        await ctx.send(f'{member.mention}: Your bet timed out or was canceled! You need to respond within 30 seconds!')
        return False
    validate_bet(member, on, amount, bot)
    final = make_bet(member, on, amount)
    if amount == 0:
        await ctx.send(
            f'{member.mention}: You have placed a reset bet of 0 with a chance to win back in with 220 G-Coins.')
    else:
        if team:
            await ctx.send(f'{member.mention}: Bet on **{on.name}** increased to {amount + bet_amount} G-Coins. '
                           f'You have {final} G-Coins remaining.')
        else:
            await ctx.send(f'{member.mention}: Bet on **{on.name}** made for {amount} G-Coins. '
                           f'You have {final} G-Coins remaining.')
    await msg.delete(delay=2)
    return True


async def update_gambit_message(gambit: Gambit, bot: 'ScoreSheetBot'):
    message = await bot.gambit_message(gambit.message_id)
    if not message:
        return
    crew1 = crew_lookup(gambit.team1, bot)
    crew2 = crew_lookup(gambit.team2, bot)

    try:
        await message.edit(embed=gambit.embed(crew1.abbr, crew2.abbr))
    except discord.errors.NotFound:
        pass


async def update_finished_gambit(gambit: Gambit, winner: int, bot: 'ScoreSheetBot', top_win, top_loss):
    message = await bot.gambit_message(gambit.message_id)
    if message:
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass

    crew1 = crew_lookup(gambit.team1, bot)
    crew2 = crew_lookup(gambit.team2, bot)
    await bot.cache.channels.gambit_announce.send(
        embed=gambit.finished_embed(crew1.abbr, crew2.abbr, winner, top_win, top_loss))


def crew_avg(crews: List[Crew]) -> float:
    total = 0
    for cr in crews:
        total += cr.member_count
    return total / len(crews)


def crew_stdev(crews: List[Crew]) -> float:
    member_numbers = [cr.member_count for cr in crews]
    return stdev(member_numbers)


def crew_bar_chart(crews: List[Crew]):
    member_numbers = [cr.member_count for cr in crews]
    bins = 20
    plt.hist(member_numbers, bins=bins)
    plt.title('Crew Sizes')
    plt.xlabel('Crews')
    plt.ylabel('Sizes')
    plt.savefig('cr.png')


def avg_flairs(flairs: List[Tuple[str, int]]) -> float:
    combined = sum([fl[1] for fl in flairs])
    return combined / len(flairs)


def flair_stdev(flairs: List[Tuple[str, int]]) -> float:
    combined = [fl[1] for fl in flairs]
    return stdev(combined)


def flair_bar_chart(flairs: List[Tuple[str, int]]):
    member_numbers = [fl[1] for fl in flairs]
    bins = 20
    plt.hist(member_numbers, bins=bins)
    plt.title('Crew Flairs last 30 days')
    plt.xlabel('Crews')
    plt.ylabel('Flairs')
    plt.savefig('fl.png')


def calc_total_slots(cr: Crew) -> Tuple[int, int, int, int]:
    if cr.ladder.startswith('**R'):
        base = 8
        rollover_max = 3
    else:
        base = 7
        rollover_max = 2
    sl = slots(cr)
    if sl and not cr.freeze:
        rollover = sl[0]
    else:
        rollover = 0
    modifiers = [6, 4, 2, 0, -1, -2]
    modifer_loc = 0
    while modifer_loc < 4 and cr.member_count >= SLOT_CUTOFFS[modifer_loc]:
        modifer_loc += 1

    total = base + modifiers[modifer_loc]
    total = max(total, 5) + min(rollover, rollover_max)

    return total, base, modifiers[modifer_loc], min(rollover_max, rollover)


def calc_reg_slots(members: int) -> int:
    base = 8
    modifiers = [6, 4, 2, 0, -1, -2]
    modifer_loc = 0
    while modifer_loc < 4 and members >= SLOT_CUTOFFS[modifer_loc]:
        modifer_loc += 1

    return base + modifiers[modifer_loc]


async def unflair_gone_member(ctx: Context, user: str, bot: 'ScoreSheetBot'):
    try:
        user_id = int(user.strip("<!@>"))
    except ValueError:
        raise ValueError(f'{user} is not a mention or an id. Try again.')
    # Get crew of gone member
    cr = find_member_crew(user_id)
    # Check if author is leader of that crew or admin
    pl = power_level(ctx.author)
    if pl < 3:
        author_crew = crew(ctx.author, bot)
        if author_crew != cr:
            await response_message(ctx, f'{ctx.author.mention} on {author_crew} cannot unflair {user} on {cr}')
            return
        if pl < 1:
            await response_message(ctx, f'{ctx.author.mention} needs to be an advisor or leader to unflair others.')
            return
    crew_name = find_member_crew(user_id)
    if not crew_name:
        await response_message(ctx, f'{user} is not on a crew and not on the server.')
        return
    # Remove crew role
    cr = crew_lookup(crew_name, bot)
    roles = bot.cache.roles
    remove_member_role(user_id, cr.role_id)
    desc = [f'Roles lost by {user_id}:', cr.name]
    member_roles = all_member_roles(user_id)
    # Remove leadership + overflow role
    roles_to_remove = [roles.overflow, roles.leader, roles.advisor]
    for role in roles_to_remove:
        if role.id in member_roles:
            desc.append(role.name)
            remove_member_role(user_id, role.id)

    # Remove from current crews
    update_member_crew(user_id, None)

    # Unflair log in db
    # Refund slot if 24h cd (do not remove)
    if roles.join_cd.id in member_roles:
        mod_slot(cr, 1)
        unflairs, remaining, total = record_unflair(user_id, cr, True)

        await ctx.send(f'{str(user_id)} was on 24h cooldown so {cr.name} gets back a slot ({remaining}/{total})')
    # Else refund 1/3 slot
    else:
        unflairs, remaining, total = record_unflair(user_id, cr, False)

        if unflairs == 3:
            await ctx.send(f'{cr.name} got a flair slot back for 3 unflairs. {remaining}/{total} left.')
        else:
            await ctx.send(f'{unflairs}/3 unflairs for returning a slot.')
    # Track Cycle
    tracks = [roles.track1, roles.track2, roles.track3]
    track = -1
    if roles.true_locked.id not in member_roles:
        for i in range(len(tracks)):
            if tracks[i].id in member_roles:
                track = i
        if track < 2:
            if track >= 0:
                desc.append(tracks[track].name)
                remove_member_role(user_id, tracks[track].id)
            add_member_role(user_id, tracks[track + 1].id)
            desc.append('Roles Added:')
            desc.append(tracks[track + 1].name)
    desc.append(f'\nChanges Made By: {str(ctx.author)} {ctx.author.id}')
    # Unflair log in flaring logs
    embed = discord.Embed(title=f'{user_id} unflaired while not in server', color=cr.color, description='\n'.join(desc))
    await bot.cache.channels.flair_log.send(embed=embed)
    # Respond in the channel
    await response_message(ctx, f'successfully unflaired {user_id}.')


def find_role_category(role: discord.Role, categories: List[discord.Role]) -> Optional[discord.Role]:
    if role.position == 0:
        return
    i = 0
    while role.position > categories[i].position:
        if role.position == categories[i].position:
            return
        i += 1
        if i >= len(categories) - 1:
            return

    return categories[i]


async def set_categories(member: discord.Member, categories: List[discord.Role]):
    has = set()
    has_not = set(categories)
    for role in member.roles:
        if role in categories:
            continue
        category = find_role_category(role, categories)
        if not category:
            continue
        has.add(category)
        has_not.discard(category)
    has_dupe = set()
    for role in has:
        if role in member.roles:
            has_dupe.add(role)
    has -= has_dupe
    has_not_dupe = set()
    for role in has_not:
        if role not in member.roles:
            has_not_dupe.add(role)
    has_not -= has_not_dupe
    if has:
        await member.add_roles(*has)
    if has_not:
        await member.remove_roles(*has_not)


async def clear_current_cbs(bot: 'ScoreSheetBot'):
    await bot.cache.channels.current_cbs.purge()
