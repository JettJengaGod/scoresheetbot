"""Bringing the database's record of the main server's members up to date with Discord.

Without the server members intent the bot never sees members join, leave or change roles, so the database
drifts. A sync finds every member through Discord's member search, which doesn't need the intent, and
records their roles, nicknames, crews and whether they are still in the server. The overflow server isn't
synced.
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set, Tuple

import discord

from .constants import OVERFLOW_ROLE
from .db_helpers import apply_member_sync, member_sync_state

if TYPE_CHECKING:
    from .scoreSheetBot import ScoreSheetBot

# Every character a Discord username can contain. The search matches the start of a username or nickname, so
# searching each of these finds every member, narrowing any search that comes back full.
NAME_CHARACTERS = 'abcdefghijklmnopqrstuvwxyz0123456789_.'
SEARCH_LIMIT = 1000
USERNAME_LENGTH = 32
# The most members Discord returns for one request by id.
ID_LIMIT = 100


@dataclass
class MemberSync:
    """The changes a sync makes to the database."""
    new_members: List[Tuple[int, str, str]] = field(default_factory=list)  # id, nickname, username
    renamed: List[Tuple[int, str]] = field(default_factory=list)  # id, nickname
    roles: List[Tuple[int, str, int]] = field(default_factory=list)  # the server's roles: id, name, server id
    gained: List[Tuple[int, int]] = field(default_factory=list)  # member id, role id
    lost: List[Tuple[int, int]] = field(default_factory=list)  # member id, role id
    retired: int = 0  # how many of the lost roles were lost because the role was deleted
    joined: List[int] = field(default_factory=list)  # members now marked as in the server
    left: List[int] = field(default_factory=list)  # members now marked as having left
    crews: List[Tuple[int, Optional[int]]] = field(default_factory=list)  # member id, new crew id or None
    unknown_crews: Set[str] = field(default_factory=set)  # crew roles with no crew in the database
    found: int = 0
    member_count: Optional[int] = None

    def summary(self) -> str:
        lines = [f'Found {self.found} of the {self.member_count} members of the server.']
        if self.member_count and self.found < self.member_count:
            lines.append(f'{self.member_count - self.found} could not be found by name; their records are left '
                         f'as they are.')
        lines.extend([
            f'New members: {len(self.new_members)}',
            f'Nicknames changed: {len(self.renamed)}',
            f'Roles gained: {len(self.gained)}',
            f'Roles lost: {len(self.lost) - self.retired}',
            f'Roles removed because the role no longer exists: {self.retired}',
            f'Marked as in the server: {len(self.joined)}',
            f'Marked as having left: {len(self.left)}',
            f'Crew changes: {len(self.crews)}',
        ])
        if self.unknown_crews:
            lines.append(f'Crew roles with no crew in the database, left alone: '
                         f'{", ".join(sorted(self.unknown_crews))}')
        return '\n'.join(lines)


async def search_members(guild: discord.Guild, query: str) -> List[discord.Member]:
    """Up to `SEARCH_LIMIT` members of `guild` whose username or nickname starts with `query`."""
    route = discord.http.Route('GET', '/guilds/{guild_id}/members/search', guild_id=guild.id)
    data = await guild._state.http.request(route, params={'query': query, 'limit': SEARCH_LIMIT})
    return [discord.Member(data=member, guild=guild, state=guild._state) for member in data]


async def all_members(guild: discord.Guild) -> Dict[int, discord.Member]:
    """Every member of `guild` the member search can find, by id. Someone whose whole username is a search
    that came back full can be missed."""
    found = {}
    prefixes = list(NAME_CHARACTERS)
    while prefixes:
        prefix = prefixes.pop()
        members = await search_members(guild, prefix)
        found.update((member.id, member) for member in members)
        if len(members) >= SEARCH_LIMIT and len(prefix) < USERNAME_LENGTH:
            prefixes.extend(prefix + character for character in NAME_CHARACTERS)
    return found


async def members_by_id(guild: discord.Guild, member_ids: Iterable[int]) -> Dict[int, discord.Member]:
    """The members of `guild` among `member_ids`, by id."""
    member_ids = list(member_ids)
    found = {}
    for start in range(0, len(member_ids), ID_LIMIT):
        chunk = member_ids[start:start + ID_LIMIT]
        for member in await guild.query_members(user_ids=chunk, limit=ID_LIMIT, cache=False):
            found[member.id] = member
    return found


def plan(guild: discord.Guild, members: Dict[int, discord.Member], crew_names: Iterable[str],
         db_members: Dict[int, Tuple[str, Optional[bool]]], db_roles: Set[Tuple[int, int]],
         db_crews: Dict[int, int], crew_ids: Dict[int, int]) -> MemberSync:
    """The changes that make the database match `members`, which must be everyone in `guild` the database
    has as being in it who is still there, plus anyone else found. The `db_` arguments and `crew_ids` are
    what `member_sync_state` reads.

    Members who left keep their roles, which are given back if they rejoin, and their crew. Members in the
    overflow server keep their crew, as it is read from the overflow server, which isn't synced."""
    sync = MemberSync(found=len(members), member_count=guild.member_count)
    role_ids = {role.id for role in guild.roles if not role.is_default()}
    sync.roles = [(role.id, role.name, guild.id) for role in guild.roles if not role.is_default()]
    crew_names = set(crew_names)
    has = set()
    for member in members.values():
        if member.id not in db_members:
            sync.new_members.append((member.id, member.display_name, member.name))
        elif db_members[member.id][0] != member.display_name:
            sync.renamed.append((member.id, member.display_name))
        if db_members.get(member.id, (None, None))[1] is not True:
            sync.joined.append(member.id)
        roles = [role for role in member.roles if not role.is_default()]
        has.update((member.id, role.id) for role in roles)

        if any(role.name == OVERFLOW_ROLE for role in roles):
            continue
        crew_role = next((role for role in roles if role.name in crew_names), None)
        crew_id = None
        if crew_role is not None:
            crew_id = crew_ids.get(crew_role.id)
            if crew_id is None:
                sync.unknown_crews.add(crew_role.name)
                continue
        if db_crews.get(member.id) != crew_id:
            sync.crews.append((member.id, crew_id))

    sync.gained = sorted(has - db_roles)
    for member_id, role_id in sorted(db_roles):
        if role_id not in role_ids:
            sync.lost.append((member_id, role_id))
            sync.retired += 1
        elif member_id in members and (member_id, role_id) not in has:
            sync.lost.append((member_id, role_id))
    sync.left = sorted(member_id for member_id, (_, in_server) in db_members.items()
                       if in_server is not False and member_id not in members)
    return sync


async def sync_members(cog: 'ScoreSheetBot', apply: bool) -> MemberSync:
    """Works out what the database is missing about the main server's members, and writes it if `apply`."""
    guild = cog.cache.scs
    db_members, db_roles, db_crews, crew_ids = member_sync_state(guild.id)
    if cog.bot.intents.members:
        members = {member.id: member for member in guild.members}
    else:
        members = await all_members(guild)
        # Anyone the search missed who the database has as in the server is looked up by id, so that only
        # members who really left are marked as having left.
        unfound = [member_id for member_id, (_, in_server) in db_members.items()
                   if in_server is not False and member_id not in members]
        members.update(await members_by_id(guild, unfound))
    sync = plan(guild, members, cog.cache.crews, db_members, db_roles, db_crews, crew_ids)
    if apply:
        apply_member_sync(sync)
    return sync
