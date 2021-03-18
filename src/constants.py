import os
from dotenv import load_dotenv
from enum import Enum

load_dotenv()
CACHE_TIME = 600_000_000_000  # 6000 seconds
CACHE_TIME_SECONDS = 300
OVERFLOW_SERVER = 'Overflow Beta' if os.getenv('VERSION') == 'ALPHA' else 'SCS Overflow Server'

TRACK = ['Track 1', 'Track 2', 'Move Locked Next Join']
TRUE_LOCKED = 'Full Move Locked'
OVERFLOW_ROLE = 'SCS Overflow Crew'
LEADER = 'Leader'
MINION = 'v2 Minion'
ADMIN = 'SCS Admin'
ADVISOR = 'Advisor'
WATCHLIST = '! Watchlisted !'
CERTIFIED = 'SCS Certified Streamer'
STREAMER = 'Streamers'
DOCS = 'Doc Keeper'
FREE_AGENT = 'Free Agent'
LEAD_RESTRICT = 'Leadership Restriction'
SCS = 'ScoresheetBot' if os.getenv('VERSION') == 'ALPHA' else 'Smash Crew Server'
OUTPUT = 'scoresheet_output'
BOT = 'Bots'
DOCS_UPDATES = 'scs_docs_updates'
JOIN_CD = '24h Join Cooldown'
FLAIRING_LOGS = 'jettbot_flairing_logs'
FLAIR_VERIFY = '! Verify Flair Change !'
PLAYOFF_LIMITED = 'Playoff Locked'
BOT_CORNER_ID = 430367391227052054
FLAIRING_QUESTIONS_ID = 786842350822490122
COOLDOWN_TIME_SECONDS = 60 * 60 * 24  # 24 Hours
TEMP_ROLES_FILE = 'temp_roles.txt'
FLAIRING_CHANNEL_NAME = 'crew_flairing'
FLAIRING_INFO = 'flairing_info'
DOC_KEEPER_CHAT = 'scs_doc_keepers'

SHEET_HISTORY = 'scoresheet_history'
GAMBIT_ANNOUNCE = 819098161221468200
GAMBIT_BOT_ID = 813645001271672852
GAMBIT_ROLE = 'Gambit'
YES = '✅'
NO = '⛔'
STAFF_LIST = [DOCS, MINION, ADMIN]
EXPECTED_NON_CREW_ROLES = {
    LEADER,
    TRUE_LOCKED,
    OVERFLOW_ROLE,
    MINION,
    ADMIN,
    ADVISOR,
    WATCHLIST,
    CERTIFIED,
    STREAMER,
    DOCS,
    '@everyone',
    'Auto Publisher',
    'JettAutoScoreSheet',
    'Member Count',
    'Full Move Locked',
    'Move Locked Next Join',
    'Track 2',
    'Track 1',
    'Verify',
    'AltDentifier',
    'Community',
    'Matchmaking',
    'React Bot',
    'Mock Battle',
    'Battle Arena',
    'Crew Battle',
    'Floof Bot',
    'Blitz Calling',
    'Gambit',
    'SCS Server Booster',
    'Scoresheeter',
    'Streamers',
    'Free Agent',
    'Advisor',
    'Leader',
    'SCS Overflow Crew',
    '! Verify Flair Change !',
    '! Watchlisted !',
    'MEE6Muted',
    'Muted',
    'MEE6',
    'YAGPDB.xyz',
    'SCS Certified Streamer',
    'Crew Coordinators',
    'Leader Union',
    'Doc Keeper',
    'Consultant',
    'v2 Minion',
    'Violations Committee',
    'Player Union',
    'Bots',
    'ModMail',
    'SCS Admin',
    '! Verify Flair !',
    'Young Night Train',
    'BurnerV3',
    'da tristate man',
    'Dyno',
    'Verify',
    'Guest',
    'AltDentifier',
    'Admin Bots',
    'Doc Keeper',
    'Floof Bot',
    'SCS Violations Committee',
    'v2 Minion',
    'SCS Admin',
    PLAYOFF_LIMITED,
    JOIN_CD,
    'BetaJettBot',
    'EVIL',
    'Special Pass',
    'how',
    'Players Union',
    'Leadership Restriction',
    'JettBot',
    'DC Verify',
    'Double Counter',
    'Corneo Champion',
    'CMC Tempered Leader',
    PLAYOFF_LIMITED
}
PLAYOFF_CHANNEL_NAMES = ['', 'first_class_playoffs_results', 'cm-extreme_playoffs_results',
                         'cm-tempered_playoffs_results']

WLED_CREWS = ['Royal Knights']


class PlayoffType(Enum):
    NO_PLAYOFF = 1
    LEGACY = 2
    EXTREME = 3
    TEMPERED = 4


SLOT_CUTOFFS = [11, 19, 34, 41]
RANK_CUTOFF = 4
