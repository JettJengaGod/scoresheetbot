"""Slash command front ends for the bot's prefix commands.

Every prefix command is reachable as a slash command in one of three ways:

* a hybrid command, declared in the cog, for player commands whose arguments Discord can express as-is;
* a "twin" generated here with the same options as the prefix command, used for crew battle and staff
  commands so they can live under `/cb <command>` and `/staff <group> <command>` while keeping their flat
  prefix names;
* a hand written front end here, for commands whose prefix form takes free text that slash commands can ask
  for as separate typed options.

Twins and typed front ends run the prefix command's own callback through `ScoreSheetBot.run_slash`, so the
guards, hooks and behaviour are shared and only the way arguments are collected differs.
"""
import inspect
import re
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .character import CHARACTERS

if TYPE_CHECKING:
    from .scoreSheetBot import ScoreSheetBot

DESCRIPTION_LIMIT = 100

# Crew battle commands live under /cb <command>. Discord allows 25 commands per group and this is 25, so
# the next one needs a subgroup (or to stay top level, like the character lookups `char` and `chars`).
CB_COMMANDS: List[str] = [
    'battle', 'mock', 'reg', 'strawhat', 'cowy', 'playoff', 'send', 'replace', 'end', 'endlag', 'undo',
    'resize', 'forfeit', 'confirm', 'clear', 'status', 'timer', 'timerstock', 'ext', 'use_ext', 'arena',
    'stream', 'lock', 'unlock', 'countdown']

# Where each staff command lives: /staff <group> <command>. Discord allows 25 commands per group.
STAFF_GROUPS: Dict[str, tuple] = {
    'crew': ('Manage crews', [
        'disband', 'freeze', 'retag', 'tomain', 'opt', 'tri', 'pair', 'register', 'overflow', 'non_crew',
        'crnumbers', 'flaircounts', 'cooldown']),
    'flair': ('Manage flairing and roles', [
        'make_lead', 'fixunflair', 'flairing_on', 'flairing_off', 'categoryrole', 'pingrole',
        'pingoverlap', 'pingnoverlap', 'savenicks']),
    'battle': ('Manage crew battle records', [
        'addforfeit', 'addsheet', 'failedreg', 'weirdreg', 'cancelcb', 'manual_battle', 'pending', 'vod', 'rate',
        'update_elos', 'initalize_ratings', 'season', 'backfill']),
    'slots': ('Manage crew slots', [
        'setslots', 'setreturnslots', 'fixslot', 'slottotals', 'slotfinals']),
    'bot': ('Manage the bot', [
        'disable', 'deactivate', 'usage', 'recache', 'charge', 'stupid', 'dele', 'sync']),
}

# Prefix commands that deliberately have no slash command.
PREFIX_ONLY = {
    # Placeholder groups that only exist to list a help category; /help covers them.
    'cb', 'ba', 'crews', 'flairing', 'staff', 'misc',
    # Developer checks of discord.py behaviour.
    'test', 'test confirm',
}

# Slash descriptions for commands whose help description is written for the prefix form (it gives an example
# or explains how to type the arguments) or is longer than Discord allows. Everything else uses help.py.
DESCRIPTIONS = {
    'end': 'Ends the current match with each player\'s character and the stocks they took.',
    'endlag': 'Ends the current match like end, but without needing one player to win.',
    'char': 'Shows the emoji for a character name; add a number for an alt, e.g. ness2.',
    'undo': 'Undoes the last match.',
    'freeze': 'Stops a crew registering for a time (e.g. 3D, 2W, 1M), or unfreezes a frozen crew.',
    'multiflair': 'Flairs several members for your crew, or for a given crew if you are staff.',
    'multiunflair': 'Unflairs several members from your crew, or from any crew if you are staff.',
    'register': 'Flairs several members for a newly registered crew.',
    'overlap': 'Lists the members who have both roles.',
    'noverlap': 'Lists the members who have the first role but not the second.',
    'result': 'Submits a best of 5 battle arena result for your opponent to confirm.',
    'help': 'Lists command groups, or explains one group or command.',
    'gamb': 'Gambit management.',
}

# Option descriptions, by option name. A "command.option" key overrides the plain name for one command.
OPTIONS = {
    'user': 'The player',
    'member': 'The member',
    'members': 'The members, each one mentioned, separated by spaces',
    'opponent': 'The player you faced',
    'team': 'Team name; only needed in a mock',
    'team1': 'Name of the first team',
    'team2': 'Name of the second team',
    'size': 'Number of players on each side',
    'new_size': 'New number of players on each side',
    'name': 'A member or a crew (name or tag); leave blank for yourself',
    'new_crew': 'Crew name or tag',
    'crew': 'Crew name or tag',
    'crew1': 'Crew name or tag',
    'crew2': 'Crew name or tag',
    'cr': 'Crew name or tag; leave blank for your own',
    'c1': 'Crew name or tag',
    'c2': 'Crew name or tag',
    'winner': 'Winning crew, name or tag',
    'loser': 'Losing crew, name or tag',
    'losing_crew': 'Losing crew, name or tag',
    'registering_crew': 'Name of the registering crew',
    'crew_name': 'Name of the registering crew',
    'players': 'Number of players on each side',
    'score': 'Stocks the winner had left',
    'screenshot': 'Screenshot of the result',
    'screenshot2': 'A second screenshot, if one is not enough',
    'char1': 'Character of the first team\'s player',
    'char2': 'Character of the second team\'s player',
    'stocks1': 'Stocks the first team\'s player took',
    'stocks2': 'Stocks the second team\'s player took',
    'emoji': 'Character name',
    'role': 'Role name',
    'role1': 'First role',
    'role2': 'Second role',
    'rank': 'Crew rank',
    'seconds': 'Seconds to count down from (10 or less)',
    'streamer': 'Streamer who should keep access to the channel',
    'stream': 'Twitch name or stream link; leave blank to show the current one',
    'id_str': 'Arena ID and password; leave blank to show the current one',
    'option': 'The option you are voting for',
    'over': 'Only show crews with more members than this',
    'amount': 'Number of G-Coins',
    'bet.amount': 'Number of G-Coins, or "all"',
    'reason': 'Reason',
    'num': 'Number of slots',
    'length': 'How long, e.g. 3D, 2W or 1M; leave blank to unfreeze',
    'channel': 'The channel',
    'command': 'Command name',
    'battle_id': 'ID of the crew battle',
    'vod': 'Link to the vod',
    'long': 'Add anything here for the long version',
    'your_characters': 'Characters you played, separated by spaces',
    'your_score': 'Games you won',
    'opponent_score': 'Games your opponent won',
    'opponent_characters': 'Characters your opponent played, separated by spaces',
}

CREW_OPTIONS = ('new_crew', 'crew', 'crew1', 'crew2', 'cr', 'c1', 'c2', 'winner', 'loser', 'losing_crew')
CHARACTER_OPTIONS = ('char1', 'char2', 'emoji')
# Commands that answer only the person who ran them.
EPHEMERAL = {'help'}
# Commands that also work in a DM with the bot.
ALLOWED_IN_DMS = {'help'}


def description(command: commands.Command) -> str:
    """The description Discord shows for `command`, which it limits to 100 characters."""
    text = DESCRIPTIONS.get(command.qualified_name) or command.description or command.brief or command.name
    if len(text) > DESCRIPTION_LIMIT:
        text = text[:DESCRIPTION_LIMIT - 3].rstrip() + '...'
    return text


def parse_members(guild: discord.Guild, text: str) -> List[discord.Member]:
    """Finds the members mentioned (or given by id) in `text`. Raises ValueError if any cannot be found."""
    ids = re.findall(r'<@!?(\d+)>|\b(\d{15,20})\b', text)
    members, missing = [], []
    for mention_id, bare_id in ids:
        member_id = int(mention_id or bare_id)
        member = guild.get_member(member_id)
        if member is None:
            missing.append(str(member_id))
        elif member not in members:
            members.append(member)
    if missing:
        raise ValueError(f'Could not find these members in this server: {", ".join(missing)}.')
    if not members:
        raise ValueError('Mention each member, separated by spaces.')
    return members


class SlashCommands:
    """Builds the slash commands for a cog and remembers which prefix command each one runs."""

    def __init__(self, cog: 'ScoreSheetBot'):
        self.cog = cog
        # Qualified prefix command name -> the slash command that runs it.
        self.by_prefix_name: Dict[str, app_commands.Command] = {}
        self.typed = self._typed_front_ends()
        prefix_commands = {command.qualified_name: command for command in cog.walk_commands()}

        cb = app_commands.Group(name='cb', description='Run a crew battle', guild_only=True)
        for name in CB_COMMANDS:
            self._add(prefix_commands[name], parent=cb)

        staff = app_commands.Group(name='staff', description='Staff commands', guild_only=True)
        for group_name, (group_description, names) in STAFF_GROUPS.items():
            group = app_commands.Group(name=group_name, description=group_description, parent=staff)
            for name in names:
                self._add(prefix_commands[name], parent=group)

        top_level = [cb, staff]
        for name, command in prefix_commands.items():
            if name in PREFIX_ONLY or name in self.by_prefix_name:
                continue
            if isinstance(command, (commands.HybridCommand, commands.HybridGroup)):
                self._document_hybrid(command)
            else:
                top_level.append(self._add(command, parent=None))
        cog.__cog_app_commands__.extend(top_level)

    def _add(self, command: commands.Command, parent: Optional[app_commands.Group]) -> app_commands.Command:
        name = command.qualified_name
        callback = self.typed.get(name) or self._twin_callback(command)
        slash = app_commands.Command(name=command.name, description=description(command), callback=callback)
        self._describe_options(slash, name)
        if parent is not None:
            parent.add_command(slash)
        elif name not in ALLOWED_IN_DMS:
            slash.guild_only = True
        self.by_prefix_name[name] = slash
        return slash

    def _document_hybrid(self, command: commands.Command) -> None:
        slash = command.app_command
        if slash is None:
            return
        name = command.qualified_name
        if isinstance(slash, app_commands.Group):
            slash.description = description(command)
            slash.guild_only = True
            if command.fallback:
                fallback = slash.get_command(command.fallback)
                # The fallback runs the group's own callback, so it is what the group's help describes.
                fallback.description = (command.description or fallback.description)[:DESCRIPTION_LIMIT]
                self.by_prefix_name[name] = fallback
            return
        slash.description = description(command)
        if slash.parent is None:
            slash.guild_only = True
        self._describe_options(slash, name)
        self.by_prefix_name[name] = slash

    def _describe_options(self, slash: app_commands.Command, name: str) -> None:
        options = {p.name for p in slash.parameters}
        described = {o: OPTIONS.get(f'{name}.{o}', OPTIONS.get(o)) for o in options}
        app_commands.describe(**{o: text for o, text in described.items() if text})(slash)
        completions = {o: self.crew_autocomplete for o in options if o in CREW_OPTIONS}
        completions.update({o: self.character_autocomplete for o in options if o in CHARACTER_OPTIONS})
        if name == 'help':
            completions['command'] = self.command_autocomplete
        if completions:
            app_commands.autocomplete(**completions)(slash)

    def _twin_callback(self, command: commands.Command) -> Callable:
        """A slash callback taking the same arguments as prefix command `command`."""
        cog = self.cog
        signature = inspect.signature(command.callback)
        options = []
        for parameter in list(signature.parameters.values())[2:]:
            annotation = parameter.annotation
            if annotation is inspect.Parameter.empty:
                annotation = str
            options.append(parameter.replace(kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation))
        interaction = inspect.Parameter('interaction', inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                        annotation=discord.Interaction)

        async def callback(interaction, **kwargs):
            await cog.run_slash(interaction, command.qualified_name, **kwargs)

        callback.__signature__ = signature.replace(parameters=[interaction] + options)
        return callback

    # Autocompletes only suggest; anything the prefix command accepts can still be typed in.

    async def crew_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        crews = [cr for cr in self.cog.cache.crews_by_name.values()
                 if current in cr.name.lower() or current in cr.abbr.lower()]
        crews.sort(key=lambda cr: (not cr.abbr.lower().startswith(current), cr.name.lower()))
        return [app_commands.Choice(name=f'{cr.name} ({cr.abbr})'[:100], value=cr.abbr) for cr in crews[:25]]

    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        names = [name for name, alts in CHARACTERS.items()
                 if current in name or any(current in alt for alt in alts)]
        names.sort(key=lambda name: (not name.startswith(current), name))
        return [app_commands.Choice(name=name, value=name) for name in names[:25]]

    async def command_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        names = sorted({command.name for command in self.cog.walk_commands()
                        if not command.hidden and current in command.name})
        return [app_commands.Choice(name=name, value=name) for name in names[:25]]

    def _typed_front_ends(self) -> Dict[str, Callable]:
        """Front ends for commands whose prefix form takes free text.

        Each one asks for separate options and puts them together the way the prefix command expects them.
        Crews are passed on by tag whenever the user picks a suggestion, which the prefix parsers match exactly.
        """
        cog = self.cog
        Score = app_commands.Range[int, 0, 3]

        async def run(interaction: discord.Interaction, name: str, *args, **kwargs):
            await cog.run_slash(interaction, name, *args, **kwargs)

        def attachments(*files):
            return [file for file in files if file is not None]

        async def members_or_error(interaction: discord.Interaction, text: str):
            try:
                return parse_members(interaction.guild, text)
            except ValueError as error:
                await interaction.response.send_message(str(error), ephemeral=True)
                return None

        async def bet(interaction, amount: str, crew: str):
            await run(interaction, 'bet', everything=f'{amount} {crew}')

        async def end(interaction, char1: str, stocks1: int, char2: str, stocks2: int):
            await run(interaction, 'end', char1, stocks1, char2, stocks2)

        async def endlag(interaction, char1: str, stocks1: int, char2: str, stocks2: int):
            await run(interaction, 'endlag', char1, stocks1, char2, stocks2)

        async def help_(interaction, command: Optional[str] = None):
            await run(interaction, 'help', *([command] if command else []))

        async def multiflair(interaction, members: str, new_crew: Optional[str] = None):
            found = await members_or_error(interaction, members)
            if found:
                await run(interaction, 'multiflair', found, new_crew)

        async def multiunflair(interaction, members: str):
            await run(interaction, 'multiunflair', everything=members)

        async def register(interaction, members: str, new_crew: str):
            found = await members_or_error(interaction, members)
            if found:
                await run(interaction, 'register', found, new_crew=new_crew)

        async def overlap(interaction, role1: discord.Role, role2: discord.Role):
            await run(interaction, 'overlap', two_roles=f'{role1.name} {role2.name}')

        async def noverlap(interaction, role1: discord.Role, role2: discord.Role):
            await run(interaction, 'noverlap', two_roles=f'{role1.name} {role2.name}')

        async def pingoverlap(interaction, role1: discord.Role, role2: discord.Role):
            await run(interaction, 'pingoverlap', two_roles=f'{role1.name} {role2.name}')

        async def pingnoverlap(interaction, role1: discord.Role, role2: discord.Role):
            await run(interaction, 'pingnoverlap', two_roles=f'{role1.name} {role2.name}')

        async def reg(interaction, crew_name: str, size: int):
            await run(interaction, 'reg', everything=f'{crew_name} {size}')

        async def result(interaction, opponent: discord.Member, your_characters: str, your_score: Score,
                         opponent_score: Score, opponent_characters: str):
            await run(interaction, 'result', opponent,
                      everything=f'{your_characters} {your_score} {opponent_score} {opponent_characters}')

        async def freeze(interaction, crew: str, length: Optional[str] = None):
            await run(interaction, 'freeze', everything=f'{crew} {length}' if length else crew)

        async def pair(interaction, crew1: str, crew2: str):
            await run(interaction, 'pair', everything=f'{crew1} {crew2}')

        async def addforfeit(interaction, winner: str, loser: str, screenshot: discord.Attachment,
                             screenshot2: Optional[discord.Attachment] = None):
            await run(interaction, 'addforfeit', everything=f'{winner} {loser}',
                      attachments=attachments(screenshot, screenshot2))

        async def addsheet(interaction, winner: str, loser: str, players: int, score: int,
                           screenshot: discord.Attachment, screenshot2: Optional[discord.Attachment] = None):
            await run(interaction, 'addsheet', everything=f'{winner} {loser} {players} {score}',
                      attachments=attachments(screenshot, screenshot2))

        async def failedreg(interaction, winner: str, registering_crew: str, players: int, score: int,
                            screenshot: discord.Attachment, screenshot2: Optional[discord.Attachment] = None):
            await run(interaction, 'failedreg', everything=f'{winner} {registering_crew} {players} {score}',
                      attachments=attachments(screenshot, screenshot2))

        async def weirdreg(interaction, losing_crew: str, registering_crew: str, players: int, score: int,
                           screenshot: discord.Attachment, screenshot2: Optional[discord.Attachment] = None):
            await run(interaction, 'weirdreg', everything=f'{losing_crew} {registering_crew} {players} {score}',
                      attachments=attachments(screenshot, screenshot2))

        return {
            'bet': bet, 'end': end, 'endlag': endlag, 'help': help_, 'multiflair': multiflair,
            'multiunflair': multiunflair, 'register': register, 'overlap': overlap, 'noverlap': noverlap,
            'pingoverlap': pingoverlap, 'pingnoverlap': pingnoverlap, 'reg': reg, 'result': result,
            'freeze': freeze, 'pair': pair, 'addforfeit': addforfeit, 'addsheet': addsheet,
            'failedreg': failedreg, 'weirdreg': weirdreg,
        }
