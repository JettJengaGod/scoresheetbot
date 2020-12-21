import os
import sys
import traceback
import time
import discord
import functools
from datetime import date
from discord.ext import commands
from dotenv import load_dotenv
from typing import Dict, Optional, Union, Iterable
from helpers import *
from battle import Battle
from cache import Cache
from character import all_emojis, string_to_emote, all_alts
from decorators import *
from help import help
from constants import *

Context = discord.ext.commands.Context

class ScoreSheetBot(commands.Cog):
    def __init__(self, bot: commands.bot, cache: Cache):
        self.bot = bot
        self.battle_map: Dict[str, Battle] = {}
        self.cache = cache

    def _current(self, ctx) -> Battle:
        return self.battle_map[key_string(ctx)]

    async def _battle_crew(self, ctx: Context, user: discord.Member) -> Optional[str]:
        crew_name = crew(user, self)
        if crew_name in (self._current(ctx).team1.name, self._current(ctx).team2.name):
            return crew_name
        return None

    async def _reject_outsiders(self, ctx: Context):
        if self._current(ctx).mock:
            return
        if not await self._battle_crew(ctx, ctx.author):
            raise Exception('You are not in this battle, stop trying to mess with it.')

    def _set_current(self, ctx: Context, battle: Battle):
        self.battle_map[key_string(ctx)] = battle

    def _clear_current(self, ctx):
        self.battle_map[key_string(ctx)] = None

    @commands.command(**help['battle'], aliases=['challenge'])
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    @cache_update
    async def battle(self, ctx: Context, user: discord.Member, size: int):
        if size < 1:
            await ctx.send('Please enter a size greater than 0.')
            return
        user_crew = crew(ctx.author, self)
        opp_crew = crew(user, self)
        if not user_crew:
            await ctx.send(f'{ctx.author.name}\'s crew didn\'t show up correctly. '
                           f'They might be in an overflow crew or no crew. '
                           f'Please contact an admin if this is incorrect.')
            return
        if not opp_crew:
            await ctx.send(f'{user.name}\'s crew didn\'t show up correctly. '
                           f'They might be in an overflow crew or no crew. '
                           f'Please contact an admin if this is incorrect.')
            return
        if user_crew != opp_crew:
            self._set_current(ctx, Battle(user_crew, opp_crew, size))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help['mock'])
    @main_only
    @no_battle
    @ss_channel
    @cache_update
    async def mock(self, ctx: Context, team1: str, team2: str, size: int):
        if size < 1:
            await ctx.send('Please enter a size greater than 0.')
            return
        self._set_current(ctx, Battle(team1, team2, size, mock=True))
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help['send'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    @cache_update
    async def send(self, ctx: Context, user: discord.Member, team: str = None):
        if self._current(ctx).mock:
            if team:
                self._current(ctx).add_player(team, escape(user.display_name), ctx.author.mention)
            else:
                await ctx.send(f'During a mock you need to send with a teamname, like this'
                               f' `,send @playername teamname`.')
                return
        else:
            await self._reject_outsiders(ctx)
            author_crew = await self._battle_crew(ctx, ctx.author)
            player_crew = await self._battle_crew(ctx, user)
            if author_crew == player_crew:
                if check_roles(user, [WATCHLIST]):
                    await ctx.send(f'Watch listed player {user.mention} cannot play in ranked battles.')
                    return
                if check_roles(user, [JOIN_CD]):
                    await ctx.send(
                        f'{user.mention} joined this crew less than '
                        f'24 hours ago and must wait to play ranked battles.')
                    return
                self._current(ctx).add_player(author_crew, escape(user.display_name), ctx.author.mention)
            else:
                await ctx.send(f'{escape(user.display_name)} is not on {author_crew} please choose someone else.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help['replace'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    @cache_update
    async def replace(self, ctx: Context, user: discord.Member, team: str = None):
        if self._current(ctx).mock:
            if team:
                self._current(ctx).replace_player(team, escape(user.display_name), ctx.author.mention)
            else:
                await ctx.send(f'During a mock you need to replace with a teamname, like this'
                               f' `,replace @playername teamname`.')
                return
        else:
            await self._reject_outsiders(ctx)
            current_crew = await self._battle_crew(ctx, ctx.author)
            if current_crew == await self._battle_crew(ctx, user):
                self._current(ctx).replace_player(current_crew, escape(user.display_name), ctx.author.mention)

            else:
                await ctx.send(f'{escape(user.display_name)} is not on {current_crew}, please choose someone else.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help['end'])
    @main_only
    @has_sheet
    @ss_channel
    @cache_update
    async def end(self, ctx: Context, char1: Union[str, discord.Emoji], stocks1: int, char2: Union[str, discord.Emoji],
                  stocks2: int):
        await self._reject_outsiders(ctx)

        self._current(ctx).finish_match(stocks1, stocks2,
                                        Character(str(char1), self.bot, is_usable_emoji(char1, self.bot)),
                                        Character(str(char2), self.bot, is_usable_emoji(char2, self.bot)))
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help['resize'])
    @main_only
    @is_lead
    @has_sheet
    @ss_channel
    @cache_update
    async def resize(self, ctx: Context, new_size: int):
        await self._reject_outsiders(ctx)
        self._current(ctx).resize(new_size)
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help['arena'], aliases=['id', 'arena_id', 'lobby'])
    @main_only
    @has_sheet
    @ss_channel
    @cache_update
    async def arena(self, ctx: Context, id_str: str = ''):
        if id_str and (check_roles(ctx.author, [LEADER, ADVISOR, ADMIN, MINION, STREAMER, CERTIFIED]
                                   ) or self._current(ctx).mock):
            self._current(ctx).id = id_str
            await ctx.send(f'Updated the id to {id_str}')
            return
        await ctx.send(f'The lobby id is {self._current(ctx).id}')

    @commands.command(**help['stream'], aliases=['streamer', 'stream_link'])
    @main_only
    @has_sheet
    @ss_channel
    @cache_update
    async def stream(self, ctx: Context, stream: str = ''):
        if stream and (check_roles(ctx.author, [LEADER, ADVISOR, ADMIN, MINION, STREAMER, CERTIFIED]
                                   ) or self._current(ctx).mock):
            if '/' not in stream:
                stream = 'https://twitch.tv/' + stream
            self._current(ctx).stream = stream
            await ctx.send(f'Updated the stream to {stream}')
            return
        await ctx.send(f'The stream is {self._current(ctx).stream}')

    @commands.command(**help['undo'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    @cache_update
    async def undo(self, ctx):
        await self._reject_outsiders(ctx)
        self._current(ctx).undo()
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help['confirm'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    @cache_update
    async def confirm(self, ctx: Context):
        await self._reject_outsiders(ctx)

        if self._current(ctx).battle_over():
            if self._current(ctx).mock:
                self._clear_current(ctx)
                await ctx.send(f'This battle was confirmed by {ctx.author.mention}.')
            else:
                self._current(ctx).confirm(await self._battle_crew(ctx, ctx.author))
                await send_sheet(ctx, battle=self._current(ctx))
                if self._current(ctx).confirmed():
                    today = date.today()

                    output_channels = [discord.utils.get(ctx.guild.channels, name=OUTPUT),
                                       discord.utils.get(ctx.guild.channels, name=DOCS_UPDATES)]
                    winner = self._current(ctx).winner().name
                    loser = self._current(ctx).loser().name
                    for output_channel in output_channels:
                        await output_channel.send(
                            f'**{today.strftime("%B %d, %Y")}- {winner} vs. {loser} **\n'
                            f'{self.cache.crews_by_name[winner].rank} crew defeats'
                            f' {self.cache.crews_by_name[loser].rank} crew in a '
                            f'{self._current(ctx).team1.num_players}v{self._current(ctx).team2.num_players} battle!\n'
                            f'from  {ctx.channel.mention}.')
                        await send_sheet(output_channel, self._current(ctx))
                    await ctx.send(
                        f'The battle between {self._current(ctx).team1.name} and {self._current(ctx).team2.name} '
                        f'has been confirmed by both sides and posted in {output_channels[1].mention}.')
                    self._clear_current(ctx)
        else:
            await ctx.send('The battle is not over yet, wait till then to confirm.')

    @commands.command(**help['clear'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    @cache_update
    async def clear(self, ctx):
        if not check_roles(ctx.author, STAFF_LIST):
            await self._reject_outsiders(ctx)
        if self._current(ctx).mock:
            await ctx.send('If you just cleared a crew battle to troll people, be warned this is a bannable offence.')
        self._clear_current(ctx)
        await ctx.send(f'{ctx.author.mention} cleared the crew battle.')

    @commands.command(**help['status'])
    @main_only
    @has_sheet
    @ss_channel
    @cache_update
    async def status(self, ctx):
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help['timer'])
    @main_only
    @has_sheet
    @ss_channel
    async def timer(self, ctx):
        await ctx.send(self._current(ctx).timer())

    @commands.command(**help['char'])
    async def char(self, ctx: Context, emoji):
        if is_usable_emoji(emoji, self.bot):
            await ctx.send(emoji)
        else:
            await ctx.send(f'What you put: {string_to_emote(emoji, self.bot)}')
            await ctx.send(f'All alts in order: {all_alts(emoji, self.bot)}')

    @commands.command(**help['crew'])
    @main_only
    @cache_update
    async def crew(self, ctx, *, name: str = None):
        if name:
            ambiguous = ambiguous_lookup(name, self)
            if isinstance(ambiguous, discord.Member):
                actual_crew = crew_lookup(crew(ambiguous, self), self)
                await ctx.send(f'{ambiguous.display_name} is in {actual_crew.name}.')
            else:
                actual_crew = ambiguous
        else:
            actual_crew = crew_lookup(crew(ctx.author, self), self)
            await ctx.send(f'{ctx.author.display_name} is in {crew(ctx.author, self)}.')
        await ctx.send(embed=actual_crew.embed)

    @commands.command(**help['non_crew'])
    @main_only
    @role_call(STAFF_LIST)
    @cache_update
    async def non_crew(self, ctx, *, name: str = None):
        out = [f'```Main server non crew roles: \n']
        for role in self.cache.non_crew_roles_main:
            guess = crew_lookup(role, self)
            out.append(f'\'{role}\' best guess from docs is \'{guess.name}\'')
            out.append('\n')
        out.append('Overflow server non crew roles: \n')
        for role in self.cache.non_crew_roles_overflow:
            guess = crew_lookup(role, self)
            out.append(f'\'{role}\' best guess from docs is \'{guess.name}\'')
            out.append('\n')
        out.append('```')
        await ctx.send(''.join(out))

    @commands.command(**help['rank'])
    @main_only
    @cache_update
    async def rank(self, ctx, *, name: str = None):
        user = None
        if name:
            ambiguous = ambiguous_lookup(name, self)
            if isinstance(ambiguous, discord.Member):
                user = ambiguous
                crew_name = crew(user, self)
            else:
                crew_name = ambiguous.name
        else:
            user = ctx.author
            crew_name = crew(user, self)

        crew_rank = self.cache.crews_by_name[crew_name].rank
        out = ''
        if user:
            out += f'{escape(user.display_name)}\'s crew '
        out += f'{crew_name} is rank {crew_rank}.'
        await ctx.send(out)

    @commands.command(**help['merit'])
    @main_only
    @cache_update
    async def merit(self, ctx, *, name: str = None):
        user = None
        if name:
            ambiguous = ambiguous_lookup(name, self)
            if isinstance(ambiguous, discord.Member):
                user = ambiguous
                crew_name = crew(user, self)
            else:
                crew_name = ambiguous.name
        else:
            user = ctx.author
            crew_name = crew(user, self)

        crew_merit = self.cache.crews_by_name[crew_name].merit
        out = ''
        if user:
            out += f'{escape(user.display_name)}\'s crew '
        out += f'{crew_name} has {crew_merit} merit.'
        await ctx.send(out)

    @commands.command(**help['promote'])
    @main_only
    @flairing_required
    @cache_update
    async def promote(self, ctx: Context, member: discord.Member):
        if not member:
            await response_message(ctx, 'You can\'t promote yourself.')
            return
        try:
            target_crew = crew(member, self)
        except ValueError:
            await response_message(ctx, f'You can\'t promote someone who is not in a crew.')
            return

        if not check_roles(ctx.author, STAFF_LIST):
            author_crew = crew(ctx.author, self)
            if author_crew is not target_crew:
                await response_message(ctx,
                                       f'Can\'t promote {member.mention} because they are on different crews.')
                return
            if check_roles(member, [ADVISOR]):
                await response_message(ctx,
                                       f'Only staff can promote to leader. '
                                       f'Ping the Doc Keeper role in {self.cache.channels.flairing_questions.mention} '
                                       f'and have a majority of leaders confirm.')
                return
            if not check_roles(ctx.author, [LEADER]):
                await response_message(ctx, f'Only leaders can make advisors on their crew.')
                return
        before = set(member.roles)
        result = await promote(member, self)
        after = set(ctx.guild.get_member(member.id).roles)

        await response_message(ctx, f'Successfully promoted {member.mention} to {result}.')
        await self.cache.channels.flair_log.send(embed=role_change(before, after, ctx.author, member))

    @commands.command(**help['demote'])
    @main_only
    @flairing_required
    @cache_update
    async def demote(self, ctx: Context, member: discord.Member):
        if not member:
            await response_message(ctx, 'You can\'t demote yourself.')
            return
        if not check_roles(ctx.author, STAFF_LIST):
            author_crew = crew(ctx.author, self)
            target_crew = crew(member, self)
            if author_crew is not target_crew:
                await response_message(ctx,
                                       f'Can\'t demote {member.mention} because they are on different crews.')
                return
            if check_roles(member, [LEADER]):
                await response_message(ctx, f'Only staff can demote leaders. Ping the Doc Keeper role in '
                                            f'{self.cache.channels.flairing_questions.mention} '
                                            f'and have a majority of leaders confirm, '
                                            f'OR have the individual being demoted confirm.')
                return
            if not check_roles(ctx.author, [LEADER]):
                await response_message(ctx, f'Only leaders can demote advisors on their crew.')
                return
        if not check_roles(member, [ADVISOR, LEADER]):
            await response_message(ctx, f'{member.mention} can\'t be demoted as they do not hold a leadership role.')
            return
        before = set(member.roles)
        result = await demote(member, self)
        after = set(ctx.guild.get_member(member.id).roles)
        await response_message(ctx, f'Successfully demoted {member.mention} from {result}.')
        await self.cache.channels.flair_log.send(embed=role_change(before, after, ctx.author, member))

    @commands.command(**help['make_lead'])
    @main_only
    @flairing_required
    @role_call(STAFF_LIST)
    @cache_update
    async def make_lead(self, ctx: Context, member: discord.Member):
        if not member:
            await response_message(ctx, 'You can\'t promote yourself.')
            return
        try:
            crew(member, self)
        except ValueError:
            await response_message(ctx, f'You can\'t promote someone who is not in a crew.')
            return
        if check_roles(member, [LEADER]):
            await response_message(ctx, f'{member.mention} is already a leader.')
            return
        before = set(member.roles)
        await promote(member, self)
        await promote(member, self)
        after = set(ctx.guild.get_member(member.id).roles)
        await response_message(ctx, f'Successfully made {member.mention} a leader.')
        await self.cache.channels.flair_log.send(embed=role_change(before, after, ctx.author, member))

    @commands.command(**help['unflair'])
    @main_only
    @flairing_required
    @cache_update
    async def unflair(self, ctx: Context, user: Optional[str]):
        if user:
            try:
                member = user_by_id(user, self)
            except ValueError as e:
                await response_message(ctx, str(e))
                return
            if not check_roles(ctx.author, STAFF_LIST):
                if member.id == ctx.author.id:
                    await response_message(ctx, 'You can unflair yourself by typing `,unflair` with nothing after it.')
                    return
                try:
                    compare_crew_and_power(ctx.author, member, self)
                except ValueError as e:
                    await response_message(ctx, str(e))
                    return
        else:
            member = ctx.author
        user_crew = crew_lookup(crew(member, self), self)
        of_before, of_after = None, None
        if user_crew.overflow:
            of_user = self.cache.overflow_server.get_member(member.id)
            of_before = set(of_user.roles)
        before = set(member.roles)
        await unflair(member, ctx.author, self)
        await response_message(ctx, f'Successfully unflaired {member.mention} from {user_crew.name}.')
        after = set(ctx.guild.get_member(member.id).roles)
        if user_crew.overflow:
            overflow_server = discord.utils.get(self.bot.guilds, name=OVERFLOW_SERVER)
            of_after = set(overflow_server.get_member(member.id).roles)
        await self.cache.channels.flair_log.send(
            embed=role_change(before, after, ctx.author, member, of_before, of_after))

    @commands.command(**help['flair'])
    @main_only
    @flairing_required
    @cache_update
    async def flair(self, ctx: Context, member: discord.Member, *, new_crew: str = None):
        if check_roles(member, [BOT]):
            await response_message(ctx, 'You can\'t flair a bot!')
            return
        author_pl = power_level(ctx.author)
        if author_pl == 0:
            await response_message(ctx, 'You cannot flair users unless you are an Advisor, Leader or Staff.')
            return
        try:
            user_crew = crew(member, self)
        except ValueError:
            user_crew = None
        if new_crew:
            flairing_crew = crew_lookup(new_crew, self)
            if flairing_crew.name != user_crew and not check_roles(ctx.author, STAFF_LIST):
                await response_message(ctx, 'You can\'t flair people for other crews unless you are Staff.')
                return
        else:
            flairing_crew = crew_lookup(crew(ctx.author, self), self)

        if member.id == ctx.author.id and user_crew == flairing_crew.name:
            await response_message(ctx, f'Stop flairing yourself, stop flairing yourself.')
            return
        overflow_mem = discord.utils.get(self.cache.overflow_server.members, id=member.id)
        if flairing_crew.overflow and not overflow_mem:
            self.cache.timer = 0
            await self.cache.update(self)
            overflow_mem = discord.utils.get(self.cache.overflow_server.members, id=member.id)
            if not overflow_mem:
                await response_message(ctx,
                                       f'{member.mention} is not in the overflow server and '
                                       f'{flairing_crew.name} is an overflow crew. https://discord.gg/ARqkTYg')
                return
        of_before, of_after = None, None
        if flairing_crew.overflow:
            of_user = self.cache.overflow_server.get_member(member.id)
            of_before = set(of_user.roles)
        before = set(member.roles)
        if user_crew == flairing_crew.name:
            await response_message(ctx, f'{str(member)} is already flaired for {user_crew}!')
            return
        if user_crew:
            if author_pl == 3:
                await unflair(member, ctx.author, self)
                await response_message(ctx, f'Unflaired {member.mention} from {user_crew}.')
            else:
                await response_message(ctx, f'{member.display_name} '
                                            f'must be unflaired for their current crew before they can be flaired. ')
                return

        await flair(member, flairing_crew, self)
        await response_message(ctx, f'Successfully flaired {member.mention} for {flairing_crew.name}.')

        after = set(ctx.guild.get_member(member.id).roles)
        if flairing_crew.overflow:
            overflow_server = discord.utils.get(self.bot.guilds, name=OVERFLOW_SERVER)
            of_after = set(overflow_server.get_member(member.id).roles)
        await self.cache.channels.flair_log.send(
            embed=role_change(before, after, ctx.author, member, of_before, of_after))

    @commands.command(**help['overflow'])
    @cache_update
    @role_call([ADMIN, MINION])
    async def overflow(self, ctx: Context):
        overflow_role = set()
        for member in self.cache.scs.members:
            if check_roles(member, OVERFLOW_ROLE):
                overflow_role.add(f'{str(member)} {member.id}')
        other_set = set()
        other_members = self.cache.overflow_server.members
        for member in other_members:
            if any((role.name in self.cache.crews for role in member.roles)):
                other_set.add(f'{str(member)} {member.id}')
                continue
        first = overflow_role - other_set
        second = other_set - overflow_role
        out = ['These members have the role, but are not in an overflow crew.']
        for member in first:
            out.append(f'> {member}')
        out.append('These members are flaired in the overflow server, but have no role here')
        for member in second:
            out.append(f'> {member}')
        output = split_on_length_and_separator('\n'.join(out), length=2000, separator='\n')
        for put in output:
            await ctx.send(put)

    @commands.command(**help['flairing_off'])
    @cache_update
    @role_call(STAFF_LIST)
    async def flairing_off(self, ctx: Context):
        self.cache.flairing_allowed = False
        await ctx.send('Flairing has been disabled for the time being.')

    @commands.command(**help['flairing_on'])
    @cache_update
    @role_call(STAFF_LIST)
    async def flairing_on(self, ctx: Context):
        self.cache.flairing_allowed = True
        await ctx.send('Flairing has been re-enabled.')

    @commands.command(**help['pending'])
    @cache_update
    @role_call(STAFF_LIST)
    async def pending(self, ctx: Context):
        await ctx.send('Printing all current battles.')
        for channel, battle in self.battle_map.items():
            if battle:
                chan = discord.utils.get(ctx.guild.channels, name=channel_from_key(channel))
                await ctx.send(chan.mention)
                await send_sheet(ctx, battle)

    @commands.command(**help['recache'])
    @role_call(STAFF_LIST)
    async def recache(self, ctx: Context):
        self.cache.timer = 0
        await self.cache.update(self)
        await ctx.send('The cache has been cleared, everything should be updated now.')

    @commands.command(**help['chars'])
    @ss_channel
    async def chars(self, ctx):
        emojis = all_emojis(self.bot)
        out = []
        for emoji in emojis:
            out.append(f'{emoji[0]}: {emoji[1]}\n')

        out = "".join(out)
        out = split_on_length_and_separator(out, 1999, ']')
        for split in out:
            await ctx.author.send(split)

    @commands.command(**help['guide'])
    async def guide(self, ctx):
        await ctx.send('https://docs.google.com/document/d/1ICpPcH3etnkcZk8Zc9wn2Aqz1yeAIH_cAWPPUUVgl9I/edit')

    @commands.command(**help['guide'])
    @cache_update
    @role_call(STAFF_LIST)
    async def cooldown(self, ctx):
        current_cooldown = set()
        with open(TEMP_ROLES_FILE, 'r') as file:
            lines = file.readlines()
            out = []
            current = time.time()
            for line in lines:
                if len(line) > 17:
                    member_id = int(line[:line.index(' ')])
                    reset = float(line[line.index(' ') + 1:-1])
                    member = self.cache.scs.get_member(member_id)
                    current_cooldown.add(member_id)
                    diff = reset - current
                    hours = int(diff // 3600)
                    minutes = int((diff % 3600) // 60)
                    seconds = int(diff % 60)
                    out.append(f'{str(member)} has {hours} hours, {minutes} minutes, {seconds} seconds'
                               f'  left on their join cooldown.')
        output = split_on_length_and_separator('\n'.join(out), length=2000, separator='\n')
        for person in self.cache.scs.members:
            if check_roles(person, [JOIN_CD]):
                if person.id not in current_cooldown:
                    await person.remove_roles(self.cache.roles.join_cd)
                    await self.cache.channels.flair_log.send(f'{person.display_name}\'s join cooldown ended.')

        for put in output:
            await ctx.send(put)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error):
        """The event triggered when an error is raised while invoking a command.
        Parameters
        ------------
        ctx: commands.Context
            The context used for command invocation.
        error: commands.CommandError
            The Exception raised.
        """

        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return

        # This prevents any cogs with an overwritten cog_command_error being handled here.
        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        ignored = ()

        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)

        # Anything in ignored will return and prevent anything happening.
        # if isinstance(error, ignored):
        #     return

        if isinstance(error, commands.DisabledCommand):
            await ctx.send(f'{ctx.command} has been disabled.')
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send(f'{str(error)}, try ",help" for a list of commands.')

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.send(f'{ctx.command} can not be used in Private Messages.')
            except discord.HTTPException:
                pass

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(str(error))
        elif isinstance(error, StateError):
            await ctx.send(f'"{ctx.command}" did not work because:{error.message}')
        elif isinstance(error, discord.ext.commands.errors.MemberNotFound):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} failed because:{str(error)}\n'
                           f'Try using `{self.bot.command_prefix}{ctx.command.name} @Member`.')
        elif str(error) == 'The read operation timed out':
            await ctx.send('The google sheets API isn\'t responding, wait 60 seconds and try again')
        else:
            # All other Errors not returned come here. And we can just print the default TraceBack.
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} failed because:{str(error)}')
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def main():
    load_dotenv()
    token = os.getenv('DISCORD_TOKEN')
    bot = commands.Bot(command_prefix=os.getenv('PREFIX'), intents=discord.Intents.all())
    cache = Cache()
    bot.add_cog(ScoreSheetBot(bot, cache))

    bot.run(token)


if __name__ == '__main__':
    main()
