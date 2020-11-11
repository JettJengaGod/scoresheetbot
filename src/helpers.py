from typing import List

import discord


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
