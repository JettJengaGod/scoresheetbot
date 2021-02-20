import dataclasses


@dataclasses.dataclass
class Gambit:
    team1: str
    team2: str
    locked: bool
    bets_1: int = 0
    bets_2: int = 0

    def __str__(self):
        return f'{self.team1} vs {self.team2}\n {self.bets_1} - {self.bets_2}'
