from typing import List, Iterable, Set

import discord

TRACK = ['Track 1', 'Track 2', 'Move Locked']


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


def check_roles(user: discord.Member, roles: Iterable) -> bool:
    return any((role.name in roles for role in user.roles))


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
