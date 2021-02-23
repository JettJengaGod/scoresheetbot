import dataclasses
import discord


@dataclasses.dataclass
class Gambit:
    team1: str
    team2: str
    locked: bool
    message_id: int
    bets_1: int = 0
    bets_2: int = 0

    @property
    def odds_1(self) -> str:
        if not self.bets_1:
            return 'N/A'
        return '1:{:.2}'.format(self.bets_2/self.bets_1)

    @property
    def odds_2(self) -> str:
        if not self.bets_1:
            return 'N/A'
        return '1:{:.2}'.format(self.bets_1/self.bets_2)

    def embed(self) -> discord.Embed:
        title = f'{self.team1} vs {self.team2}'
        color = discord.Color.red() if self.locked else discord.Color.green()
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name=f'{self.team1} bets', value=str(self.bets_1), inline=True)
        embed.add_field(name=f'{self.team2} bets', value=str(self.bets_2), inline=True)
        embed.add_field(name=f'Current odds',
                        value=f'{self.team1} {self.odds_1} {self.team2}\n{self.team2} {self.odds_2} {self.team1}',
                        inline=False)
        return embed

    def __str__(self):
        return f'{self.team1} vs {self.team2}\n {self.bets_1} - {self.bets_2}'
