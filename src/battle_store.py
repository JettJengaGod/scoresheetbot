"""Saves the running crew battles to disk and loads them back, so they survive a restart of the bot.

A battle is written as plain JSON: both teams with their players, the match log, and everything set on the
battle itself (confirmations, arena, stream, colour, timer, type). The match log refers to players by their
place in a team's roster rather than copying them, because `Battle.undo` relies on a match and the roster
sharing the same `Player` object.
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from discord import colour

from .battle import Battle, BattleType, Difficulty, ForfeitMatch, InfoMatch, Match, Player, Team, TimerMatch
from .character import Character

VERSION = 1
# Next to the code rather than in the working directory, which differs between the server and a dev machine.
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'battles.json')

log = logging.getLogger(__name__)


def battle_file() -> str:
    """Where the battles are kept: the BATTLE_FILE environment variable, or battles.json in the project."""
    return os.getenv('BATTLE_FILE') or DEFAULT_PATH


def _player_to_dict(player: Player) -> dict:
    return {'name': player.name, 'team_name': player.team_name, 'taken': player.taken, 'left': player.left,
            'id': player.id, 'char': dict(vars(player.char))}


def _player_from_dict(data: dict) -> Player:
    # The saved attributes are put back as they were instead of being parsed again from the name: parsing
    # turns some skins into their base character (larry into bowser_jr, alph into olimar).
    char = Character('', bot=None)
    vars(char).update(data['char'])
    return Player(name=data['name'], team_name=data['team_name'], taken=data['taken'], left=data['left'],
                  char=char, id=data['id'])


def _player_ref(team: Team, player: Optional[Player]) -> Optional[dict]:
    """A player by their place in the roster, or in full if they are no longer on it."""
    if player is None:
        return None
    for index, listed in enumerate(team.players):
        if listed is player:
            return {'index': index}
    return {'player': _player_to_dict(player)}


def _player_from_ref(team: Team, ref: Optional[dict]) -> Optional[Player]:
    if ref is None:
        return None
    if 'index' in ref:
        return team.players[ref['index']]
    return _player_from_dict(ref['player'])


def _team_to_dict(team: Team) -> dict:
    return {
        'name': team.name,
        'num_players': team.num_players,
        'stocks': team.stocks,
        'players': [_player_to_dict(player) for player in team.players],
        'leader': sorted(team.leader),
        'current_player': _player_ref(team, team.current_player),
        'ext_used': team.ext_used,
        'replaced': sorted(team.replaced),
        'difficulty': team.difficulty.name,
    }


def _fill_team(team: Team, data: dict) -> None:
    team.num_players = data['num_players']
    team.stocks = data['stocks']
    team.players = [_player_from_dict(player) for player in data['players']]
    team.leader = set(data['leader'])
    team.current_player = _player_from_ref(team, data['current_player'])
    team.ext_used = data['ext_used']
    team.replaced = set(data['replaced'])
    team.difficulty = Difficulty[data['difficulty']]


def _match_to_dict(battle: Battle, match: Match) -> dict:
    # The subclasses come first: they are all Matches.
    if isinstance(match, InfoMatch):
        return {'kind': 'info', 'info': match.info}
    if isinstance(match, TimerMatch):
        return {'kind': 'timer', 'team': battle.teams.index(match.team),
                'player': _player_ref(match.team, match.player)}
    if isinstance(match, ForfeitMatch):
        return {'kind': 'forfeit', 'team': battle.teams.index(match.team), 'stocks': match.stocks}
    return {'kind': 'match', 'p1': _player_ref(battle.team1, match.p1), 'p2': _player_ref(battle.team2, match.p2),
            'p1_taken': match.p1_taken, 'p2_taken': match.p2_taken, 'winner': match.winner}


def _match_from_dict(battle: Battle, data: dict) -> Match:
    kind = data['kind']
    if kind == 'info':
        return InfoMatch(info=data['info'])
    if kind == 'timer':
        team = battle.teams[data['team']]
        return TimerMatch(player=_player_from_ref(team, data['player']), team=team)
    if kind == 'forfeit':
        return ForfeitMatch(team=battle.teams[data['team']], stocks=data['stocks'])
    if kind == 'match':
        return Match(_player_from_ref(battle.team1, data['p1']), _player_from_ref(battle.team2, data['p2']),
                     data['p1_taken'], data['p2_taken'], data['winner'])
    raise ValueError(f'Unknown kind of match: {kind}')


def battle_to_dict(battle: Battle) -> dict:
    return {
        'battle_type': battle.battle_type.name,
        'team1': _team_to_dict(battle.team1),
        'team2': _team_to_dict(battle.team2),
        'matches': [_match_to_dict(battle, match) for match in battle.matches],
        'confirms': list(battle.confirms),
        'id': battle.id,
        'stream': battle.stream,
        'color': battle.color.value,
        'time': battle.time.isoformat(),
    }


def battle_from_dict(data: dict) -> Battle:
    team1, team2 = data['team1'], data['team2']
    # Building it the normal way sets everything that follows from the type, such as the header.
    battle = Battle(team1['name'], team2['name'], team1['num_players'], BattleType[data['battle_type']])
    _fill_team(battle.team1, team1)
    _fill_team(battle.team2, team2)
    battle.matches = [_match_from_dict(battle, match) for match in data['matches']]
    battle.confirms = list(data['confirms'])
    battle.id = data['id']
    battle.stream = data['stream']
    battle.color = colour.Color(data['color'])
    battle.time = datetime.fromisoformat(data['time'])
    return battle


def dumps(battle_map: Dict[str, Battle]) -> str:
    """Every running battle as JSON. The same battles always give the same text, so it can be compared."""
    battles = {key: battle_to_dict(battle) for key, battle in battle_map.items() if battle}
    return json.dumps({'version': VERSION, 'battles': battles}, indent=1, sort_keys=True, ensure_ascii=False)


def loads(text: str) -> Dict[str, Battle]:
    """The battles in `text`. One that cannot be read is logged and left out rather than losing the rest."""
    saved = json.loads(text)
    if saved.get('version') != VERSION:
        raise ValueError(f'Battles were saved as version {saved.get("version")}, this reads version {VERSION}.')
    battle_map = {}
    for key, data in saved['battles'].items():
        try:
            battle_map[key] = battle_from_dict(data)
        except Exception:
            log.exception('Could not restore the battle saved for %s; leaving it out.', key)
    return battle_map


def save_battles(path: str, text: str) -> None:
    """Writes `text` to `path` in one step, so a crash part way through cannot leave half a file."""
    temporary = f'{path}.tmp'
    with open(temporary, 'w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def load_battles(path: str) -> Dict[str, Battle]:
    """The battles saved at `path`, or none if there is no file. An unreadable file is set aside as .bad."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return loads(f.read())
    except Exception:
        log.exception('Could not read the saved battles in %s; starting with none.', path)
        try:
            os.replace(path, f'{path}.bad')
        except OSError:
            pass
        return {}


def keys_without_channel(battle_map: Dict[str, Battle], channel_ids: List[int]) -> List[str]:
    """The battles whose channel is not one of `channel_ids`, by key (`server|channel id`)."""
    known = set(channel_ids)
    return [key for key in battle_map if int(key.rsplit('|', 1)[1]) not in known]
