from dataclasses import dataclass, field
from typing import Optional, Iterable
from character import Character
from discord import embeds


class StateError(Exception):
    """ Raised When the state of the program is incompatible with the given command."""

    def __init__(self, battle, message: str):
        self.battle = battle
        self.message = message


PLAYER_STOCKS = 3
DEFAULT_SIZE = 5


def bold(s: str) -> str:
    return f'**{s}**'


@dataclass
class Player:
    name: str
    team_name: str
    taken: int = 0
    left: int = PLAYER_STOCKS
    char: Character = Character('', bot=None)

    def set_char(self, char: Character) -> None:
        self.char = char

    def __str__(self) -> str:
        return f'{self.name} {self.char}'


@dataclass
class Team:
    name: str
    num_players: int
    stocks: int
    players: list = field(default_factory=list)
    current_player: Optional[Player] = None

    def add_player(self, player_name: str) -> None:
        if self.current_player:
            raise StateError(None,
                             f"This team already has a current player, {self.current_player.name}, use \"!replace\" "
                             f"to replace them")
            # TODO add role checks here to make sure the player is on their team
        self.current_player = Player(name=player_name, team_name=self.name)
        self.players.append(self.current_player)

    def replace_current(self, player_name: str) -> None:
        if self.current_player:
            self.players.pop()
        self.current_player = Player(name=player_name, team_name=self.name)
        self.players.append(self.current_player)

    def match_finish(self, lost: int, took: int):
        self.current_player.left -= lost
        self.current_player.taken += took
        self.stocks -= lost
        if self.current_player.left == 0:
            self.current_player = None

    def undo_match(self, lost: int, took: int):
        if not self.current_player:
            self.current_player = self.players[-1]
        self.current_player.left += lost
        self.current_player.taken -= took
        self.stocks += lost

    def mvp(self) -> Optional[Iterable]:
        highest = 0
        ret = []
        for player in self.players:
            if player.taken > highest:
                ret = [player]
                highest = max(highest, player.taken)
            elif player.taken == highest:
                ret.append(player)
        return ret

    def mvp_parse(self) -> str:
        players = ''
        for player in self.mvp():
            players += str(player)
        return f'MVP for {self.name} was {players} with {self.mvp()[0].taken} stocks'

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
        p1 = f'{self.p1.name}| {self.p1.char} [{self.p1_taken}]'
        p2 = f'[{self.p2_taken}] {self.p2.char}|{self.p2.name}'
        if self.winner == 1:
            p1 = bold(p1)
        else:
            p2 = bold(p2)
        return f'{p1} vs {p2}'

    def __eq__(self, other):
        return (
                   self.p1.name, self.p2.name, self.p1_taken, self.p2_taken, self.winner, self.p1.char.name,
                   self.p2.char.name
               ) == (
                   other.p1.name, other.p2.name, other.p1_taken, other.p2_taken, other.winner, other.p1.char.name,
                   other.p2.char.name
               )


class Battle:
    def __init__(self, name1: str, name2: str, players: int):
        self.team1 = Team(name1, players, players * PLAYER_STOCKS)
        self.team2 = Team(name2, players, players * PLAYER_STOCKS)
        self.teams = (self.team1, self.team2)
        self.matches = []
        self.confirms = [False, False]

    def confirmed(self):
        return all(self.confirms)

    def match_ready(self) -> bool:
        return all(t.current_player for t in self.teams)

    def lookup(self, team_name: str) -> Team:
        for team in self.teams:
            if team_name == team.name:
                return team
        raise StateError(self, f"Team \"{team_name}\" does not exist.")

    def add_player(self, team_name: str, player_name: str) -> None:
        team = self.lookup(team_name)
        team.add_player(player_name)

    def replace_player(self, team_name: str, player_name: str) -> None:
        team = self.lookup(team_name)
        team.replace_current(player_name)

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
        if winner == 1:
            if taken2 >= p1.left:
                raise StateError(self, f'Both players can\'t win the game. Please try again. '
                                       f' {p1.name} has {p1.left} stocks {p2.name} has {p2.left} stocks')
        else:
            if taken1 >= p2.left:
                raise StateError(self, f'Both players can\'t win the game. Please try again. '
                                       f' {p1.name} has {p1.left} stocks {p2.name} has {p2.left} stocks')
        match = Match(p1, p2, taken1, taken2, winner)
        self.matches.append(match)
        self.team1.match_finish(taken2, taken1)
        self.team2.match_finish(taken1, taken2)
        return match

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
        if new_size < max(len(self.team1.players), len(self.team2.players), 1):
            raise StateError(self, "You can't resize under the current amount of players.")
        for team in self.teams:
            team.num_players = new_size

    def undo(self):
        if not self.matches:
            raise StateError(self, "You can't undo a match when there are no matches!")
        last = self.matches.pop()
        self.team1.undo_match(last.p2_taken, last.p1_taken)
        self.team2.undo_match(last.p1_taken, last.p2_taken)

    def __str__(self):
        out = f'{self.team1.name} vs {self.team2.name}\n' \
              f'{self.team1.num_players} vs {self.team2.num_players} Crew battle'
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
        title = f'{self.team1.name} vs {self.team2.name}  ' \
                f'{self.team1.num_players} vs {self.team2.num_players} Crew battle'
        body = ''
        for match in self.matches:
            body += str(match)
            body += '\n'

        footer = ''
        if self.battle_over():
            footer += '--------------------------------------------\n' \
                      f'{self.winner().name} wins {self.winner().stocks} - 0 over ' \
                      f'{self.loser().name}\n{self.team1.mvp_parse()}\n{self.team2.mvp_parse()}'
            if not all(self.confirms):
                footer += '\nPlease confirm: '
                if not self.confirms[0]:
                    footer += f'{self.team1.name} '
                if not self.confirms[1]:
                    footer += f'{self.team2.name} '
        else:
            footer += f'Current score: {self.team1.name}[{self.team1.stocks}] - ' \
                      f'{self.team2.name}[{self.team2.stocks}] \n' \
                      f'{self.team1.name}: {self.team1.current_status()}  \n' \
                      f'{self.team2.name}: {self.team2.current_status()}'
        body += footer
        return embeds.Embed(title=title, description=body)
