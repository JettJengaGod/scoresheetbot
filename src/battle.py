from dataclasses import dataclass, field
from character import Character
from enum import Enum
from typing import Optional, Set, List
from discord import embeds, colour
from datetime import datetime
import random


class StateError(Exception):
    """ Raised When the state of the program is incompatible with the given command."""

    def __init__(self, battle, message: str):
        self.battle = battle
        self.message = message


PLAYER_STOCKS = 3
DEFAULT_SIZE = 5


def bold(s: str) -> str:
    return f'**{s}**'


class BattleType(Enum):
    RANKED = 1
    MOCK = 2
    REG = 3
    PLAYOFF = 4
    MASTER = 5
    MASTER_PLAYOFF = 6
    BF_PLAYOFF = 7
    RC_PLAYOFF = 8
    SH_PLAYOFF = 9
    COWY = 10
    OC_PLAYOFF = 11
    DESTINY = 12
    MIDSEASON = 13
    TRINITY_PLAYOFF = 14
    ARCADE = 15
    WISDOM = 16
    COURAGE = 17
    POWER = 18


class Difficulty(Enum):
    EASY = 1
    NORMAL = 2
    HARD = 3
    UNSET = 4
    BOSS = 5


@dataclass
class Player:
    name: str
    team_name: str
    taken: int = 0
    left: int = PLAYER_STOCKS
    char: Character = Character('', bot=None)
    id: int = 0

    def set_char(self, char: Character) -> None:
        self.char = char

    def __str__(self) -> str:
        return f'{self.name} {self.char}'


@dataclass
class Team:
    name: str
    num_players: int
    stocks: int
    players: List[Player] = field(default_factory=list)
    leader: Set[str] = field(default_factory=set)
    current_player: Optional[Player] = None
    ext_used: bool = False
    replaced: Set[str] = field(default_factory=set)
    difficulty: Difficulty = Difficulty.UNSET

    def add_player(self, player_name: str, player_id: Optional[int]) -> None:
        if self.current_player:
            raise StateError(None,
                             f"This team already has a current player, {self.current_player.name}, use \",replace\" "
                             f"to replace them")
        self.current_player = Player(name=player_name, team_name=self.name, id=player_id)
        self.players.append(self.current_player)

    def check_resend(self, player_id: id):
        if len(self.players) >= 4:
            return
        for player in self.players:
            if player_id == player.id and player.name not in self.replaced:
                raise StateError(None,
                                 f'{self.name} has only played {len(self.players)} unique players and must send '
                                 f' at least 4 unique players before resending someone.')

    def replace_current(self, player_name: str, player_id: Optional[int] = 0) -> str:
        current_stocks = PLAYER_STOCKS
        current = ''
        if self.current_player:
            current_stocks = self.current_player.left
            current = self.current_player.name
            if self.current_player.left == PLAYER_STOCKS and self.current_player.taken == 0:
                self.players.pop()
            else:
                self.replaced.add(player_name)
        self.current_player = Player(name=player_name, team_name=self.name, left=current_stocks, id=player_id)
        self.players.append(self.current_player)

        return f'{self.name} subbed {current}  with {player_name} with {current_stocks} stocks left.'

    def timer_stock(self):
        if self.current_player:
            if self.current_player.left == 0:
                raise ValueError('You can\'t lose a stock to the timer if you don\'t have any left.')
            self.current_player.left -= 1
            self.stocks -= 1
            if self.current_player.left == 0:
                self.current_player = None
        else:
            raise ValueError('No current player.')

    def match_finish(self, lost: int, took: int):
        self.current_player.left -= lost
        self.current_player.taken += took
        self.stocks -= lost
        if self.current_player.left == 0:
            self.current_player = None

    def undo_match(self, lost: int, took: int, player: Player):
        if not self.current_player:
            self.current_player = player
        elif self.current_player != player:
            self.players.pop()
            self.current_player = player
        self.current_player.left += lost
        self.current_player.taken -= took
        self.stocks += lost

    def mvp(self) -> List[Player]:
        highest = 0
        ret = []
        for player in self.players:
            if player.taken > highest:
                ret = [player]
                highest = player.taken
            elif player.taken == highest:
                ret.append(player)
        return ret

    def mvp_parse(self) -> str:
        players = ''
        for player in self.mvp():
            players += f'**{str(player)}**, '
        return f'MVP for **{self.name}** was {players[:-2]} with {self.mvp()[0].taken} stocks'

    def current_status(self) -> str:
        if self.current_player:
            ret = f'{str(self.current_player)} {self.current_player.left} stocks'
            return ret
        return 'Waiting'


@dataclass
class Match:
    p1: Player
    p2: Player
    p1_taken: int
    p2_taken: int
    winner: int

    def __str__(self):
        p1 = f'[{self.p1.char}]{self.p1.name} ({self.p1_taken})'
        p2 = f'({self.p2_taken}) {self.p2.name} [{self.p2.char}]'
        if self.winner == 1:
            p1 = bold(p1)
        else:
            p2 = bold(p2)
        return f'{p1} <a:vs:775901296171155456> {p2}'

    def __eq__(self, other):
        return (
                   self.p1.name, self.p2.name, self.p1_taken, self.p2_taken, self.winner, self.p1.char.emoji,
                   self.p2.char.emoji
               ) == (
                   other.p1.name, other.p2.name, other.p1_taken, other.p2_taken, other.winner, other.p1.char.emoji,
                   other.p2.char.emoji
               )


class InfoMatch(Match):
    def __init__(self, info: str):
        self.info: str = info

    def __str__(self):
        return self.info


class TimerMatch(Match):
    def __init__(self, player: Player, team: Team):
        self.player = player
        self.team = team

    def __str__(self):
        return f'{self.player.name} on {self.team.name} lost a stock to the timer.'


class ForfeitMatch(Match):
    def __init__(self, team: Team, stocks: int):
        self.stocks = stocks
        self.team = team

    def __str__(self):
        return f'{self.team.name} forfeited with {self.stocks} left.'


class Battle:
    def __init__(self, name1: str, name2: str, players: int, battle_type: BattleType = BattleType.ARCADE):
        self.team1 = Team(name1, players, players * PLAYER_STOCKS)
        self.team2 = Team(name2, players, players * PLAYER_STOCKS)
        self.teams = (self.team1, self.team2)
        self.matches = []
        self.confirms = [False, False]
        self.id = 'Not Set, use `,arena ID/PASS` to set '
        self.stream = 'Not Set, use `,stream STREAMLINKHERE` to set '
        self.color = colour.Color.from_rgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        self.time = datetime.now()
        self.battle_type = battle_type
        if self.battle_type == BattleType.MASTER:
            self.header = 'Master Class '
        elif self.battle_type == BattleType.MOCK:
            self.header = 'Mock '
        elif self.battle_type == BattleType.REG:
            self.header = 'Registration '
        elif self.battle_type == BattleType.OC_PLAYOFF:
            self.header = 'Overclocked Playoff '
        elif self.battle_type == BattleType.COWY:
            self.header = 'Cowy Random Playoff '
        elif self.battle_type == BattleType.SH_PLAYOFF:
            self.header = 'Straw Hat Invitational '
        elif self.battle_type == BattleType.DESTINY:
            self.header = 'Destiny '
        elif self.battle_type == BattleType.MIDSEASON:
            self.header = 'Midseason Playoff'
        elif self.battle_type == BattleType.TRINITY_PLAYOFF:
            self.header = 'Trinity Playoff '
        elif self.battle_type == BattleType.ARCADE:
            self.header = 'Arcade '
        else:
            self.header = ''

    def set_difficulty(self, team_name: str, difficulty: Difficulty):
        team = self.lookup(team_name)
        if self.battle_type == BattleType.ARCADE:
            if team.difficulty == Difficulty.UNSET:
                team.difficulty = difficulty

    def check_difficulty(self, team_name: str) -> Difficulty:
        team = self.lookup(team_name)
        if self.battle_type == BattleType.ARCADE:
            return team.difficulty

    def ready_for_countdown(self) -> bool:
        # if self.battle_type != BattleType.ARCADE:
        #     return True
        # if self.team1.difficulty == Difficulty.UNSET or self.team2.difficulty == Difficulty.UNSET:
        #     return False
        return True

    def confirmed(self) -> bool:
        return all(self.confirms)

    def match_ready(self) -> bool:
        return all(t.current_player for t in self.teams)

    def lookup(self, team_name: str) -> Team:
        for team in self.teams:
            if team_name == team.name:
                return team
        raise StateError(self, f"Team \"{team_name}\" does not exist.")

    def add_player(self, team_name: str, player_name: str, leader: str, player_id: Optional[int] = 0) -> None:
        team = self.lookup(team_name)
        if self.battle_type != BattleType.MOCK:
            team.check_resend(player_id)
        # if self.battle_type == BattleType.ARCADE:
        #     if team.difficulty == Difficulty.UNSET:
        #         raise StateError(self, f'Team "{team.name}" needs to set difficulty with `,difficulty`')
        team.add_player(player_name, player_id)
        team.leader.add(leader)

    def forfeit(self, team_name: str):
        team = self.lookup(team_name)
        current = team.stocks
        team.stocks = 0
        self.matches.append(ForfeitMatch(team, current))

    def ext_used(self, team_name: str) -> bool:
        team = self.lookup(team_name)
        ext = team.ext_used
        if ext:
            return True
        else:
            self.matches.append(InfoMatch(info=f'{team_name} used their extension'))
            team.ext_used = True
            return False

    def team_from_member(self, leader: str) -> Optional[str]:
        if leader in self.team1.leader:
            return self.team1.name
        if leader in self.team2.leader:
            return self.team2.name
        return None

    def ext_str(self) -> str:
        return f'Teams extension status:\n' \
               f'{self.team1.name} Extension used: {self.team1.ext_used}\n' \
               f'{self.team2.name} Extension used: {self.team2.ext_used}'

    def replace_player(self, team_name: str, player_name: str, leader: str, player_id: Optional[int] = 0) -> None:
        team = self.lookup(team_name)
        if self.battle_type != BattleType.MOCK:
            team.check_resend(player_id)
        info = team.replace_current(player_name, player_id)
        team.leader.add(leader)
        self.matches.append(InfoMatch(info=info))

    def timer_stock(self, team_name: str, leader: str) -> None:
        team = self.lookup(team_name)
        player = team.current_player
        team.timer_stock()
        team.leader.add(leader)
        self.matches.append(TimerMatch(player=player, team=team))

    def finish_match(self, taken1: int, taken2: int, char1: Character, char2: Character) -> Match:
        if not self.match_ready():
            not_ready = []
            for team in self.teams:
                if not team.current_player:
                    not_ready.append(team.name)
            raise StateError(self, f'The match is not ready yet, {not_ready} still need players')
        p1 = self.team1.current_player
        p1.set_char(char1)
        p2 = self.team2.current_player
        p2.set_char(char2)
        if not (p1.left == taken2 or p2.left == taken1):
            raise StateError(self, f'Game ended incorrectly,\n'
                                   f' {p1.name} has {p1.left} stocks {p2.name} has {p2.left} stocks')
        winner = 1 if taken1 == p2.left else 2
        if taken2 >= p1.left and taken1 >= p2.left:
            raise StateError(self, f'Both players can\'t win the game. Please try again. '
                                   f' {p1.name} has {p1.left} stocks {p2.name} has {p2.left} stocks')
        match = Match(p1, p2, taken1, taken2, winner)
        self.matches.append(match)
        self.team1.match_finish(taken2, taken1)
        self.team2.match_finish(taken1, taken2)
        self.time = datetime.now()
        return match

    def finish_lag(self, taken1: int, taken2: int, char1: Character, char2: Character) -> Match:
        if not self.match_ready():
            not_ready = []
            for team in self.teams:
                if not team.current_player:
                    not_ready.append(team.name)
            raise StateError(self, f'The match is not ready yet, {not_ready} still need players')
        p1 = self.team1.current_player
        p1.set_char(char1)
        p2 = self.team2.current_player
        p2.set_char(char2)
        if p1.left == taken2 or p2.left == taken1:
            raise StateError(self, f'Game ended normally,\n'
                                   f' use the normal end command.')
        winner = 1
        if taken2 > p1.left or taken1 > p2.left:
            raise StateError(self, f'You can\'t take more stocks than a player has. '
                                   f' {p1.name} has {p1.left} stocks {p2.name} has {p2.left} stocks')
        match = Match(p1, p2, taken1, taken2, winner)
        self.matches.append(match)
        self.team1.match_finish(taken2, taken1)
        self.team2.match_finish(taken1, taken2)
        info = InfoMatch('Previous match ended due to lag ignore the winner.')
        self.matches.append(info)
        self.time = datetime.now()
        return match

    def timer(self) -> str:

        past = datetime.now() - self.time
        mins = 's' if past.seconds >= 120 else ''
        minutes = '' if past.seconds < 60 else f'{past.seconds // 60} minute{mins} and '
        end = 'the match finished.' if len(self.matches) else 'the crew battle started.'
        second = 'second' if past.seconds % 60 == 1 else 'seconds'
        return f'It has been {minutes}{past.seconds % 60} {second} since {end}'

    def confirm(self, team: str) -> None:
        if team == self.team1.name:
            self.confirms[0] = not self.confirms[0]

        if team == self.team2.name:
            self.confirms[1] = not self.confirms[1]

    def battle_over(self):
        return any(t.stocks == 0 for t in self.teams)

    def winner(self) -> Team:
        if self.battle_over():
            return self.team1 if self.team2.stocks == 0 else self.team2
        raise StateError(self, "This should not be reachable")

    def loser(self) -> Team:
        if self.battle_over():
            return self.team2 if self.team2.stocks == 0 else self.team1
        raise StateError(self, "This should not be reachable")

    def resize(self, new_size: int) -> None:
        if new_size < max((self.team1.num_players * PLAYER_STOCKS - self.team1.stocks) // 3,
                          (self.team2.num_players * PLAYER_STOCKS - self.team2.stocks) // 3, 1):
            raise StateError(self, "You can't resize under the current amount of players.")
        current_size = self.team1.num_players
        difference = new_size - current_size
        for team in self.teams:
            team.num_players = new_size
            team.stocks += difference * PLAYER_STOCKS

    def undo(self) -> bool:
        if not self.matches:
            raise StateError(self, "You can't undo a match when there are no matches!")
        last = self.matches.pop()
        if isinstance(last, InfoMatch):
            return False
        if isinstance(last, TimerMatch):
            if not last.team.current_player:
                last.team.current_player = last.team.players[-1]
            elif last.team.current_player != last.player:
                last.team.players.pop()
                last.team.current_player = last.team.players[-1]

            last.team.current_player.left += 1
            last.team.stocks += 1
            return True
        if isinstance(last, ForfeitMatch):
            last.team.stocks = last.stocks
            return True
        self.team1.undo_match(last.p2_taken, last.p1_taken, last.p1)
        self.team2.undo_match(last.p1_taken, last.p2_taken, last.p2)
        return True

    def __str__(self):
        out = f'{self.team1.name} vs {self.team2.name}\n' \
              f'{self.team1.num_players} vs {self.team2.num_players} {self.header}Crew battle'
        out += '\n----------------------------------------------\n'
        for match in self.matches:
            out += str(match)
            out += '\n'
        if self.battle_over():
            out += '--------------------------------------------\n'
            out += f'{self.winner().name} wins {self.winner().stocks} - 0 over {self.loser().name}\n'
            out += f'{self.team1.mvp_parse()}\n{self.team2.mvp_parse()}'
        else:
            out += f'Current score: {self.team1.current_status()} - {self.team2.current_status()}'

        return out

    def embed(self) -> embeds.Embed:
        title = f'{self.team1.name} vs {self.team2.name}'
        body = f'Lobby ID: {self.id}\n' \
               f'Streamer: {self.stream}\n\n' \
               f'{self.team1.num_players} vs {self.team2.num_players} {self.header}Crew battle\n\n'
        for match in self.matches:
            body += str(match)
            body += '\n'

        footer = '\n'
        if self.battle_over():
            footer += '--------------------------------------------\n' \
                      f'{self.winner().name} wins {self.winner().stocks} - 0 over ' \
                      f'{self.loser().name}\n\n{self.team1.mvp_parse()}\n{self.team2.mvp_parse()}'
        else:
            footer += f'Current score: {self.team1.name}[{self.team1.stocks}] - ' \
                      f'{self.team2.name}[{self.team2.stocks}] \n' \
                      f'{self.team1.name}: {self.team1.current_status()}  \n' \
                      f'{self.team2.name}: {self.team2.current_status()}'
        body += footer
        return embeds.Embed(title=title, description=body, color=self.color)
