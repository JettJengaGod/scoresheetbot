from dataclasses import dataclass, field
from typing import Union, Optional
from discord import Emoji


class StateError(Exception):
    """ Raised When the state of the program is incompatible with the given command."""

    def __init__(self, battle, message: str):
        self.battle = battle
        self.message = message


PLAYER_STOCKS = 3
DEFAULT_SIZE = 5


@dataclass
class Character:
    name: str

    def __str__(self):
        return self.name


@dataclass
class Player:
    name: str
    team_name: str
    taken: int = 0
    left: int = PLAYER_STOCKS
    char: Character = None

    def set_char(self, char: Character) -> None:
        self.char = char


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


@dataclass
class Match:
    p1: Player
    p2: Player
    p1_taken: int
    p2_taken: int
    winner: int

    def __str__(self):
        # TODO bold winner here
        return f'{self.p1.name}| {self.p1.char} [{self.p1_taken}] vs [{self.p2_taken}] {self.p2.char}|{self.p2.name}'

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
        assert (p1.left == taken2) or (p2.left == taken1)
        winner = 1 if taken1 == p2.left else 2
        if winner == 1:
            assert taken2 < p1.left
        else:
            assert taken1 < p2.left
        match = Match(p1, p2, taken1, taken2, winner)
        self.matches.append(match)
        self.team1.match_finish(taken2, taken1)
        self.team2.match_finish(taken1, taken2)
        print(match)
        if self.battle_over():
            self.finish_battle()
        return match

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

    def finish_battle(self):
        pass

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
            out += f'{self.winner().name} wins {self.winner().stocks} - 0 over {self.loser().name}'
        else:
            out += f'Current score: {self.team1.name}[{self.team1.stocks}] - {self.team2.name}[{self.team2.stocks}]'
        return out
