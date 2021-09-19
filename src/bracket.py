import string
from typing import List
import discord

from src.crew import Crew

ROUND_NAMES = ['Winners round 1', 'Winners Quarterfinals', 'Winners Semi Finals', 'Winners Finals']


class CrewSelectButton(discord.ui.Button['Bracket']):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label)

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: Bracket = self.view
        view.message += f'{self.label} '
        view.clear_items()
        view.matches.pop(0)
        view.winners.append(self.label)
        view.new_match()
        await interaction.response.edit_message(content=view.message, view=view)


class Bracket(discord.ui.View):
    children: List[CrewSelectButton]

    def __init__(self, crews: List[Crew]):
        super().__init__()
        self.message = f'**{ROUND_NAMES[0]}**\n'
        self.matches = []
        for i in range(0, len(crews) - 1, 2):
            self.matches.append((crews[i], crews[i + 1]))
        self.new_match()
        self.winners = []
        self.round_number = 0

    def new_match(self):
        if not self.matches:
            self.round_number += 1
            if self.round_number >= len(ROUND_NAMES):
                self.message += '\nDone'
                self.stop()
                return
            self.message += f'\n**{ROUND_NAMES[self.round_number]}**\n'
            for i in range(0, len(self.winners) - 1, 2):
                self.matches.append((self.winners[i], self.winners[i + 1]))
            self.winners.clear()
        if self.matches:
            self.add_item(CrewSelectButton(self.matches[0][0].name))
            self.add_item(CrewSelectButton(self.matches[0][1].name))

