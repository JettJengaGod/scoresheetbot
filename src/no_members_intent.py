"""Stand-ins for Discord's member list while the bot runs without the server members intent.

The intent is switched off for now (MEMBERS_INTENT unset in .env). Without it Discord sends no member list
and no member events, so the bot knows only the members it fetches here, and the crew data it used to read
off the member list comes from the database instead.

Nothing here runs with the intent on: every caller checks `intents.members` first. To go back to the intent,
switch it on in the Discord Developer Portal and set MEMBERS_INTENT=1. To remove this for good afterwards,
delete this module and the calls to it, each of which sits behind one of those checks.
"""
import logging
import os
from typing import TYPE_CHECKING, List, Optional

import discord

from .constants import ADVISOR, CREW_STAFF, LEADER, MUTED
from .crew import Crew
from .db_helpers import crew_rosters, db_crew_members, update_member_status
from .helpers import Context, check_roles, crew
from .slash import MEMBER_ID

if TYPE_CHECKING:
    from .cache import Cache
    from .scoreSheetBot import ScoreSheetBot


async def cache_command_members(cog: 'ScoreSheetBot', ctx: Context) -> None:
    """Caches, fresh from Discord, the members a slash command is about: whoever ran it and anyone given in
    its options, in this server and in the main and overflow servers, so the command's `get_member` lookups
    find them."""
    ids = {ctx.author.id}
    for _, value in ctx.interaction.namespace:
        if isinstance(value, (discord.Member, discord.User)):
            ids.add(value.id)
        elif isinstance(value, str):
            ids.update(int(a or b) for a, b in MEMBER_ID.findall(value))
    guilds = {guild.id: guild for guild in (ctx.guild, cog.cache.scs, cog.cache.overflow_server) if guild}
    for guild in guilds.values():
        for member_id in ids:
            await fetch_member(cog, guild, member_id)


async def fetch_member(cog: 'ScoreSheetBot', guild: discord.Guild, member_id: int) -> Optional[discord.Member]:
    """`guild`'s member `member_id` fetched from Discord and cached, or None if they aren't in it.

    This also does what the member events would have: when the member's roles or name differ from the copy
    the bot had, or it had none, the database is brought up to date (`ScoreSheetBot._member_changed`), and
    someone no longer in the main server is marked as having left.
    """
    before = guild.get_member(member_id)
    try:
        member = await guild.fetch_member(member_id)
    except discord.NotFound:
        if guild.id == cog.cache.scs.id and os.getenv('VERSION') == 'PROD':
            update_member_status((), (member_id,))
        return None
    guild._add_member(member)
    if before is None or before.roles != member.roles or before.display_name != member.display_name:
        try:
            await cog._member_changed(before, member)
        except Exception:
            # Keeping the database in step must never stop the command that fetched the member.
            logging.exception(f'Could not record the changes to member {member_id}.')
    return member


async def crew_members(cog: 'ScoreSheetBot', cr: Crew) -> List[discord.Member]:
    """The crew's members in the main server, as `helpers.crew_members` would find them on the member list:
    the database's members of the crew, fetched fresh, who are still on it."""
    members = []
    for member_id in db_crew_members(cr):
        member = await fetch_member(cog, cog.cache.scs, member_id)
        if member is None:
            continue
        if cr.overflow:
            # `crew` reads an overflow crew from the member's roles in the overflow server.
            await fetch_member(cog, cog.cache.overflow_server, member_id)
        try:
            current = crew(member, cog)
        except ValueError:
            current = None
        if current == cr.name:
            members.append(member)
    return members


async def muted_crew_members(cog: 'ScoreSheetBot', cr: Crew) -> List[discord.Member]:
    """The crew's members who are muted, as `helpers.overlap_members(MUTED, crew name)` would find them."""
    return [member for member in await crew_members(cog, cr) if check_roles(member, [MUTED])]


def crews_from_db(cache: 'Cache') -> None:
    """Fills in each crew's member count, leaders, advisors and crew staff from the database, in place of what
    `Cache.members_by_name` and `Cache.crew_populate` read off the member list."""
    for cr in cache.crews_by_name.values():
        cr.member_count = 0
        cr.leaders, cr.leader_ids, cr.advisors, cr.crew_staff = [], [], [], []
    for crew_name, member_id, name, roles in crew_rosters():
        cr = cache.crews_by_name.get(crew_name)
        if cr is None:
            continue
        cr.member_count += 1
        if LEADER in roles:
            cr.leaders.append(name)
            cr.leader_ids.append(member_id)
        if ADVISOR in roles:
            cr.advisors.append(name)
        if CREW_STAFF in roles:
            cr.crew_staff.append(name)
