import dataclasses
import discord
import math
from typing import Tuple, List


@dataclasses.dataclass
class Gambit:
    team1: str
    team2: str
    locked: bool
    message_id: int
    bets_1: int = 0
    bets_2: int = 0
    top_1: Tuple[str, int] = ()
    top_2: Tuple[str, int] = ()

    @property
    def odds_1(self) -> str:
        if not self.bets_1:
            return 'N/A (No bets)'
        return '**{:.3}x**'.format(self.bets_2 / self.bets_1)

    @property
    def odds_2(self) -> str:
        if not self.bets_2:
            return 'N/A (No bets)'
        return '**{:.3}x**'.format(self.bets_1 / self.bets_2)

    def embed(self, c1_tag, c2_tag) -> discord.Embed:
        title = f'{self.team1} vs {self.team2}'
        color = discord.Color.red() if self.locked else discord.Color.green()
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name=f'{c1_tag}', value=f'{self.bets_1}G-Coins', inline=True)
        embed.add_field(name=f'{c2_tag}', value=f'{self.bets_2}G-Coins', inline=True)
        embed.add_field(name=f'Current odds',
                        value=f'{self.team1}: {self.odds_1}\n{self.team2}:{self.odds_2}',
                        inline=False)

        if self.locked:
            embed.add_field(name='Current Status', value='Locked')
        if self.top_1:
            embed.add_field(name=f'{c1_tag} top bet', value=f'{self.top_1[0]}: {self.top_1[1]}')
        if self.top_2:
            embed.add_field(name=f'{c2_tag} top bet', value=f'{self.top_2[0]}: {self.top_2[1]}')

        return embed

    def finished_embed(self, c1_tag: str, c2_tag: str, winner: int, top_win: Tuple[int, str],
                       top_loss: Tuple[int, str]) -> discord.Embed:
        if winner == 1:
            winning_team = self.team1
            losing_team = self.team2
        else:
            winning_team = self.team2
            losing_team = self.team1

        title = f'{winning_team} beat {losing_team}'
        color = discord.Color.dark_gold()
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name=f'{c1_tag}', value=f'{self.bets_1}G-Coins', inline=True)
        embed.add_field(name=f'{c2_tag}', value=f'{self.bets_2}G-Coins', inline=True)
        embed.add_field(name=f'Final odds',
                        value=f'{self.team1} {self.odds_1} {self.team2}\n{self.team2} {self.odds_2} {self.team1}',
                        inline=False)
        if top_win:
            embed.add_field(name=f'Top Winner',
                            value=f'{top_win[1]}: {top_win[0]}')
        if top_loss:
            embed.add_field(name=f'Most Lost', value=f'{top_loss[1]}: {top_loss[0]}')

        embed.add_field(name='Current Status', value='finished')

        return embed

    def __str__(self):
        return f'{self.team1} vs {self.team2}\n {self.bets_1} - {self.bets_2}'
