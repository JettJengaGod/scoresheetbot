from typing import Optional, List, Tuple
import discord

CHARACTERS = {
    'banjo_and_kazooie': ['banjo', 'banjokazooie'],
    'bayonetta': ['bayo'],
    'bowser': [],
    'bowser_jr': ['bjr', 'jr', 'larry', 'royjr', 'wendy', 'iggy', 'morton', 'lemmy', 'ludwig'],
    'byleth': [],
    'captain_falcon': ['falcon'],
    'chrom': [],
    'clouds': ['cloud'],
    'corrin': [],
    'daisy': [],
    'dark_pit': ['dpit'],
    'dark_samus': ['damus', 'ds', 'darkus', 'dsamus'],
    'diddy_kong': ['diddy'],
    'donkey_kong': ['dk', 'monke', 'monkee'],
    'dr_mario': ['dr.mario', 'doc'],
    'duck_hunt': ['dh', 'dhd','doge'],
    'falco': [],
    'foxs': ['fox'],
    'ganondorf': ['ganon'],
    'greninja': ['gren'],
    'hero': [],
    'ice_climbers': ['ic', 'ics', 'icies', 'climbers', 'iceclimber'],
    'ike': [],
    'incineroar': ['incin', 'roar'],
    'inkling': ['ink'],
    'isabelle': ['isa'],
    'jigglypuff': ['jiggs', 'jigg', 'jiggly', 'puff'],
    'joker': [],
    'kazuya': ['kaz'],
    'ken': [],
    'king_dedede': ['dedede', 'ddd'],
    'king_k_rool': ['krool', 'croc'],
    'kirby': [],
    'links': ['link'],
    'little_mac': ['mac'],
    'lucario': [],
    'lucas': [],
    'lucina': ['luci'],
    'luigi': [],
    'mario': [],
    'marth': [],
    'mega_man': ['mm'],
    'meta_knight': ['mk'],
    'mewtwo': ['m2'],
    'mii_brawler': ['brawler'],
    'mii_gunner': ['gunner'],
    'mii_swordfighter': ['swordfighter', 'msf'],
    'min_min': ['min'],
    'mr_game_and_watch': ['gnw', 'g&w', 'gameandwatch', 'game&watch', 'gw', 'mgw'],
    'ness': ['wide', 'thicc'],
    'olimar': ['oli', 'alph'],
    'pac_man': ['pac'],
    'palutena': ['palu'],
    'peachs': ['peach'],
    'pichu': [],
    'pikachu': ['pika'],
    'piranha_plant': ['plant', 'pp'],
    'pit': [],
    'pokemon_trainer': ['pt', 'trainer'],
    'pythra': ['pyra', 'mythra', 'aegis', 'baeblades', 'myra'],
    'random': ['rand'],
    'richter': [],
    'ridley': [],
    'rob': ['r.o.b.'],
    'robin': [],
    'rosalina_and_luma': ['rosa', 'rosalina', 'rosaluma'],
    'roy': [],
    'ryu': [],
    'samus': [],
    'sephiroth': ['seph'],
    'sheik': ['shiek'],
    'shulk': [],
    'simon': [],
    'snakes': ['snake'],
    'sonic': [],
    'sora': [],
    'steve': ['enderman', 'alex', 'zombie'],
    'terry': [],
    'toon_link': ['tink'],
    'villager': ['villi', 'villy'],
    'wario': [],
    'wii_fit_trainer': ['wiifit', 'wft', 'wii'],
    'wolfs': ['wolf'],
    'yoshi': [],
    'young_link': ['yink'],
    'zelda': [],
    'zero_suit_samus': ['zss'],
}

S_SET = {
    'clouds',
    'wolfs',
    'links',
    'peachs',
    'snakes',
    'foxs'

}

for name in CHARACTERS:
    CHARACTERS[name].append(name.replace('_', ''))

CANONICAL_NAMES_MAP = {}  # Maps alternate names to canonical names.
for canonical_name in CHARACTERS:
    for alt_name in CHARACTERS[canonical_name]:
        CANONICAL_NAMES_MAP[alt_name] = canonical_name

# Assert that all names are distinct.
assert sum(len(x) for x in CHARACTERS.values()) == len(CANONICAL_NAMES_MAP)


def clean_emoji(input_str: str) -> str:
    if input_str.startswith('<:'):
        input_str = input_str[2:]
        if input_str.endswith('>'):
            input_str = input_str[:-1]
        return input_str[:input_str.index(':')]
    return input_str


JR_LIST = ['bowser_jr', 'larry', 'royjr', 'wendy', 'iggy', 'morton', 'lemmy', 'ludwig']


def post_process(character: str, canonical_name: str, alt_num: int) -> Optional[str]:
    if canonical_name in S_SET and alt_num > 1:
        canonical_name = canonical_name[:-1]
    if canonical_name in JR_LIST:
        if alt_num > 1:
            canonical_name = JR_LIST[alt_num - 1]
            alt_num = 1
        elif canonical_name != 'bowser_jr':
            canonical_name = character
    if canonical_name == 'olimar':
        if alt_num > 4:
            canonical_name = 'alph'
    if canonical_name == 'steve':
        if alt_num in [2, 4, 6]:
            canonical_name = 'alex'
        if alt_num == 7:
            canonical_name = 'zombie'
        if alt_num == 8:
            canonical_name = 'enderman'
    return '{}{}'.format(canonical_name, '' if alt_num == 1 else alt_num)


def pre_process(input_str: str) -> Tuple[str, str, int]:
    input_str = clean_emoji(input_str)
    # Lowercase, remove ':' and '_'.
    input_str = input_str.strip(':').lower().replace('_', '').replace(' ', '')

    if not input_str:
        raise ValueError('Input string too short')
    last_char = input_str[-1]
    if last_char.isdigit():
        alt_num = int(last_char)
        if not 1 <= alt_num <= 8:
            raise ValueError('Alt number {} must be 1-8'.format(alt_num))
        character = input_str[:-1]
    else:
        alt_num = 1
        character = input_str
    if character in CANONICAL_NAMES_MAP:
        canonical_name = CANONICAL_NAMES_MAP[character]
        return character, canonical_name, alt_num
    else:
        raise ValueError('Unknown character: \'{}\' remember no spaces in character names, '
                         'try `,chars` '.format(character))


def string_to_canonical(input_str: str) -> Optional[str]:
    character, base, alt_num = pre_process(input_str)
    return post_process(character, base, alt_num)


def canonical_to_emote(canonical: str, bot) -> str:
    return str(discord.utils.get(bot.emojis, name=canonical))


def string_to_emote(input_str: str, bot) -> Optional[str]:
    return str(discord.utils.get(bot.emojis, name=string_to_canonical(input_str)))


def all_alts(input_str: str, bot):
    last_char = input_str[-1]
    if last_char.isdigit():
        input_str = input_str[:-1]
    return ''.join([string_to_emote(input_str + str(i), bot) for i in range(1, 9)])


def all_emojis(bot) -> List[Tuple[str, str]]:
    ret = []
    for c_name, alts in CHARACTERS.items():
        if c_name.startswith('mii') or c_name.startswith('random') or c_name.startswith('sora'):
            ret.append((c_name, f'{string_to_emote(c_name, bot)} AKA: {alts}'))
            continue
        ret.append((c_name, f'{all_alts(c_name, bot)} AKA: {alts}'))
    return ret


class Character:

    def __init__(self, char: str, bot, valid_emoji: bool = False):
        # TODO Parse this into categories
        # if not valid_emoji:
        if not char:
            self.emoji_name = ''
            self.emoji = ''
            return
        char = clean_emoji(char)
        _, self.base, self.skin = pre_process(char)
        self.emoji_name = string_to_canonical(char)
        if bot:
            self.emoji = canonical_to_emote(self.emoji_name, bot)
        else:
            self.emoji = self.emoji_name
        # else:
        #     self.char = char
        #     self.emoji = char

    def __str__(self):
        return self.emoji
