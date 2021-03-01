import dataclasses
import discord
from typing import List
from constants import PlayoffType
from datetime import datetime


@dataclasses.dataclass
class Crew:
    name: str
    abbr: str
    social: str = ''
    rank: int = 0
    merit: int = 0
    member_count: int = 0
    ladder: str = ''
    icon: str = ''
    leaders: List[str] = dataclasses.field(default_factory=list)
    advisors: List[str] = dataclasses.field(default_factory=list)
    overflow: bool = False
    role_id: int = -1
    color: discord.Color = discord.Color.default()
    playoff: PlayoffType = PlayoffType.NO_PLAYOFF
    pool: int = 0
    wl: bool = False
    freeze: str = ''
    verify: bool = False
    strikes: int = 0
    total_slots: int = 0
    remaining_slots: int = 0

    @property
    def embed(self) -> discord.Embed:
        title = f'{self.name}'
        if self.overflow:
            title += f' (Overflow) '
        if self.rank:
            title += f'Qualifier {self.rank}'
        if self.wl:
            title += ' WATCHLISTED'
        description = [f'Tag: {self.abbr}\n', f'Total Members: {self.member_count}\n']
        if self.playoff != PlayoffType.NO_PLAYOFF:
            description.append(f'Playoff: {self.playoff.name}\n')
        if self.ladder:
            description.append(f'Qualifiers Current Placement: {self.ladder}\n')
        if self.social:
            description.append(f'Social: {self.social}\n')
        if self.leaders:
            description.append(f'Leaders: ')
            for name in self.leaders:
                description.append(f'{name}, ')
            description[-1] = description[-1][:-2]
            description.append('\n')
        if self.advisors:
            description.append(f'Advisors: ')
            for name in self.advisors:
                description.append(f'{name}, ')
            description[-1] = description[-1][:-2]
            description.append('\n')
        description.append(f'Merit: {self.merit}')
        if self.freeze:
            description.append(f'\nRecruitment frozen till: {self.freeze}')
        if self.verify:
            description.append('\nVerify required for flairing')
        if self.total_slots:
            description.append(f'\nFlairing Slots: {self.remaining_slots}/{self.total_slots}')
        embed = discord.Embed(title=title, description=''.join(description), color=self.color)
        if self.icon:
            embed.set_thumbnail(url=self.icon)
        return embed

    def dbattr(self, wl: bool, freeze: datetime, verify: bool, strikes: int, total: int, remaining: int):
        self.wl = wl
        self.verify = verify
        if freeze:
            self.freeze = freeze.strftime('%m/%d/%Y')
        self.strikes = strikes
        self.total_slots = total
        self.remaining_slots = remaining
