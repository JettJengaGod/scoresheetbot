from typing import Optional, List, Tuple

CHARACTERS = {
    'banjo_and_kazooie': ['banjo', 'banjokazooie'],
    'bayonetta': ['bayo'],
    'bowser': [],
    'bowser_jr': ['bjr'],
    'byleth': [],
    'captain_falcon': ['falcon'],
    'chrom': [],
    'clouds': ['cloud'],
    'corrin': [],
    'daisy': [],
    'dark_pit': [],
    'diddy_kong': ['diddy'],
    'donkey_kong': ['dk'],
    'dr_mario': ['dr.mario'],
    'duck_hunt': ['dh'],
    'falco': [],
    'foxs': ['fox'],
    'ganondorf': ['ganon'],
    'greninja': ['gren'],
    'hero': [],
    'ice_climbers': ['ic', 'ics', 'icies', 'climbers', 'iceclimber'],
    'ike': [],
    'incineroar': ['incin'],
    'inkling': ['ink'],
    'isabelle': ['isa'],
    'jigglypuff': ['jiggs', 'jigg', 'jiggly', 'puff'],
    'joker': [],
    'ken': [],
    'king_dedede': ['dedede', 'd3', 'ddd'],
    'king_k_rool': ['krool'],
    'kirby': [],
    'links': ['link'],
    'little_mac': ['mac'],
    'lucario': [],
    'lucas': [],
    'lucina': ['luci'],
    'luigi': [],
    'mario': [],
    'marth': [],
    'mega_man': [],
    'meta_knight': ['mk'],
    'mewtwo': ['m2'],
    'mii_brawler': ['brawler'],
    'mii_gunner': ['gunner'],
    'mii_swordfighter': ['swordfighter'],
    'min_min': [],
    'mr_game_and_watch': ['gnw', 'g&w', 'gameandwatch', 'game&watch'],
    'ness': [],
    'olimar': ['oli'],
    'pac_man': ['pac'],
    'palutena': ['palu'],
    'peachs': ['peach'],
    'pichu': [],
    'pikachu': ['pika'],
    'piranha_plant': ['plant'],
    'pit': [],
    'pokemon_trainer': ['pt', 'trainer'],
    'richter': [],
    'ridley': [],
    'rob': ['r.o.b.'],
    'robin': [],
    'rosalina_and_luma': ['rosa', 'rosalina', 'rosaluma'],
    'roy': [],
    'ryu': [],
    'samus': [],
    'sheik': ['shiek'],
    'shulk': [],
    'simon': [],
    'snakes': ['snake'],
    'sonic': [],
    'steve': ['enderman', 'alex'],
    'terry': [],
    'toon_link': ['tink'],
    'villager': ['villi'],
    'wario': [],
    'wii_fit_trainer': ['wiifit', 'wft'],
    'wolfs': ['wolf'],
    'yoshi': [],
    'young_link': ['yink'],
    'zelda': [],
    'zero_suit_samus': ['zss'],
}

ID_FROM_CANONICAL = {
    'banjo_and_kazooie': 596831625765978131,
    'bayonetta': 575804398215757854,
    'bowser': 575804398123352104,
    'bowser_jr': 575804398186528768,
    'byleth': 672630558886461460,
    'captain_falcon': 575804398425604116,
    'chrom': 575804398521810994,
    'clouds': 575804398496776192,
    'corrin': 575804398530330634,
    'daisy': 575804398677262346,
    'dark_pit': 575804398718943243,
    'diddy_kong': 575804398413021219,
    'donkey_kong': 575804398631124993,
    'dr_mario': 575804398865743879,
    'duck_hunt': 575804398962475029,
    'falco': 575804399142567936,
    'foxs': 575804399096561664,
    'ganondorf': 575804399348088833,
    'greninja': 575804399276916756,
    'hero': 596831646842486805,
    'ice_climbers': 575804399339700234,
    'ike': 575804399377711115,
    'incineroar': 575804399272722432,
    'inkling': 575804399549415424,
    'isabelle': 575804745453797396,
    'jigglypuff': 575804399545483264,
    'joker': 575804399742484500,
    'ken': 575804400195469331,
    'king_dedede': 575804399847211052,
    'king_k_rool': 575804399830564894,
    'kirby': 575804399587164190,
    'links': 575804400056926250,
    'little_mac': 575804400099131394,
    'lucario': 575804400136880142,
    'lucas': 575804400023371776,
    'lucina': 575804400208052244,
    'luigi': 575804401130799130,
    'mario': 575804400140943381,
    'marth': 575804400157589546,
    'mega_man': 575804482064089089,
    'meta_knight': 575804482084929546,
    'mewtwo': 575804482198175763,
    'mii_brawler': 596831773338632202,
    'mii_gunner': 596831773556736000,
    'mii_swordfighter': 596831773535764527,
    'min_min': 728013949865558046,
    'mr_game_and_watch': 575804481980071939,
    'ness': 575804482642771994,
    'olimar': 575804482756018196,
    'pac_man': 575804482148106276,
    'palutena': 575804482387050560,
    'peachs': 575804482852618265,
    'pichu': 575804744325398532,
    'pikachu': 575804744040185894,
    'piranha_plant': 595042549887139840,
    'pit': 575804744476393502,
    'pokemon_trainer': 575804744849948674,
    'richter': 575804744510078976,
    'ridley': 575804744996487168,
    'rob': 575804744363409409,
    'robin': 575804744707211284,
    'rosalina_and_luma': 575804744917057577,
    'roy': 575804744891891714,
    'ryu': 575804745005006868,
    'samus': 575804744959000577,
    'steve': 761608590867038248,
    'sheik': 575804745193881610,
    'shulk': 575804745302671399,
    'simon': 575804745340420126,
    'snakes': 575804746561093632,
    'sonic': 575804745462317071,
    'terry': 641715693225639953,
    'toon_link': 575804745760112650,
    'villager': 575804745558655016,
    'wario': 575804745520906260,
    'wii_fit_trainer': 575804745654992906,
    'wolfs': 575804745797599252,
    'yoshi': 575804745734946816,
    'young_link': 575804746091462688,
    'zelda': 575804745877553182,
    'zero_suit_samus': 575804746124886016,
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


def string_to_emote(input_str: str) -> Optional[str]:
    input_str = clean_emoji(input_str)
    # Lowercase, remove ':' and '_'.
    input_str = input_str.strip(':').lower().replace('_', '')

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
    else:
        raise ValueError('Unknown character: \'{}\', try `!chars` '.format(character))

    return '<:{}{}:{}>'.format(canonical_name, '' if alt_num == 1 else alt_num, ID_FROM_CANONICAL[canonical_name])


def all_emojis() -> List[Tuple[str, str]]:
    ret = []
    for c_name, c_id in ID_FROM_CANONICAL.items():
        ret.append((c_name, f'<:{c_name}:{c_id}> AKA: {CHARACTERS[c_name]}'))
    return ret


class Character:
    def __init__(self, char: str):
        if not char:
            self.name = ''
            self.emoji = ''
            return
        char = clean_emoji(char)
        if char[-1].isdigit():
            self.skin = char[-1]
            char = char[:-1]
        self.name = char
        self.emoji = string_to_emote(char)

    def __str__(self):
        return self.emoji
