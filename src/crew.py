import dataclasses
import discord
from typing import List
from datetime import datetime


@dataclasses.dataclass
class DbCrew:
    discord_id: int
    tag: str
    name: str
    rank: int
    overflow: bool
    watch_listed: bool
    freeze_date: datetime
    verify: bool
    strikes: int
    slots_total: int
    slots_left: int
    decay_level: int
    last_battle: datetime
    last_opp: str
    db_id: int
    softcap_max: int = 0
    member_count: int = 0
    triforce: int = 0
    softcap_used: int = 0
    current_destiny: int = 0
    destiny_opponent: str = ''
    destiny_rank: int = 0
    destiny_opt_out: bool = False


@dataclasses.dataclass
class Crew:
    name: str
    abbr: str
    social: str = ''
    trinity_rating: int = 0
    rank: int = 0
    current_destiny: int = 0
    destiny_opponent: str = ''
    member_count: int = 0
    destiny_rank = 0
    ladder: str = ''
    icon: str = ''
    leaders: List[str] = dataclasses.field(default_factory=list)
    advisors: List[str] = dataclasses.field(default_factory=list)
    overflow: bool = False
    master_class: bool = False
    role_id: int = -1
    color: discord.Color = discord.Color.default()
    pool: int = 0
    wl: bool = False
    freeze: str = ''
    verify: bool = False
    strikes: int = 0
    total_slots: int = 0
    softcap_max: int = 0
    softcap_used: int = 0
    remaining_slots: int = 0
    decay_level: int = -1
    last_opp: str = ''
    last_match: datetime = None
    leader_ids: List[int] = dataclasses.field(default_factory=list)
    db_id: int = 0
    ranking: int = 0
    total_crews: int = 0
    destiny_opt_out: bool = False
    ranking_string = ''
    triforce = 0

    @property
    def embed(self) -> discord.Embed:
        title = f'{self.name}'
        if self.triforce == 1:
            title += f' (Triforce of Courage)'
        if self.triforce == 2:
            title += f' (Triforce of Power)'
        if self.overflow:
            title += f' (Overflow) '
        if self.wl:
            title += ' WATCHLISTED'
        description = [f'**Tag:** {self.abbr}\n', f'**Total Members:** {self.member_count}\n']

        # if self.trinity_rating:
        #     description.append(f'**Trinity Rating:** {self.trinity_rating}\n')
        if self.ladder:
            description.append(f'{self.ladder}: {self.ranking_string}\n')
        # if self.softcap_max:
        #     description.append(f'**Softcap:** {self.softcap_used}/{self.softcap_max}')
        #     description.append('\n')
        # description.append(f'**Destiny:** ')
        # if self.destiny_opt_out:
        #     description.append(f'Opted out\n')
        # else:
        #     meter = '' if self.destiny_opt_out else f'Meter {self.current_destiny}/100\n'
        #     description.append(f'Rank {self.destiny_rank} {meter}')
        # if self.destiny_opponent:
        #     description.append(f'**Destiny Opponent:** {self.destiny_opponent}\n')
        if self.last_opp:
            description.append(f'**Last Match:** {self.last_match.date().strftime("%m/%d/%y")} {self.last_opp}\n')
        if self.social:
            description.append(f'**Social:** {self.social}\n')
        if self.leaders:
            description.append(f'**Leaders:** ')
            for name in self.leaders:
                description.append(f'{name}, ')
            description[-1] = description[-1][:-2]
            description.append('\n')
        if self.advisors:
            description.append(f'**Advisors:** ')
            for name in self.advisors:
                description.append(f'{name}, ')
            description[-1] = description[-1][:-2]
            description.append('\n')
        if self.freeze:
            description.append(f'**Recruitment frozen till:** {self.freeze}\n')
        if self.verify:
            description.append('**Verify required for flairing**\n')
        if self.total_slots:
            description.append(f'**Flairing Slots:** {self.remaining_slots}/{self.total_slots}\n')
        embed = discord.Embed(title=title, description=''.join(description), color=self.color)
        if self.icon:
            embed.set_thumbnail(url=self.icon)
        return embed

    def fromDbCrew(self, db_crew: DbCrew):
        self.wl = db_crew.watch_listed
        self.verify = db_crew.verify
        if db_crew.freeze_date:
            self.freeze = db_crew.freeze_date.strftime('%m/%d/%Y')
        self.strikes = db_crew.strikes
        self.total_slots = db_crew.slots_total
        self.remaining_slots = db_crew.slots_left
        self.decay_level = db_crew.decay_level
        self.last_match = db_crew.last_battle
        self.last_opp = db_crew.last_opp
        self.db_id = db_crew.db_id
        self.softcap_max = db_crew.softcap_max
        self.softcap_used = db_crew.softcap_used
        self.current_destiny = db_crew.current_destiny
        self.destiny_opponent = db_crew.destiny_opponent
        self.destiny_rank = db_crew.destiny_rank
        self.destiny_opt_out = db_crew.destiny_opt_out
        self.member_count = db_crew.member_count
        self.triforce = db_crew.triforce

    def set_rankings(self, rank: int, rating: int, total: int):
        self.ladder = '**Trinity League:** '
        self.ladder += f'{rank}/{total}'
        self.ranking = rank
        self.total_crews = total
        self.trinity_rating = rating
