import dataclasses
import discord
from typing import List


@dataclasses.dataclass
class Crew:
    name: str
    abbr: str
    social: str = ''
    rank: str = ''
    merit: int = 0
    leaders: List[str] = dataclasses.field(default_factory=list)
    advisers: List[str] = dataclasses.field(default_factory=list)
    overflow: bool = False
    color: discord.Color = None

    @property
    def embed(self) -> discord.Embed:
        title = f'{self.name}'
        if self.overflow:
            title += f' (Overflow) '
        if self.rank:
            title += f' {self.rank}'
        description = [f'Tag: {self.abbr}\n']
        if self.social:
            description.append(f'Social: {self.social}\n')
        if self.leaders:
            description.append(f'Leaders: ')
            for name in self.leaders:
                description.append(f'{name}, ')
            description[-1] = description[-1][:-2]
            description.append('\n')
        if self.advisers:
            description.append(f'Advisers: ')
            for name in self.advisers:
                description.append(f'{name}, ')
            description[-1] = description[-1][:-2]
            description.append('\n')
        description.append(f'Merit: {self.merit}')
        return discord.Embed(title=title, description=''.join(description),color=self.color)
