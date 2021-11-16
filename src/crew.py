import dataclasses
import discord
from typing import List
from datetime import datetime


@dataclasses.dataclass
class Crew:
    name: str
    abbr: str
    social: str = ''
    scl_rating: int = 0
    overclocked_ranking: int = 0
    rank: int = 0
    current_umbra: int = 0
    max_umbra: int = 0
    member_count: int = 0
    rank_up: str = ''
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
    remaining_slots: int = 0
    decay_level: int = -1
    last_opp: str = ''
    last_match: datetime = None
    leader_ids: List[int] = dataclasses.field(default_factory=list)
    db_id: int = 0

    @property
    def embed(self) -> discord.Embed:
        title = f'{self.name} (Rank: {self.rank})'
        # if self.master_class:
        #     title += f' (Master Class) '
        if self.overflow:
            title += f' (Overflow) '
        if self.wl:
            title += ' WATCHLISTED'
        description = [f'**Tag:** {self.abbr}\n', f'**Total Members:** {self.member_count}\n']
        # if self.ladder:
        #     description.append(f'{self.ladder}\n')
        # if self.scl_rating:
        #     description.append(f'**SCL Rating:** {self.scl_rating}\n')
        if self.max_umbra:
            description.append(f'**Umbra Meter:** {self.current_umbra}/{self.max_umbra}\n')
        if self.current_umbra >= self.max_umbra:
            description.append(f'**Rank up Opponent:** {self.rank_up}\n')
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

    def dbattr(self, wl: bool, freeze: datetime, verify: bool, strikes: int, total: int, remaining: int, master: bool,
               decay: int, finished: datetime, last_opp: str, db_id: int):
        self.wl = wl
        self.verify = verify
        if freeze:
            self.freeze = freeze.strftime('%m/%d/%Y')
        self.strikes = strikes
        self.total_slots = total
        self.remaining_slots = remaining
        self.master_class = master
        self.decay_level = decay
        self.last_match = finished
        self.last_opp = last_opp
        self.db_id = db_id

    def set_rankings(self, rank: int, rating: int, bf: bool, total: int):
        self.ladder = '**Battle Frontier:** ' if bf else '**Rookie Class:** '
        self.ladder += f'{rank}/{total}'
        self.scl_rating = rating
