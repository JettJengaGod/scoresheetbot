import string
from typing import List, Optional, Tuple
import discord
from enum import Enum
from dataclasses import dataclass

from src.crew import Crew

ROUND_NAMES = ['Winners Round 1', 'Winners Quarterfinals', 'Winners Semi Finals', 'Winners Finals',
               'Losers Round 1', 'Losers Round 2', 'Losers Round 3', 'Losers Quarterfinals',
               'Losers Semi Finals', 'Losers Finals', 'Grand Finals']


class Round(Enum):
    WINNERS_ROUND_1 = 1
    WINNERS_QUARTERS = 2
    WINNERS_SEMIS = 3
    WINNERS_FINALS = 4
    LOSERS_ROUND_1 = 5
    LOSERS_ROUND_2 = 6
    LOSERS_ROUND_3 = 7
    LOSERS_QUARTERS = 8
    LOSERS_SEMIS = 9
    LOSERS_FINALS = 10
    GRAND_FINALS = 11


@dataclass
class Match:
    round: Round
    number: int
    crew_1: Optional[Crew] = None
    crew_2: Optional[Crew] = None
    winner_match: Optional['Match'] = None
    loser_match: Optional['Match'] = None
    winner: Optional[Crew] = None

    def add_crew(self, cr: Crew):
        if not self.crew_1:
            self.crew_1 = cr
        elif not self.crew_2:
            self.crew_2 = cr
        else:
            raise ValueError('Should be unreachable.')


class CrewSelectButton(discord.ui.Button['Bracket']):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label)

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: Bracket = self.view
        view.report_winner(self.label)
        await interaction.response.edit_message(content=view.message, view=view)


class Bracket(discord.ui.View):
    children: List[CrewSelectButton]

    def __init__(self, crews: List[Crew]):
        super().__init__()
        self.message = f'**{ROUND_NAMES[0]}**\n'
        self.matches = []
        # Winners round 1
        for i in range(30):
            if i < 8:
                rou = Round.WINNERS_ROUND_1
            elif i < 12:
                rou = Round.LOSERS_ROUND_1
            elif i < 16:
                rou = Round.WINNERS_QUARTERS
            elif i < 20:
                rou = Round.LOSERS_ROUND_2
            elif i < 22:
                rou = Round.LOSERS_ROUND_3
            elif i < 24:
                rou = Round.WINNERS_SEMIS
            elif i < 26:
                rou = Round.LOSERS_QUARTERS
            elif i == 26:
                rou = Round.LOSERS_SEMIS
            elif i == 27:
                rou = Round.WINNERS_FINALS
            elif i == 28:
                rou = Round.LOSERS_FINALS
            elif i == 29:
                rou = Round.GRAND_FINALS
            else:
                rou = Round.WINNERS_ROUND_1
            self.matches.append(Match(rou, i))
        # WINNERS ROUND 1
        for i in range(8):
            self.matches[i].loser_match = self.matches[8 + i // 2]
            self.matches[i].winner_match = self.matches[12 + i // 2]
        # LOSERS ROUND 1
        for i in range(4):
            self.matches[i + 8].winner_match = self.matches[16 + i]
        # WINNERS QUARTERS
        for i in range(4):
            self.matches[i + 12].loser_match = self.matches[19 - i]
            self.matches[i + 12].winner_match = self.matches[22 + i // 2]
        # LOSERS ROUND 2
        for i in range(4):
            self.matches[i + 16].winner_match = self.matches[20 + i // 2]
        # LOSERS ROUND 3
        for i in range(2):
            self.matches[i + 20].winner_match = self.matches[24 + i]
        # WINNERS SEMIS
        for i in range(2):
            self.matches[i + 22].winner_match = self.matches[27]
            self.matches[i + 22].loser_match = self.matches[24 + i]
        # LOSERS QUARTERS
        for i in range(2):
            self.matches[i + 24].winner_match = self.matches[26]
        # LOSERS SEMIS
        self.matches[26].winner_match = self.matches[28]
        # WINNERS FINALS
        self.matches[27].winner_match = self.matches[29]
        self.matches[27].loser_match = self.matches[28]
        # LOSERS FINALS
        self.matches[28].winner_match = self.matches[29]

        for i in range(8):
            self.matches[i].crew_1 = crews[i*2]
            self.matches[i].crew_2 = crews[i*2 + 1]
        self.current_match = 0
        self.new_match()

    @property
    def current(self) -> Match:
        if self.current_match < len(self.matches):
            return self.matches[self.current_match]
        else:
            return self.matches[len(self.matches)-1]

    def new_match(self):
        if self.current_match < len(self.matches):
            self.add_item(CrewSelectButton(self.matches[self.current_match].crew_1.name))
            self.add_item(CrewSelectButton(self.matches[self.current_match].crew_2.name))
        else:
            for match in self.matches:
                print(f'{match.number} {match.crew_1.name} vs {match.crew_2.name} Winner: {match.winner.name}')
            self.stop()

    def report_winner(self, name: str):
        if self.current.crew_1.name == name:
            if self.current.winner_match:
                self.current.winner_match.add_crew(self.current.crew_1)
            self.current.winner = self.current.crew_1
            if self.current.loser_match:
                self.current.loser_match.add_crew(self.current.crew_2)
        else:
            if self.current.winner_match:
                self.current.winner_match.add_crew(self.current.crew_2)
            self.current.winner = self.current.crew_2
            if self.current.loser_match:
                self.current.loser_match.add_crew(self.current.crew_1)
        self.message += f'{self.current.winner.name} '
        rou = self.current.round
        self.current_match += 1
        if rou != self.current.round:
            self.message += f'\n **{ROUND_NAMES[self.current.round.value-1]}** \n'
        self.clear_items()
        self.new_match()

