import string
from collections import defaultdict
from typing import List, Optional, Tuple
import discord
import asyncio
from enum import Enum
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO

from src.crew import Crew
from src.db_helpers import add_bracket_predictions, add_bracket_questions

ROUND_NAMES = ['Winners Round 1', 'Winners Quarterfinals', 'Winners Semi Finals', 'Winners Finals',
               'Losers Round 1', 'Losers Round 2', 'Losers Round 3', 'Losers Quarterfinals',
               'Losers Semi Finals', 'Losers Finals', 'Grand Finals', 'True Finals']

NUMBER_QUESTIONS = ['How many upsets will there be? (lower seed beating higher seed)',
                    'Final score of the Grand Finals? (If there is a reset, the reset will count)',
                    'Most stocks taken by a single player in a cb?',
                    'Biggest margin of victory in the playoffs? (Highest stocks left by the winning crew)',
                    'Most MVPs By a Single Player?',
                    'Will there be a bracket reset? (1 for yes, 0 for no)'
                    ]


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
    TRUE_FINALS = 12


PLACEMENTS = ['1st', '2nd', '3rd', '4th', '5th', '7th', '9th', '13th']


@dataclass
class Match:
    round: Round
    number: int
    crew_1: Optional[Crew] = None
    crew_2: Optional[Crew] = None
    winner_match: Optional['Match'] = None
    loser_match: Optional['Match'] = None
    winner: Optional[Crew] = None
    loser_placing: Optional[str] = None

    def add_crew(self, cr: Crew):
        if not self.crew_1:
            self.crew_1 = cr
        elif not self.crew_2:
            self.crew_2 = cr
        else:
            raise ValueError('Should be unreachable.')

    @property
    def loser(self) -> Optional[Crew]:
        if self.winner:
            if self.winner == self.crew_1:
                return self.crew_2
            return self.crew_1
        return None


class CrewSelectButton(discord.ui.Button['Bracket']):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label)

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: Bracket = self.view
        view.report_winner(self.label)
        await interaction.response.edit_message(content=view.message, view=view)


class ImageOutputButton(discord.ui.Button['Bracket']):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label='See Current')

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        await interaction.channel.send(file=draw_bracket(self.view.matches))
        # file = draw_bracket(self.view.matches)
        # embed = discord.Embed()
        # embed.set_image(url='attachment://bracket.png')
        # await interaction.message.edit(embed=embed, attachments=[file])


class DropdownQuestion(discord.ui.Select):
    def __init__(self, question: str):
        options = [discord.SelectOption(label=f'{i}', value=f'{i}') for i in range(24)]
        super().__init__(placeholder=question, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        self.view.new_question(self.values[0])
        await interaction.response.edit_message(content=NUMBER_QUESTIONS[self.view.current_question], view=self.view)


class Questions(discord.ui.View):
    children: List[DropdownQuestion]

    def __init__(self, author: discord.Member):
        super().__init__()
        self.author = author
        self.answers = []
        self.current_question = 0
        self.add_item(DropdownQuestion(NUMBER_QUESTIONS[self.current_question]))

    def new_question(self, answer: int):
        self.answers.append(answer)
        if self.current_question < len(NUMBER_QUESTIONS)-1:
            self.current_question += 1
            self.clear_items()
            self.add_item(DropdownQuestion(NUMBER_QUESTIONS[self.current_question]))
        else:
            add_bracket_questions(self.author.id, self.answers)
            out_str = ['Your extra predictions!']
            for i, question in enumerate(NUMBER_QUESTIONS):
                out_str.append(question + ': ' + self.answers[i])
            asyncio.create_task(self.author.send(content='\n'.join(out_str)))

            self.clear_items()
            self.stop()


class Bracket(discord.ui.View):
    children: List[CrewSelectButton]

    def __init__(self, crews: List[Crew], author: discord.Member, view_only: bool = False):
        super().__init__()
        self.view_only = view_only
        self.author = author
        self.author_id = author.id
        self.message = f'**{ROUND_NAMES[0]}**\n'
        self.matches = []
        self.placings = defaultdict(list)
        # Winners round 1
        for i in range(31):
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
            elif i == 30:
                rou = Round.TRUE_FINALS
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
            self.matches[i + 8].loser_placing = '13th'
        # WINNERS QUARTERS
        for i in range(4):
            self.matches[i + 12].loser_match = self.matches[19 - i]
            self.matches[i + 12].winner_match = self.matches[22 + i // 2]
        # LOSERS ROUND 2
        for i in range(4):
            self.matches[i + 16].winner_match = self.matches[20 + i // 2]
            self.matches[i + 16].loser_placing = '9th'
        # LOSERS ROUND 3
        for i in range(2):
            self.matches[i + 20].winner_match = self.matches[24 + i]
            self.matches[i + 20].loser_placing = '7th'
        # WINNERS SEMIS
        for i in range(2):
            self.matches[i + 22].winner_match = self.matches[27]
            self.matches[i + 22].loser_match = self.matches[24 + i]
        # LOSERS QUARTERS
        for i in range(2):
            self.matches[i + 24].winner_match = self.matches[26]
            self.matches[i + 24].loser_placing = '5th'
        # LOSERS SEMIS
        self.matches[26].winner_match = self.matches[28]
        self.matches[26].loser_placing = '4th'
        # WINNERS FINALS
        self.matches[27].winner_match = self.matches[29]
        self.matches[27].loser_match = self.matches[28]
        # LOSERS FINALS
        self.matches[28].winner_match = self.matches[29]
        self.matches[28].loser_placing = '3rd'
        # GRAND AND TRUE FINALS
        self.matches[29].winner_match = self.matches[30]
        self.matches[29].loser_match = self.matches[30]
        self.matches[29].loser_placing = '2nd'
        self.matches[30].loser_placing = '2nd'

        for i in range(8):
            self.matches[i].crew_1 = crews[i * 2]
            self.matches[i].crew_2 = crews[i * 2 + 1]
        self.current_match = 0
        self.new_match()

    @property
    def current(self) -> Match:
        if self.current_match < len(self.matches):
            return self.matches[self.current_match]
        else:
            return self.matches[len(self.matches) - 1]

    def new_match(self):
        if self.current_match < len(self.matches):
            self.add_item(CrewSelectButton(self.matches[self.current_match].crew_1.name))
            self.add_item(CrewSelectButton(self.matches[self.current_match].crew_2.name))
            self.add_item(ImageOutputButton())
        else:
            self.stop()
            for match in self.matches:
                print(f'{match.number} {match.crew_1.name} vs {match.crew_2.name} Winner: {match.winner.name}')
            if not self.view_only:
                add_bracket_predictions(self.author_id, self.matches)
            placement_str = ['Your predictions']
            for placement in PLACEMENTS:
                placement_str.append(placement + ' ' + ' \\| '.join(f'{cr.name}' for cr in self.placings[placement]))

            asyncio.create_task(self.author.send(content='\n'.join(placement_str), file=draw_bracket(self.matches)))

    def report_winner(self, name: str):
        if self.current.crew_1.name == name:
            self.current.winner = self.current.crew_1
            if self.current.round == Round.GRAND_FINALS:
                self.matches.pop()
            if self.current.round in (Round.GRAND_FINALS, Round.TRUE_FINALS):
                self.placings['1st'].append(self.current.crew_1)
            else:
                if self.current.winner_match:
                    self.current.winner_match.add_crew(self.current.crew_1)
                if self.current.loser_match:
                    self.current.loser_match.add_crew(self.current.crew_2)
            if self.current.loser_placing:
                self.placings[self.current.loser_placing].append(self.current.crew_2)

        else:
            if self.current.winner_match:
                self.current.winner_match.add_crew(self.current.crew_2)
            self.current.winner = self.current.crew_2
            if self.current.loser_match:
                self.current.loser_match.add_crew(self.current.crew_1)
            if self.current.loser_placing and self.current.round != Round.GRAND_FINALS:
                self.placings[self.current.loser_placing].append(self.current.crew_1)
            if self.current.round == Round.TRUE_FINALS:
                self.placings['1st'].append(self.current.crew_2)
        self.message += f'**{self.current.winner.name}** > {self.current.loser.name} \\|\\|'
        rou = self.current.round
        self.current_match += 1
        if rou != self.current.round:
            self.message += f'\n **{ROUND_NAMES[self.current.round.value - 1]}** \n'
        self.clear_items()
        self.new_match()


def draw_bracket(matches: List['Match']):
    response = requests.get(
        "https://cdn.discordapp.com/attachments"
        "/790736388634705940/890658443151679498/SCL2021MasterClassGraphicBracketBG.png")
    img = Image.open(BytesIO(response.content))

    d1 = ImageDraw.Draw(img)
    my_font = ImageFont.truetype('C:/Users/Jett/Fonts/SquadaOne-Regular.ttf', 32)
    logo_size = 50
    for i, match in enumerate(matches):
        if match.round == Round.WINNERS_ROUND_1:
            if match.crew_2:
                fill_color = (255, 255, 255) if match.crew_2.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((73, 55 + i * 73), match.crew_2.name, font=my_font, fill=match.crew_2.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.crew_1:
                fill_color = (255, 255, 255) if match.crew_1.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((73, 16 + i * 73), match.crew_1.name, font=my_font, fill=match.crew_1.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.winner == match.crew_1:
                d1.line([(72, 51 + i * 73), (262, 51 + i * 73), (262, 71 + i * 73)], fill=match.crew_1.color.to_rgb(),
                        width=14,
                        joint='curve')
            if match.winner == match.crew_2:
                d1.line([(72, 91 + i * 73), (262, 91 + i * 73), (262, 71 + i * 73)], fill=match.crew_2.color.to_rgb(),
                        width=14,
                        joint='curve')
        if match.round == Round.LOSERS_ROUND_1:
            round_i = i - 8
            difference = round_i * 98
            if match.crew_2:
                fill_color = (255, 255, 255) if match.crew_2.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((73, 714 + difference), match.crew_2.name, font=my_font, fill=match.crew_2.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.crew_1:
                fill_color = (255, 255, 255) if match.crew_1.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((73, 672 + difference), match.crew_1.name, font=my_font, fill=match.crew_1.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(72, 708 + difference), (262, 708 + difference), (262, 729 + difference)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(72, 750 + difference), (262, 750 + difference), (262, 729 + difference)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.WINNERS_QUARTERS:
            round_i = i - 12
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(255, 71 + round_i * 144), (442, 71 + round_i * 144), (442, 107 + round_i * 144)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(255, 144 + round_i * 144), (442, 144 + round_i * 144), (442, 107 + round_i * 144)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')

        if match.round == Round.LOSERS_ROUND_2:
            round_i = i - 16
            difference = round_i * 98
            if match.crew_2:
                fill_color = (255, 255, 255) if match.crew_2.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((265, 637 + difference), match.crew_2.name, font=my_font, fill=match.crew_2.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.winner:
                if match.winner == match.crew_2:
                    d1.line([(255, 673 + difference), (442, 673 + difference), (442, 703 + difference)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
                    # response = requests.get(match.crew_1.icon)
                    # logo = Image.open(BytesIO(response.content))
                    # logo = logo.resize((logo_size, logo_size))
                    # img.paste(logo, (255 - logo_size // 2, 730 + difference - logo_size // 2), logo.convert('RGBA'))
                if match.winner == match.crew_1:
                    d1.line([(255, 730 + difference), (442, 730 + difference), (442, 703 + difference)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')

        if match.round == Round.WINNERS_SEMIS:
            round_i = i - 22
            difference = round_i * 290
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(436, 107 + difference), (623, 107 + difference), (623, 174 + difference)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(436, 253 + difference), (623, 253 + difference), (623, 174 + difference)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.WINNERS_FINALS:
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(617, 174), (986, 174), (986, 293)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(617, 469), (986, 469), (986, 293)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.GRAND_FINALS:
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(980, 293), (1346, 293), (1346, 493), (1545, 493)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                    response = requests.get(match.crew_1.icon)
                    logo = Image.open(BytesIO(response.content))
                    logo = logo.resize((300, 300))
                    img.paste(logo, (1545-150, 493-150), logo.convert('RGBA'))
                if match.winner == match.crew_2:
                    d1.line([(1162, 723), (1346, 723), (1346, 493)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.TRUE_FINALS:
            if match.crew_2:
                fill_color = (255, 255, 255) if match.crew_2.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((1344, 918), match.crew_2.name, font=my_font, fill=match.crew_2.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(1340, 493), (1545, 493), (1545, 720), (1738, 720)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')

                    response = requests.get(match.crew_1.icon)
                    logo = Image.open(BytesIO(response.content))
                    logo = logo.resize((300, 300))
                    img.paste(logo, (1738-150, 720-150), logo.convert('RGBA'))

                if match.winner == match.crew_2:
                    d1.line([(1344, 956), (1545, 956), (1545, 720), (1738, 720)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')

                    response = requests.get(match.crew_2.icon)
                    logo = Image.open(BytesIO(response.content))
                    logo = logo.resize((300, 300))
                    img.paste(logo, (1738-150, 720-150), logo.convert('RGBA'))
        if match.round == Round.LOSERS_ROUND_3:
            round_i = i - 20
            difference = round_i * 195
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(436, 703 + difference), (623, 703 + difference), (623, 752 + difference)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(436, 801 + difference), (623, 801 + difference), (623, 752 + difference)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.LOSERS_QUARTERS:
            round_i = i - 24
            if match.crew_2:
                fill_color = (255, 255, 255) if match.crew_2.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((620, 612 + round_i * 400), match.crew_2.name, font=my_font, fill=match.crew_2.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.winner:
                if match.winner == match.crew_1:
                    difference = 193 * round_i
                    d1.line([(617, 752 + difference), (804, 752 + difference), (804, 699 + round_i * 294)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    difference = 400 * round_i
                    d1.line([(617, 649 + difference), (804, 649 + difference), (804, 699 + round_i * 294)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.LOSERS_SEMIS:
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(799, 702), (986, 702), (986, 842)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(799, 996), (986, 996), (986, 842)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
        if match.round == Round.LOSERS_FINALS:
            if match.crew_2:
                fill_color = (255, 255, 255) if match.crew_2.name in (
                    'Black Gang', 'Black Halo', 'Flow State Gaming', 'Dream Casters', 'Wombo Combo') else (0, 0, 0)
                d1.text((986, 567), match.crew_2.name, font=my_font, fill=match.crew_2.color.to_rgb(),
                        stroke_width=1, stroke_fill=fill_color)
            if match.winner:
                if match.winner == match.crew_1:
                    d1.line([(982, 843), (1168, 843), (1168, 723)],
                            fill=match.crew_1.color.to_rgb(),
                            width=14,
                            joint='curve')
                if match.winner == match.crew_2:
                    d1.line([(982, 603), (1168, 603), (1168, 723)],
                            fill=match.crew_2.color.to_rgb(),
                            width=14,
                            joint='curve')
    buffer = BytesIO()
    img.save(buffer, 'png')
    buffer.seek(0)
    return discord.File(fp=buffer, filename='bracket.png')
