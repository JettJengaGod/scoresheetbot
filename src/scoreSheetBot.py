import os
import sys
import traceback
import time
import discord
import math
import functools
from asyncio import sleep
from datetime import date
from discord.ext import commands, tasks, menus
from discord.ext.commands import Greedy
from dotenv import load_dotenv
from typing import Dict, Optional, Union, Iterable
from helpers import *
from db_helpers import *
from battle import Battle
from cache import Cache
from character import all_emojis, string_to_emote, all_alts, CHARACTERS
from decorators import *
from help import help_doc
from constants import *

from gambit_helpers import update_gambit_sheet
import logging

logging.basicConfig(level=logging.INFO)

Context = discord.ext.commands.Context

class ScoreSheetBot(commands.Cog):
    def __init__(self, bot: commands.bot, cache: Cache):
        self.bot = bot
        self.battle_map: Dict[str, Battle] = {}
        self.cache = cache
        self.auto_cache.start()
        self._gambit_message = None

    def _current(self, ctx) -> Battle:
        if key_string(ctx) in self.battle_map:
            return self.battle_map[key_string(ctx)]
        else:
            return None

    async def gambit_message(self, msg_id: int) -> discord.Message:
        if not self._gambit_message:
            try:
                msg = await self.cache.channels.gambit_announce.fetch_message(msg_id)
                self._gambit_message = msg
            except discord.errors.NotFound:
                return None
        return self._gambit_message

    async def _battle_crew(self, ctx: Context, user: discord.Member) -> Optional[str]:
        crew_name = crew(user, self)
        if crew_name in (self._current(ctx).team1.name, self._current(ctx).team2.name):
            return crew_name
        return None

    async def _reject_outsiders(self, ctx: Context):
        if self._current(ctx).mock:
            return
        if not await self._battle_crew(ctx, ctx.author):
            if not check_roles(ctx.author, [DOCS, ADMIN, ADVISOR, LEADER]):
                raise Exception('You need to be an advisor or leader to run this command.')
            raise Exception('You are not in this battle, stop trying to mess with it.')

    async def _set_current(self, ctx: Context, battle: Battle):
        self.battle_map[key_string(ctx)] = battle
        await update_channel_open(NO, ctx.channel)

    async def _clear_current(self, ctx):
        self.battle_map.pop(key_string(ctx), None)
        await unlock(ctx.channel)
        await update_channel_open('', ctx.channel)

    def cog_unload(self):
        self.auto_cache.cancel()

    async def cog_before_invoke(self, ctx):
        if ctx.channel.id in disabled_channels():
            await ctx.message.delete()
            msg = await ctx.send(f'Jettbot is disabled for this channel please use <#{BOT_CORNER_ID}> instead.')
            await msg.delete(delay=5)
            raise ValueError('Jettbot is Disabled for this channel.')
        if command_lookup(ctx.command.name)[1]:
            await ctx.message.delete(delay=2)
            msg = await ctx.send(f'{ctx.command.name} is deactivated, and cannot be used for now.')
            await msg.delete(delay=5)
            raise ValueError(f'{ctx.command.name} is deactivated, and cannot be used for now.')

    async def cog_after_invoke(self, ctx):
        if os.getenv('VERSION') == 'PROD':
            increment_command_used(ctx.command.name)

    @tasks.loop(seconds=CACHE_TIME_SECONDS)
    async def auto_cache(self):
        await cache_process(self)

    @auto_cache.before_loop
    async def wait_for_bot(self):
        await self.bot.wait_until_ready()

    """ Future commands for role listening """

    # @commands.Cog.listener()
    # async def on_member_remove(self, user):
    #     print([role.name for role in user.roles], user.guild.name)
    #
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if os.getenv('VERSION') == 'PROD':
            if before.roles != after.roles:
                update_member_roles(after)
                try:
                    after_crew = crew(after, self)
                except ValueError:
                    after_crew = None
                if not crew_correct(after, after_crew):
                    if after_crew:
                        after_crew = crew_lookup(after_crew, self)
                    update_member_crew(after, after_crew)
                    self.cache.minor_update(self)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):

        if os.getenv('VERSION') == 'PROD':
            role_ids = find_member_roles(member)
            if role_ids:
                roles = [discord.utils.get(member.guild.roles, id=role_id) for role_id in role_ids]
                await member.add_roles(*roles)
            else:
                add_member_and_roles(member)

    @commands.command(help='Shows this command')
    async def help(self, ctx, *group):
        """Gets all categories and commands of mine."""
        main_user = self.cache.scs.get_member(ctx.author.id)
        if not main_user:
            await ctx.author.send('You need to be a member of the scs to access this help.')
            return
        staff = check_roles(main_user, STAFF_LIST)
        if not group:
            halp = discord.Embed(title='Group Listing and Uncategorized Commands',
                                 description=f'Use `{self.bot.command_prefix}help *group*` to find out more about them!')
            groups_desc = ''
            for cmd in self.bot.walk_commands():
                if isinstance(cmd, discord.ext.commands.Group):
                    groups_desc += ('{} - {}'.format(cmd, cmd.brief) + '\n')
            halp.add_field(name='Cogs', value=groups_desc[0:len(groups_desc) - 1], inline=False)
            cmds_desc = ''
            for y in self.bot.walk_commands():
                if y.name == 'help':
                    cmds_desc += ('{} - {}'.format(y.name, y.help) + '\n')
            halp.add_field(name='Help Commands', value=cmds_desc[0:len(cmds_desc) - 1], inline=False)
            if not isinstance(ctx.channel, discord.channel.DMChannel):
                await ctx.message.add_reaction(emoji='✉')
            await ctx.message.author.send(embed=halp)
        else:
            if len(group) > 1:
                halp = discord.Embed(title='Error!', description='You can only send 1 group or command name!',
                                     color=discord.Color.red())
                await ctx.message.author.send(embed=halp)
                return
            else:
                found = False
                for cmd in self.bot.walk_commands():
                    for grp in group:
                        if cmd.name == grp:
                            if isinstance(cmd, discord.ext.commands.Group) and not cmd.hidden:
                                cmds = []
                                halp = discord.Embed(title=group[0] + ' Command Listing',
                                                     description=cmd.brief)
                                for c in self.bot.walk_commands():
                                    if c.help == cmd.name:
                                        if staff or not c.hidden:
                                            cmds.append(c)
                                cmds.sort(key=lambda c: c.name)
                                for c in cmds:
                                    halp.add_field(name=c.name, value=c.brief, inline=False)
                            else:
                                if staff or not cmd.hidden:
                                    halp = discord.Embed(title=group[0],
                                                         description=f'{cmd.description}\n'
                                                                     f'{self.bot.command_prefix}{cmd.name} {cmd.usage}')
                                else:
                                    await ctx.author.send('That command is hidden.')
                            found = True
                if not found:
                    halp = discord.Embed(title='Error!', description=f'Command {group} not found.',
                                         color=discord.Color.red())
                else:
                    if not isinstance(ctx.channel, discord.channel.DMChannel):
                        await ctx.message.add_reaction(emoji='✉')
                await ctx.message.author.send('', embed=halp)

    ''' **********************************CB COMMANDS ******************************************'''

    @commands.group(name='cb', brief='Commands for running a crew battle', invoke_without_command=True)
    async def cb(self, ctx):
        await self.help(ctx, 'cb')

    @commands.command(**help_doc['lock'])
    @main_only
    @role_call([MINION, ADMIN, DOCS, LEADER, ADVISOR])
    @ss_channel
    async def lock(self, ctx: Context, streamer: Optional[discord.Member]):

        if 'testing' in ctx.channel.name:
            await ctx.send('This channel cannot be locked')
            return

        try:
            current = self._current(ctx)
        except ValueError:
            await ctx.send('There needs to be a ranked battle running to use this command.')
            return
        if current and not current.mock:
            if not check_roles(ctx.author, STAFF_LIST):
                await self._reject_outsiders(ctx)
            overwrites = ctx.channel.overwrites

            crew_overwrite = discord.PermissionOverwrite(send_messages=True, add_reactions=True)
            if crew_lookup(current.team1.name, self).overflow:
                _, mems = members_with_str_role(current.team1.name, self)
                for mem in mems:
                    overwrites[mem] = crew_overwrite
            else:
                cr_role_1 = discord.utils.get(ctx.guild.roles, name=current.team1.name)
                overwrites[cr_role_1] = crew_overwrite

            if crew_lookup(current.team2.name, self).overflow:
                _, mems = members_with_str_role(current.team2.name, self)
                for mem in mems:
                    overwrites[mem] = crew_overwrite
            else:
                cr_role_2 = discord.utils.get(ctx.guild.roles, name=current.team2.name)
                overwrites[cr_role_2] = crew_overwrite
            everyone_overwrite = discord.PermissionOverwrite(send_messages=False, manage_messages=False,
                                                             add_reactions=False)
            overwrites[self.cache.roles.everyone] = everyone_overwrite
            out = f'Room Locked to only {current.team1.name} and {current.team2.name}.'
            if streamer:
                overwrites[streamer] = crew_overwrite
                out += f' As the streamer, {streamer.display_name} also can talk.'
            await ctx.channel.edit(overwrites=overwrites)
            await ctx.send(out)
        else:
            await ctx.send('There needs to be a ranked battle running to use this command.')
            return

    @commands.command(**help_doc['unlock'])
    @main_only
    @role_call([MINION, ADMIN, DOCS, LEADER, ADVISOR])
    @ss_channel
    async def unlock(self, ctx: Context):
        await unlock(ctx.channel)
        await ctx.send('Unlocked the channel for all crews to use.')

    @commands.command(**help_doc['battle'], aliases=['challenge'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
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
            await ctx.send(f'If you are in a playoff battle, please use `{self.bot.command_prefix}playoffbattle`')
            await self._set_current(ctx, Battle(user_crew, opp_crew, size))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['playoffbattle'], aliases=['pob', 'playoff'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def playoffbattle(self, ctx: Context, user: discord.Member, size: int):
        if size < 1:
            await ctx.send('Please enter a size greater than 0.')
            return
        user_crew = crew(ctx.author, self)
        opp_crew = crew(user, self)
        if not user_crew:
            await ctx.send(f'{ctx.author.name}\'s crew didn\'t show up correctly. '
                           f'They might not be in a crew. '
                           f'Please contact an admin if this is incorrect.')
            return
        if not opp_crew:
            await ctx.send(f'{user.name}\'s crew didn\'t show up correctly. '
                           f'They might not be in a crew. '
                           f'Please contact an admin if this is incorrect.')
            return
        if user_crew != opp_crew:
            user_cr = crew_lookup(user_crew, self)
            opp_cr = crew_lookup(opp_crew, self)
            if user_cr.playoff != opp_cr.playoff or user_cr.playoff == PlayoffType.NO_PLAYOFF:
                await ctx.send(
                    f'{user_crew} and {opp_crew} are not in the same playoffs or are not in playoffs at all.')
                return
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, playoff=True))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['mock'])
    @main_only
    @no_battle
    @ss_channel
    async def mock(self, ctx: Context, team1: str, team2: str, size: int):
        if size < 1:
            await ctx.send('Please enter a size greater than 0.')
            return
        await self._set_current(ctx, Battle(team1, team2, size, mock=True))
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help_doc['countdown'])
    @ss_channel
    async def countdown(self, ctx: Context, seconds: Optional[int] = 3):
        if seconds > 10 or seconds < 1:
            await ctx.send('You can only countdown from 10 or less!')
            return
        await ctx.send(f'Counting down from {seconds}')
        while seconds > 0:
            await ctx.send(f'{seconds}')
            seconds -= 1
            await sleep(1)
        await ctx.send('Finished!')

    @commands.command(**help_doc['send'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def send(self, ctx: Context, user: discord.Member, team: str = None):
        if self._current(ctx).mock:
            if team:
                self._current(ctx).add_player(team, escape(user.display_name), ctx.author.mention, user.id)
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
                if self._current(ctx).playoff and check_roles(user, [PLAYOFF_LIMITED]):
                    await ctx.send(f'{user.mention} is playoff locked and cannot play in playoff battles.')
                    return
                self._current(ctx).add_player(author_crew, escape(user.display_name), ctx.author.mention, user.id)
            else:
                await ctx.send(f'{escape(user.display_name)} is not on {author_crew} please choose someone else.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['use_ext'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def use_ext(self, ctx: Context, team: str = None):
        if self._current(ctx).mock:
            if team:
                if self._current(ctx).ext_used(team):
                    await ctx.send(f'{team} has already used their extension.')
                    return
            else:
                await ctx.send(f'During a mock you need to use your extension, like this'
                               f' `,ext teamname`.')
                return
        else:
            await self._reject_outsiders(ctx)
            author_crew = await self._battle_crew(ctx, ctx.author)

            if self._current(ctx).ext_used(author_crew):
                await ctx.send(f'{team} has already used their extension.')
                return
            else:
                await ctx.send(f'{author_crew} just used their extension. '
                               f'They now get 5 more minutes for their next player to be in the arena.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['ext'])
    @main_only
    @has_sheet
    @ss_channel
    async def ext(self, ctx):
        await ctx.send(self._current(ctx).ext_str())

    @commands.command(**help_doc['replace'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def replace(self, ctx: Context, user: discord.Member, team: str = None):
        if self._current(ctx).mock:
            if team:
                self._current(ctx).replace_player(team, escape(user.display_name), ctx.author.mention, user.id)
            else:
                await ctx.send(f'During a mock you need to replace with a teamname, like this'
                               f' `,replace @playername teamname`.')
                return
        else:
            await self._reject_outsiders(ctx)
            current_crew = await self._battle_crew(ctx, ctx.author)
            if current_crew == await self._battle_crew(ctx, user):
                if self._current(ctx).playoff and check_roles(user, [PLAYOFF_LIMITED]):
                    await ctx.send(f'{user.mention} is playoff limited and cannot play in playoff battles.')
                    return
                self._current(ctx).replace_player(current_crew, escape(user.display_name), ctx.author.mention, user.id)

            else:
                await ctx.send(f'{escape(user.display_name)} is not on {current_crew}, please choose someone else.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['end'])
    @main_only
    @has_sheet
    @ss_channel
    async def end(self, ctx: Context, char1: Union[str, discord.Emoji], stocks1: int, char2: Union[str, discord.Emoji],
                  stocks2: int):
        await self._reject_outsiders(ctx)

        self._current(ctx).finish_match(stocks1, stocks2,
                                        Character(str(char1), self.bot, is_usable_emoji(char1, self.bot)),
                                        Character(str(char2), self.bot, is_usable_emoji(char2, self.bot)))
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['endlag'])
    @main_only
    @has_sheet
    @ss_channel
    async def endlag(self, ctx: Context, char1: Union[str, discord.Emoji], stocks1: int,
                     char2: Union[str, discord.Emoji],
                     stocks2: int):
        await self._reject_outsiders(ctx)

        self._current(ctx).finish_lag(stocks1, stocks2,
                                      Character(str(char1), self.bot, is_usable_emoji(char1, self.bot)),
                                      Character(str(char2), self.bot, is_usable_emoji(char2, self.bot)))
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['resize'])
    @main_only
    @is_lead
    @has_sheet
    @ss_channel
    async def resize(self, ctx: Context, new_size: int):
        await self._reject_outsiders(ctx)
        self._current(ctx).resize(new_size)
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['arena'], aliases=['id', 'arena_id', 'lobby'])
    @main_only
    @has_sheet
    @ss_channel
    async def arena(self, ctx: Context, id_str: str = ''):
        if id_str and (check_roles(ctx.author, [LEADER, ADVISOR, ADMIN, MINION, STREAMER, CERTIFIED]
                                   ) or self._current(ctx).mock):
            self._current(ctx).id = id_str
            await ctx.send(f'Updated the id to {id_str}')
            return
        await ctx.send(f'The lobby id is {self._current(ctx).id}')

    @commands.command(**help_doc['stream'], aliases=['streamer', 'stream_link'])
    @main_only
    @has_sheet
    @ss_channel
    async def stream(self, ctx: Context, stream: str = ''):
        if stream and (check_roles(ctx.author, [LEADER, ADVISOR, ADMIN, MINION, STREAMER, CERTIFIED]
                                   ) or self._current(ctx).mock):
            if '/' not in stream:
                stream = 'https://twitch.tv/' + stream
            self._current(ctx).stream = stream
            await ctx.send(f'Updated the stream to {stream}')
            return
        await ctx.send(f'The stream is {self._current(ctx).stream}')

    @commands.command(**help_doc['undo'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def undo(self, ctx):
        await self._reject_outsiders(ctx)
        if not self._current(ctx).undo():
            await ctx.send('Note: undoing a replace on the scoresheet doesn\'t actually undo the replace, '
                           'you need to use `,replace @player` with the original player to do that.')

        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['confirm'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def confirm(self, ctx: Context):
        await self._reject_outsiders(ctx)
        current = self._current(ctx)
        if current.battle_over():
            if current.mock:
                await self._clear_current(ctx)
                await ctx.send(f'This battle was confirmed by {ctx.author.mention}.')
            else:
                current.confirm(await self._battle_crew(ctx, ctx.author))
                await send_sheet(ctx, battle=current)
                if current.confirmed():
                    today = date.today()

                    output_channels = [discord.utils.get(ctx.guild.channels, name=DOCS_UPDATES),
                                       discord.utils.get(ctx.guild.channels, name=OUTPUT)]
                    winner = current.winner().name
                    loser = current.loser().name
                    if current.playoff:
                        league_id = crew_lookup(winner, self).playoff.value
                        output_channels.pop(0)
                        output_channels.insert(0,
                                               discord.utils.get(ctx.guild.channels,
                                                                 name=PLAYOFF_CHANNEL_NAMES[league_id - 1]))
                    else:
                        league_id = 1
                    current = self._current(ctx)
                    if not current:
                        return
                    await self._clear_current(ctx)
                    for output_channel in output_channels:
                        await output_channel.send(
                            f'**{today.strftime("%B %d, %Y")}- {winner} vs. {loser} **\n'
                            f'{self.cache.crews_by_name[winner].rank} crew defeats'
                            f' {self.cache.crews_by_name[loser].rank} crew in a '
                            f'{current.team1.num_players}v{current.team2.num_players} battle!\n'
                            f'from  {ctx.channel.mention}.')
                        link = await send_sheet(output_channel, current)
                    battle_id = add_finished_battle(current, link.jump_url, league_id)
                    await ctx.send(
                        f'The battle between {current.team1.name} and {current.team2.name} '
                        f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
                        f'(Battle number:{battle_id})')
        else:
            await ctx.send('The battle is not over yet, wait till then to confirm.')

    @commands.command(**help_doc['clear'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def clear(self, ctx):
        if not check_roles(ctx.author, STAFF_LIST):
            await self._reject_outsiders(ctx)
        if self._current(ctx).mock:
            await ctx.send('If you just cleared a crew battle to troll people, be warned this is a bannable offence.')
        await self._clear_current(ctx)
        await ctx.send(f'{ctx.author.mention} cleared the crew battle.')

    @commands.command(**help_doc['status'])
    @main_only
    @has_sheet
    @ss_channel
    async def status(self, ctx):
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['timer'])
    @main_only
    @has_sheet
    @ss_channel
    async def timer(self, ctx):
        await ctx.send(self._current(ctx).timer())

    @commands.command(**help_doc['timerstock'])
    @main_only
    @has_sheet
    @ss_channel
    @is_lead
    async def timerstock(self, ctx, team: str = None):
        if self._current(ctx).mock:
            if team:
                self._current(ctx).timer_stock(team, ctx.author.mention)
            else:
                await ctx.send(f'During a mock you need to take a timer_stock with a teamname, like this'
                               f' `,timer_stock teamname`.')
                return
        else:
            await self._reject_outsiders(ctx)
            current_crew = await self._battle_crew(ctx, ctx.author)
            self._current(ctx).timer_stock(current_crew, ctx.author.mention)

        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['char'])
    async def char(self, ctx: Context, emoji):
        if is_usable_emoji(emoji, self.bot):
            await ctx.send(emoji)
        else:
            await ctx.send(f'What you put: {string_to_emote(emoji, self.bot)}')
            await ctx.send(f'All alts in order: {all_alts(emoji, self.bot)}')

    @commands.command(**help_doc['chars'])
    @ss_channel
    async def chars(self, ctx):
        emojis = all_emojis(self.bot)
        out = []
        for emoji in emojis:
            out.append(f'{emoji[0]}: {emoji[1]}\n')

        await send_long(ctx.author, "".join(out), ']')

    ''' *************************************** CREW COMMANDS ********************************************'''

    @commands.group(name='crews', brief='Commands for crews, including stats and rankings', invoke_without_command=True)
    async def crews(self, ctx):
        await self.help(ctx, 'crews')

    @commands.command(**help_doc['rankings'])
    async def rankings(self, ctx):
        crews_sorted_by_ranking = sorted([cr for cr in self.cache.crews_by_name.values() if cr.ladder],
                                         key=lambda x: int(x.ladder[1:x.ladder.index('/')]))
        crew_ranking_str = [f'{cr.name} {cr.rank}' for cr in crews_sorted_by_ranking]

        pages = menus.MenuPages(source=Paged(crew_ranking_str, title='Legacy Crews Rankings'),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['groups'])
    async def groups(self, ctx, group: Optional[str]):
        if not group:
            group = 'legacy'
        if group not in ['legacy', 'tempered']:
            await ctx.send(f'`{group}` is not `legacy` or `tempered` try `{self.bot.command_prefix}groups legacy`')
        if group == 'legacy':
            playoff = PlayoffType.LEGACY
            group_size = 5
        else:
            playoff = PlayoffType.TEMPERED
            group_size = 4

        playoff_crews = sorted([cr for cr in self.cache.crews_by_name.values() if cr.playoff == playoff],
                               key=lambda x: x.pool)
        playoff_crew_str = []
        for cr in playoff_crews:
            record = crew_record(cr, playoff.value)
            playoff_crew_str.append(f'{cr.name} {record[1]}/{record[2] - record[1]}')

        pages = menus.MenuPages(
            source=PoolPaged(playoff_crew_str, title=f'{playoff.name} Playoffs Pools', per_page=group_size),
            clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['battles'])
    async def battles(self, ctx):

        pages = menus.MenuPages(source=Paged(all_battles(), title='Battles'), clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['vod'])
    @role_call([CERTIFIED, ADMIN, DOCS, MINION])
    async def vod(self, ctx, battle_id: int, vod: str):

        set_vod(battle_id, vod)
        await ctx.send(f'{ctx.author.name} set battle {battle_id}\'s vod to {vod}.')

    @commands.command(**help_doc['playerstats'])
    @main_only
    async def playerstats(self, ctx, *, name: str = None):
        if name:
            member = member_lookup(name, self)

        else:
            member = ctx.author
        taken, lost = player_stocks(member)
        total, wins = player_record(member)
        title = f'Stats for {str(member)}'
        embed = discord.Embed(title=title, color=member.color)
        embed.add_field(name='Crews record while participating:', value=f'{wins}/{total - wins}', inline=False)
        embed.add_field(name='Stocks Taken/Lost', value=f'{taken}/{lost}', inline=False)
        pc = player_chars(member)
        embed.add_field(name='Characters played', value='how many battles played in ', inline=False)
        for char in pc:
            emoji = string_to_emote(char[1], self.bot)
            embed.add_field(name=emoji, value=f'{char[0]}', inline=True)
        await ctx.send(embed=embed)

    @commands.command(**help_doc['history'])
    @main_only
    async def history(self, ctx, *, name: str = None):
        if name:
            member = member_lookup(name, self)

        else:
            member = ctx.author
        if member.id == 775586622241505281:
            await ctx.send('Don\'t use EvilJett for this')
            return
        embed = discord.Embed(title=f'Crew History for {str(member)}', color=member.color)
        desc = []
        current = member_crew_and_date(member)
        if current:
            desc.append(f'Current crew: {current[0]} Joined: {current[1].strftime("%m/%d/%Y")}')
        past = member_crew_history(member)
        desc.append('Past Crew              Joined            Left')
        for cr_name, joined, left in past:
            j = joined.strftime('%m/%d/%Y')
            l = left.strftime('%m/%d/%Y')
            desc.append(f'{cr_name}: {j}       {l}')
        embed.description = '\n'.join(desc)
        await send_long_embed(ctx, embed)

    @commands.command(**help_doc['crewstats'])
    @main_only
    async def crewstats(self, ctx, *, name: str = None):
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
        record = crew_record(actual_crew)
        if not record[2]:
            await ctx.send(f'{actual_crew.name} does not have any recorded crew battles with the bot.')
            return
        title = f'{actual_crew.name}: {record[1]}-{int(record[2]) - int(record[1])}'
        pages = menus.MenuPages(
            source=Paged(crew_matches(actual_crew), title=title, color=actual_crew.color, thumbnail=actual_crew.icon),
            clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['rank'])
    @main_only
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

    @commands.command(**help_doc['merit'])
    @main_only
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

    @commands.command(**help_doc['logo'])
    @main_only
    async def logo(self, ctx, *, name: str = None):
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
        embed = discord.Embed(title=f'{actual_crew.name}\'s logo', color=actual_crew.color)
        embed.set_image(url=actual_crew.icon)
        await ctx.send(embed=embed)

    @commands.command(**help_doc['crew'])
    @main_only
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

    @commands.command()
    @role_call([LEADER, ADMIN, MINION, ADVISOR, DOCS])
    async def playoffs(self, ctx, *, name: str = None):
        if name:
            ambiguous = ambiguous_lookup(name, self)
            if isinstance(ambiguous, discord.Member):
                actual_crew = crew_lookup(crew(ambiguous, self), self)
            else:
                actual_crew = ambiguous
        else:
            actual_crew = crew_lookup(crew(ctx.author, self), self)
        allowed = []
        disallowed = []
        for member in self.cache.scs.members:
            try:
                cr = crew(member, self)
            except ValueError:
                cr = None
            if cr == actual_crew.name:
                if check_roles(member, [PLAYOFF_LIMITED]):
                    disallowed.append(f'> {str(member)} {member.mention}')
                else:
                    allowed.append(f'> {escape(str(member))} {member.mention}')
        desc = [f'Allowed players ({len(allowed)}):', '\n'.join(allowed), f'Disallowed players ({len(disallowed)}):',
                '\n'.join(disallowed)]
        out = discord.Embed(title=f'Eligibility of {actual_crew.name} players for playoffs',
                            description='\n'.join(desc), color=actual_crew.color)
        await send_long_embed(ctx, out)

    ''' ************************************FLAIRING COMMANDS ********************************************'''

    @commands.group(name='flairing', brief='Commands for flairing and unflairing', invoke_without_command=True)
    async def flairing(self, ctx):
        await self.help(ctx, 'flairing')

    @commands.command(**help_doc['promote'])
    @main_only
    @flairing_required
    async def promote(self, ctx: Context, member: discord.Member):
        if not member:
            await response_message(ctx, 'You can\'t promote yourself.')
            return
        try:
            target_crew = crew(member, self)
        except ValueError:
            await response_message(ctx, f'You can\'t promote someone who is not in a crew.')
            return
        if check_roles(member, [LEAD_RESTRICT]):
            await response_message(ctx,
                                   f'{member.mention} is leadership restricted and can\'t be made a leader or advisor.')
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

    @commands.command(**help_doc['demote'])
    @main_only
    @flairing_required
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

    @commands.command(hidden=True)
    @main_only
    @flairing_required
    @role_call(STAFF_LIST)
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
        if check_roles(member, [LEAD_RESTRICT]):
            await response_message(ctx, f'{member.mention} is leadership restricted and can\'t be made a leader.')
            return
        before = set(member.roles)
        await promote(member, self)
        await promote(member, self)
        after = set(ctx.guild.get_member(member.id).roles)
        await response_message(ctx, f'Successfully made {member.mention} a leader.')
        await self.cache.channels.flair_log.send(embed=role_change(before, after, ctx.author, member))

    @commands.command(**help_doc['unflair'])
    @main_only
    @flairing_required
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

        if check_roles(member, [OVERFLOW_ROLE]):
            oveflow_member = discord.utils.get(self.cache.overflow_server.members, id=member.id)
            if not oveflow_member:
                before = set(member.roles)
                await member.edit(nick=nick_without_prefix(member.display_name))
                await member.remove_roles(self.cache.roles.overflow)
                await member.remove_roles(self.cache.roles.advisor, self.cache.roles.leader)
                await track_cycle(member, self.cache.scs)
                after = set(ctx.guild.get_member(member.id).roles)
                await response_message(ctx, f'Successfully unflaired {member.mention} from an overflow crew, '
                                            f'but they have left the overflow server so it\'s unclear which.')
                await self.cache.channels.flair_log.send(
                    embed=role_change(before, after, ctx.author, member))
                return
        user_crew = crew_lookup(crew(member, self), self)
        of_before, of_after = None, None
        if user_crew.overflow:
            of_user = self.cache.overflow_server.get_member(member.id)
            of_before = set(of_user.roles)
        before = set(member.roles)
        await unflair(member, ctx.author, self)
        await response_message(ctx, f'Successfully unflaired {member.mention} from {user_crew.name}.')
        if check_roles(member, [JOIN_CD]):
            mod_slot(user_crew, 1)
            unflairs, left, total = record_unflair(member, user_crew, True)
            await ctx.send(
                f'{str(member)} was on 24h cooldown so {user_crew.name} gets back a slot ({left}/{total})')
        else:
            unflairs, remaining, total = record_unflair(member, user_crew, False)
            if unflairs == 3:
                await ctx.send(f'{user_crew.name} got a flair slot back for 3 unflairs. {remaining}/{total} left.')
            else:
                await ctx.send(f'{unflairs}/3 unflairs for returning a slot.')
        after = set(ctx.guild.get_member(member.id).roles)
        if user_crew.overflow:
            overflow_server = discord.utils.get(self.bot.guilds, name=OVERFLOW_SERVER)
            of_after = set(overflow_server.get_member(member.id).roles)
        await self.cache.channels.flair_log.send(
            embed=role_change(before, after, ctx.author, member, of_before, of_after))

    @commands.command(**help_doc['flair'])
    @main_only
    @flairing_required
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
            if not check_roles(ctx.author, STAFF_LIST) and flairing_crew.name != crew(ctx.author, self):
                await response_message(ctx, 'You can\'t flair people for other crews unless you are Staff.')
                return
        else:
            flairing_crew = crew_lookup(crew(ctx.author, self), self)
        if flairing_crew.freeze and not new_crew:
            await response_message(ctx,
                                   f'WEE OOO WEE OO {flairing_crew.name} is recruitment frozen till '
                                   f'{flairing_crew.freeze} and can\'t flair people!')
            return
        if member.id == ctx.author.id and user_crew == flairing_crew.name:
            await response_message(ctx, f'Stop flairing yourself, stop flairing yourself.')
            return
        overflow_mem = discord.utils.get(self.cache.overflow_server.members, id=member.id)
        if flairing_crew.overflow and not overflow_mem:
            await self.cache.update(self)
            overflow_mem = discord.utils.get(self.cache.overflow_server.members, id=member.id)
            if not overflow_mem:
                await response_message(ctx,
                                       f'{member.mention} is not in the overflow server and '
                                       f'{flairing_crew.name} is an overflow crew. https://discord.gg/ARqkTYg')
                return

        left, total = slots(flairing_crew)
        if left <= 0:
            await response_message(ctx, f'{flairing_crew.name} has no flairing slots left ({left}/{total})')
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
            await response_message(ctx, f'{member.display_name} '
                                        f'must be unflaired for their current crew before they can be flaired. ')
            return
        try:
            await flair(member, flairing_crew, self, check_roles(ctx.author, STAFF_LIST))
        except ValueError as ve:
            await response_message(ctx, str(ve))
            return
        await response_message(ctx, f'Successfully flaired {member.mention} for {flairing_crew.name}.')
        mod_slot(flairing_crew, -1)
        record_flair(member, flairing_crew)
        await ctx.send(f'{flairing_crew.name} now has ({left - 1}/{total}) slots.')
        after = set(ctx.guild.get_member(member.id).roles)
        if flairing_crew.overflow:
            overflow_server = discord.utils.get(self.bot.guilds, name=OVERFLOW_SERVER)
            of_after = set(overflow_server.get_member(member.id).roles)
        await self.cache.channels.flair_log.send(
            embed=role_change(before, after, ctx.author, member, of_before, of_after))

    @commands.command(**help_doc['multiflair'])
    @main_only
    @flairing_required
    async def multiflair(self, ctx: Context, members: Greedy[discord.Member], new_crew: str = None):
        for member in set(members):
            await self.flair(ctx, member, new_crew=new_crew)

    ''' ***********************************GAMBIT COMMANDS ************************************************'''

    @commands.command(**help_doc['coins'])
    @main_only
    async def coins(self, ctx: Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        await ctx.send(f'{str(member)} has {member_gcoins(member)} G-Coins.')

    @commands.group(name='gamb', invoke_without_command=True)
    @main_only
    @role_call([MINION, ADMIN])
    async def gamb(self, ctx: Context):
        if current_gambit():
            await ctx.send(f'{current_gambit()}')
        else:
            await ctx.send('No Current gambit.')

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN])
    async def start(self, ctx: Context, c1: str, c2: str):
        cg = current_gambit()
        if cg:
            await response_message(ctx, f'Gambit is already started between {cg.team1} and {cg.team2}')
            return
        crew1, crew2 = crew_lookup(c1, self), crew_lookup(c2, self)
        msg = await ctx.send(f'Would you like to start a gambit between {crew1.name} and {crew2.name}?')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
        msg = await self.cache.channels.gambit_announce.send(
            f'{self.cache.roles.gambit.mention} a new gambit has started between {crew1.name} and {crew2.name}!'
            f'\nPlace your bets by typing `,bet AMOUNT CREW_NAME` in {self.cache.channels.gambit_bot.mention} '
            f'and find out the odds by typing `,odds`.')
        new_gambit(crew1, crew2, msg.id)
        await ctx.send(f'Gambit started between {crew1.name} and {crew2.name}.')
        self._gambit_message = msg

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN])
    async def close(self, ctx: Context, stream: Optional[str] = ''):
        cg = current_gambit()
        if not cg:
            await response_message(ctx, f'Gambit not started, please use `,gamb start`')
            return
        if cg.locked:
            msg = await ctx.send(f'Gambit between {cg.team1} and {cg.team2} is already locked, do you want to unlock?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
            lock_gambit(False)
            await msg.delete()
            await response_message(ctx, f'Gambit between {cg.team1} and {cg.team2} unlocked by {ctx.author.mention}.')
        else:
            lock_gambit(True)
            cg = current_gambit()
            await response_message(ctx, f'Gambit between {cg.team1} and {cg.team2} locked by {ctx.author.mention}.')
            await self.cache.channels.gambit_announce.send(
                f'{self.cache.roles.gambit.mention}: {cg.team1} vs {cg.team2} has started! {stream}',
                embed=cg.embed(crew_lookup(cg.team1, self).abbr, crew_lookup(cg.team2, self).abbr))
            if self._gambit_message:
                await self._gambit_message.delete()

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN])
    async def cancel(self, ctx: Context):
        cg = current_gambit()
        if not cg:
            await response_message(ctx, f'Gambit not started, please use `,gamb start`')
            return
        msg = await ctx.send(f'Are you sure you want to cancel the gambit between {cg.team1} and {cg.team2}?')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
        for member_id, amount, cr in all_bets():
            member = self.bot.get_user(member_id)
            total = refund_member_gcoins(member, amount)
            await member.send(f'The gambit between {cg.team1} and {cg.team2} was canceled, '
                              f'you have been refunded {amount} G-Coins for your bet on {cr}.\n'
                              f'You now have {total} G-Coins.')
        cancel_gambit()
        await ctx.send(f'Gambit between {cg.team1} and {cg.team2} cancelled. All participants have been refunded.')

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN])
    async def finish(self, ctx: Context, *, winner: str):
        cg = current_gambit()
        if not cg:
            await response_message(ctx, f'Gambit not started, please use `,gamb start`')
            return
        win = crew_lookup(winner, self)
        if win.name == cg.team1:
            loser = cg.team2
            winning_bets = cg.bets_1
            losing_bets = cg.bets_2
            winner = 1

        elif win.name == cg.team2:
            loser = cg.team1
            winning_bets = cg.bets_2
            losing_bets = cg.bets_1
            winner = 2
        else:
            await response_message(ctx, f'{win.name} is not in the current gambit between {cg.team1} and {cg.team2}.')
            return
        msg = await ctx.send(f'Are you sure you want to end the gambit as {win.name} beat {loser}?')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return

        await ctx.send('This might take awhile, so please do not repeat the command.')
        if winning_bets == 0:
            ratio = 0
        else:
            ratio = losing_bets / winning_bets
        gambit_id = archive_gambit(win.name, loser, winning_bets, losing_bets)
        top_win, top_loss = (0, None), (0, None)
        for member_id, amount, cr in all_bets():
            member = self.bot.get_user(member_id)
            if not member:
                continue
            try:
                if cr == win.name:
                    final = amount + math.ceil(amount * ratio)
                    if final == 0:
                        # Reset win
                        final = 220
                    total = refund_member_gcoins(member, final)
                    if final > top_win[0]:
                        top_win = [final, str(member)]

                    await member.send(f'You won {final} G-Coins on your bet of {amount} on {cr} over {loser}! '
                                      f'Congrats you now have {total} G-Coins!')
                else:
                    total = member_gcoins(member)
                    final = -amount

                    if final > top_loss[0]:
                        top_loss = [final, str(member)]
                    await member.send(f'You lost {amount} G-Coins on your bet on {cr} over {win.name}.')
                    if total > 0:
                        await member.send(f'You now have {total} coins remaining.')
                    else:
                        await member.send('You are all out of G-Coins, but worry not! If you place a 0 G-Coin bet'
                                          ' when you are bankrupt, if you win, you get 220 G-Coins!')
            except discord.errors.Forbidden:
                await ctx.send(f'{str(member)} is not accepting dms.')
            archive_bet(member, final, gambit_id)
        cancel_gambit()
        await ctx.send(f'Gambit concluded! {win.name} beat {loser}, {winning_bets} G-Coins were placed on {win.name} '
                       f'and {losing_bets} G-Coins were placed on {loser}.')

        update_gambit_sheet()
        await update_finished_gambit(cg, winner, self, top_win, top_loss)

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN])
    async def update(self, ctx):
        cg = current_gambit()
        if cg:
            await update_gambit_message(cg, self)

        update_gambit_sheet()

    @commands.command(**help_doc['bet'])
    @gambit_channel
    async def bet(self, ctx: Context, *, everything: str):
        cg = current_gambit()
        split = everything.split()
        current = member_gcoins(ctx.author)
        if split[0] == 'all':
            amount = current
            team = ' '.join(split[1:])
        elif split[-1] == 'all':
            team = ' '.join(split[:-1])
            amount = current
        elif split[0].isdigit():
            team = ' '.join(split[1:])
            amount = int(split[0])
        elif split[-1].isdigit():
            team = ' '.join(split[:-1])
            amount = int(split[-1])
        else:
            await response_message(ctx, f'{everything} needs to start or end with a bet amount.')
            return

        if not cg:
            await ctx.send('No gambit is currently running, please wait for one to start before betting.')
            return
        if cg.locked:
            await ctx.send(f'The gambit between {cg.team1} and {cg.team2} is locked as the battle has already started.'
                           f'\nUse `,odds` to see the current odds.')
            return
        if not is_gambiter(ctx.author):
            if not await join_gambit(ctx.author, self):
                await ctx.send(f'{str(ctx.author)} isn\'t a gambiter and didn\'t join. (check your dms and try again)')
                return
        cr = crew_lookup(team, self)
        validate_bet(ctx.author, cr, amount, self)
        if await confirm_bet(ctx, cr, amount, self):
            await ctx.message.delete()

            await update_gambit_message(current_gambit(), self)

    @commands.command(**help_doc['odds'])
    @gambit_channel
    async def odds(self, ctx: Context):
        cg = current_gambit()
        if not cg:
            await ctx.send('No gambit is currently running, please wait for one to start before betting.')
            return
        await ctx.send(f'If you win a bet on {cg.team1} you will get {cg.odds_1} extra G-Coins.'
                       f'\nIf you win bet on {cg.team2} you will get {cg.odds_2} extra G-Coins.')

    ''' ***********************************STAFF COMMANDS ************************************************'''

    @commands.group(name='staff', brief='Commands for staff', invoke_without_command=True)
    async def staff(self, ctx):
        await self.help(ctx, 'staff')

    @commands.command(**help_doc['setslots'])
    @role_call(STAFF_LIST)
    @main_only
    async def setslots(self, ctx, num: int, *, name: str = None):
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
        new = cur_slot_set(actual_crew, num)
        await ctx.send(f'Set {actual_crew.name} slots to {new}.')

    @commands.command(**help_doc['cooldown'], hidden=True)
    @role_call(STAFF_LIST)
    async def cooldown(self, ctx):
        users_and_times = sorted(cooldown_current(), key=lambda x: x[1])
        out = []
        for user_id, tdelta in users_and_times:
            user = self.cache.scs.get_member(user_id)
            if tdelta.days > 0:
                out.append(f'{str(user)} is past 24 hours for some reason.')
            else:
                out.append(f'{str(user)} was flaired {strfdelta(tdelta, "{hours} hours and {minutes} minutes ago")}')
        await send_long(ctx, '\n'.join(out), '\n')

    @commands.command(**help_doc['non_crew'], hidden=True)
    @main_only
    @role_call(STAFF_LIST)
    async def non_crew(self, ctx):
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

    @commands.command(**help_doc['overflow'], hidden=True)
    @role_call([ADMIN, MINION])
    async def overflow(self, ctx: Context):
        first, second = await overflow_anomalies(self)
        out = ['These members have the role, but are not in an overflow crew.']
        for member in first:
            out.append(f'> {member}')
        out.append('These members are flaired in the overflow server, but have no role here')
        for member in second:
            out.append(f'> {member}')
        out_str = '\n'.join(out)
        embed = discord.Embed(description=out_str, title="Overflow Anomalies")
        await send_long_embed(ctx, embed)

    @commands.command(**help_doc['flairing_off'], hidden=True)
    @role_call(STAFF_LIST)
    async def flairing_off(self, ctx: Context):
        self.cache.flairing_allowed = False
        await ctx.send('Flairing has been disabled for the time being.')

    @commands.command(**help_doc['flairing_on'], hidden=True)
    @role_call(STAFF_LIST)
    async def flairing_on(self, ctx: Context):
        self.cache.flairing_allowed = True
        await ctx.send('Flairing has been re-enabled.')

    @commands.command(**help_doc['disable'])
    @role_call(STAFF_LIST)
    async def disable(self, ctx: Context, channel: discord.TextChannel):
        if channel.id in disabled_channels():
            msg = await ctx.send(f'{channel.name} is already disabled, re-enable?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
            remove_disabled_channel(channel.id)
            await ctx.send(f'{channel.name} undisabled.')
        else:
            msg = await ctx.send(f'Really disable the bot in {channel.name}?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
            add_disabled_channel(channel.id)
            await ctx.send(f'JettBot disabled in {channel.name}.')

    @commands.command(**help_doc['deactivate'])
    @role_call(STAFF_LIST)
    async def deactivate(self, ctx: Context, command: str):
        command_name = closest_command(command, self)
        db_command = command_lookup(command_name)
        if db_command[1]:
            msg = await ctx.send(f'`{command_name}` is already deactivated, re-activate?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
            set_command_activation(command_name, False)
            await ctx.send(f'{command_name} reactivated.')
        else:
            msg = await ctx.send(f'really deactivate `{command_name}`?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
            set_command_activation(command_name, True)
            await ctx.send(f'`{command_name}` deactivated.')

    @commands.command(**help_doc['usage'])
    @role_call([DOCS, MINION, ADMIN, CERTIFIED])
    async def usage(self, ctx: Context):
        pages = menus.MenuPages(source=Paged(command_leaderboard(), title='Command usage counts'),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['pending'], hidden=True)
    @role_call(STAFF_LIST)
    async def pending(self, ctx: Context):
        await ctx.send('Printing all current battles.')
        for key, battle in self.battle_map.items():
            if battle:
                chan = discord.utils.get(ctx.guild.channels, id=channel_id_from_key(key))
                await ctx.send(chan.mention)
                await send_sheet(ctx, battle)

    @commands.command(**help_doc['po'], hidden=True)
    @main_only
    async def po(self, ctx: Context):
        await ctx.send(embed=playoff_summary(self))

    @commands.command(**help_doc['register'])
    @main_only
    @role_call(STAFF_LIST)
    @flairing_required
    async def register(self, ctx: Context, members: Greedy[discord.Member], new_crew: str = None):

        await self.cache.update(self)
        success = []
        fail_not_overflow = []
        fail_on_crew = []
        flairing_crew = crew_lookup(new_crew, self)
        for member in members:
            try:
                user_crew = crew(member, self)
            except ValueError:
                user_crew = None

            if user_crew:
                await response_message(ctx, f'{member.display_name} '
                                            f'must be unflaired for their current crew before they can be flaired. ')
                fail_on_crew.append(member)
                continue
            overflow_mem = discord.utils.get(self.cache.overflow_server.members, id=member.id)
            if flairing_crew.overflow and not overflow_mem:
                await response_message(ctx,
                                       f'{member.mention} is not in the overflow server and '
                                       f'{flairing_crew.name} is an overflow crew. https://discord.gg/ARqkTYg')
                fail_not_overflow.append(member)
                continue
            of_before, of_after = None, None
            if flairing_crew.overflow:
                of_user = self.cache.overflow_server.get_member(member.id)
                of_before = set(of_user.roles)
            before = set(member.roles)
            try:
                await flair(member, flairing_crew, self, True, True)
                record_flair(member, flairing_crew)
            except ValueError as ve:
                await response_message(ctx, str(ve))
                return

            after = set(ctx.guild.get_member(member.id).roles)
            if flairing_crew.overflow:
                overflow_server = discord.utils.get(self.bot.guilds, name=OVERFLOW_SERVER)
                of_after = set(overflow_server.get_member(member.id).roles)
            await self.cache.channels.flair_log.send(
                embed=role_change(before, after, ctx.author, member, of_before, of_after))
            success.append(member)
        desc = ['Successful flairs']
        for s in success:
            desc.append(f'{s.display_name}: {s.mention}')
        if fail_not_overflow or fail_on_crew:
            desc.append('Unsuccessful flairs')
            if fail_not_overflow:
                desc.append('Not in overflow:')
                for s in fail_not_overflow:
                    desc.append(f'{s.display_name}: {s.mention}')
            if fail_on_crew:
                desc.append('Already on a crew, needs to unflair')
                for s in fail_on_crew:
                    desc.append(f'{s.display_name}: {s.mention}')
        _, total = slots(flairing_crew)
        if total == 0:
            calced = calc_reg_slots(len(members))
            total_slot_set(flairing_crew, calced)
            desc.append(f'Initiated with {calced} slots.')

        embed = discord.Embed(title=f'Crew Reg for {flairing_crew.name}', description='\n'.join(desc),
                              color=flairing_crew.color)
        await send_long_embed(ctx, embed)
        await send_long_embed(self.cache.channels.flair_log, embed)

    @commands.command(**help_doc['freeze'])
    @role_call(STAFF_LIST)
    async def freeze(self, ctx: Context, *, everything: str):
        split = everything.split()
        try:
            parseTime(split[-1])
            length = split[-1]
            cr = ''.join(split[:-1])
        except ValueError:
            length = ''
            cr = ''.join(split)

        actual = crew_lookup(cr, self)
        if actual.freeze:
            if not length:
                msg = await ctx.send(f'{actual.name} is already frozen till {actual.freeze}, really unfreeze them?')
                if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                    await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                    return
                freeze_crew(actual, None)
                await ctx.send(f'{actual.name} unfrozen.')
            else:
                finish = parseTime(length)
                msg = await ctx.send(f'{actual.name} is already frozen till {actual.freeze}'
                                     f' do you want to change their end date to {finish}?')
                if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                    await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                    return
                freeze_crew(actual, finish)
                await ctx.send(f'{actual.name} frozen till {finish}.')
        else:
            if length:
                finish = parseTime(length)
                msg = await ctx.send(f'Do you want to freeze {actual.name} till {finish}?')
                if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                    await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                    return
                freeze_crew(actual, finish)
                await ctx.send(f'{actual.name} frozen till {finish}.')
            else:
                msg = await ctx.send(f'Do you want to freeze {actual.name} indefinitely?')
                if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                    await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                    return
                freeze_crew(actual, datetime(2069, 4, 20))
                await ctx.send(f'{actual.name} frozen indefinitely.')

    @commands.command(**help_doc['disband'], hidden=True)
    @role_call(STAFF_LIST)
    async def disband(self, ctx, *, name: str = None):
        if name:
            dis_crew = crew_lookup(name, self)
        else:
            await ctx.send('You must send in a crew name.')
            return

        members = crew_members(dis_crew, self)
        desc = [f'({len(members)}):', '\n'.join([str(mem) for mem in members])]
        out = discord.Embed(title=f'{dis_crew.name} these players will have all crew roles stripped.',
                            description='\n'.join(desc), color=dis_crew.color)

        await send_long_embed(ctx, out)
        message = f'{ctx.author.mention}: You are attempting to disband {dis_crew.name}, all {len(members)} members' \
                  f' will have their crew roles stripped, are you sure?'
        msg = await ctx.send(message)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return

        desc = [f'({len(members)}):', '\n'.join([str(mem) for mem in members])]
        out = discord.Embed(title=f'{dis_crew.name} is disbanding, here is their players:',
                            description='\n'.join(desc), color=dis_crew.color)

        await send_long_embed(self.cache.channels.doc_keeper, out)
        if dis_crew.overflow:
            cr_role = discord.utils.get(self.cache.overflow_server.roles, name=dis_crew.name)
        else:
            cr_role = discord.utils.get(self.cache.scs.roles, name=dis_crew.name)
        for member in members:

            if dis_crew.overflow:
                if check_roles(member, [self.cache.roles.overflow.name]):
                    user = discord.utils.get(self.cache.overflow_server.members, id=member.id)
                    await member.remove_roles(self.cache.roles.overflow,
                                              reason=f'Unflaired in disband by {ctx.author.name}')
                    if not user:
                        continue
                    await member.edit(nick=nick_without_prefix(member.display_name))
                    await user.remove_roles(cr_role, reason=f'Unflaired by {ctx.author.name}')
            else:
                await member.remove_roles(cr_role)
            await member.remove_roles(self.cache.roles.advisor, self.cache.roles.leader,
                                      reason=f'Unflaired in disband by {ctx.author.name}')

        await cr_role.delete(reason=f'disbanded by {ctx.author.name}')
        response_embed = discord.Embed(title=f'{dis_crew.name} has been disbanded',
                                       description='\n'.join(
                                           [f'{mem.mention}, {mem.id}, {str(mem)}' for mem in members]),
                                       color=dis_crew.color)
        await send_long_embed(ctx, response_embed)
        await send_long_embed(self.cache.channels.flair_log, response_embed)

    @commands.command(**help_doc['tomain'], hidden=True)
    @role_call(STAFF_LIST)
    async def tomain(self, ctx, *, name: str = None):
        if name:
            dis_crew = crew_lookup(name, self)
        else:
            await ctx.send('You must send in a crew name.')
            return
        if not dis_crew.overflow:
            await ctx.send('You can only move overflow crews like this')
            return

        members = crew_members(dis_crew, self)
        message = f'{ctx.author.mention}: You are attempting to move {dis_crew.name} to main, ' \
                  f'this crew has {len(members)} members.' \
                  f' The overflow crew will be deleted, are you sure?'
        msg = await ctx.send(message)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
        desc = [f'({len(members)}):', '\n'.join([str(mem) for mem in members])]
        out = discord.Embed(title=f'{dis_crew.name} this crew is moving to main.',
                            description='\n'.join(desc), color=dis_crew.color)

        await send_long_embed(ctx, out)

        desc = [f'({len(members)}):', '\n'.join([str(mem) for mem in members])]
        out = discord.Embed(title=f'{dis_crew.name} is moving to main, here is their players:',
                            description='\n'.join(desc), color=dis_crew.color)

        output = split_embed(out, 2000)
        for put in output:
            await self.cache.channels.doc_keeper.send(embed=put)

        of_role = discord.utils.get(self.cache.overflow_server.roles, name=dis_crew.name)
        new_role = await self.cache.scs.create_role(
            hoist=True, name=dis_crew.name, color=of_role.color,
            permissions=discord.Permissions(permissions=37080640)
        )
        for member in members:
            if check_roles(member, [self.cache.roles.overflow.name]):
                user = discord.utils.get(self.cache.overflow_server.members, id=member.id)
                await member.remove_roles(self.cache.roles.overflow,
                                          reason=f'Moved to main by {ctx.author.name}')
                if not user:
                    continue
                await member.edit(nick=nick_without_prefix(member.display_name))
                await user.remove_roles(of_role, reason=f'Unflaired by {ctx.author.name}')
                await member.add_roles(new_role)
        update_crew_tomain(dis_crew, new_role.id)
        await self.cache.update(self)
        await of_role.delete()
        response_embed = discord.Embed(title=f'{dis_crew.name} has been moved to the main server.',
                                       description='\n'.join([f'{mem.display_name} |{mem.mention}' for mem in members]),
                                       color=dis_crew.color)
        await ctx.send(f'{ctx.author.mention} don\'t forget to move the crew role in the list!')
        await send_long_embed(ctx, response_embed)

    @commands.command(**help_doc['recache'], hidden=True)
    @role_call(STAFF_LIST)
    async def recache(self, ctx: Context):
        await cache_process(self)
        self.auto_cache.cancel()
        self.auto_cache.restart()
        await ctx.send('The cache has been reset, everything should be updated now.')

    @commands.command(**help_doc['retag'], hidden=True)
    @role_call(STAFF_LIST)
    async def retag(self, ctx, *, name: str = None):
        if name:
            dis_crew = crew_lookup(name, self)
        else:
            await ctx.send('You must send in a crew name.')
            return
        if not dis_crew.overflow:
            await ctx.send('You can only retag overflow crews like this')
            return
        members = crew_members(dis_crew, self)
        preview = []
        for member in members:
            before = member.nick if member.nick else member.name
            member_nick = nick_without_prefix(member.nick) if member.nick else nick_without_prefix(member.name)
            after = f'{dis_crew.abbr} | {member_nick}'
            preview.append(f'{before} -> {after}')
        desc = [f'({len(members)}):', '\n'.join(preview)]
        out = discord.Embed(title=f'{dis_crew.name} these player\'s will have their names updated.',
                            description='\n'.join(desc), color=dis_crew.color)
        await send_long_embed(ctx, out)
        message = f'{ctx.author.mention}: Really retag all {len(members)} members of {dis_crew.name}?'

        msg = await ctx.send(message)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
        name_change = []
        for member in members:
            before = member.nick if member.nick else member.name
            member_nick = nick_without_prefix(member.nick) if member.nick else nick_without_prefix(member.name)
            await member.edit(nick=f'{dis_crew.abbr} | {member_nick}')
            after = member.nick
            name_change.append(f'{before} -> {after}')

        desc = [f'({len(members)}):', '\n'.join(name_change)]
        out = discord.Embed(title=f'{dis_crew.name} these player\'s nicknames have been updated.',
                            description='\n'.join(desc), color=dis_crew.color)
        await send_long_embed(ctx, out)

    ''' ******************************* HELP AND MISC COMMANDS ******************************************'''

    @commands.group(name='misc', brief='Miscellaneous commands', invoke_without_command=True)
    async def misc(self, ctx):
        await self.help(ctx, 'misc')

    @commands.command(**help_doc['thank'])
    @banned_channels(['crew_flairing', 'scs_docs_updates'])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def thank(self, ctx: Context):

        await ctx.send(f'Thanks for all the hard work you do on the bot alexjett!\n'
                       f'{add_thanks(ctx.author)}')

    @commands.command(**help_doc['thankboard'])
    @banned_channels(['crew_flairing', 'scs_docs_updates'])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def thankboard(self, ctx: Context):

        await ctx.send(embed=thank_board(ctx.author))

    @commands.command(**help_doc['disablelist'])
    async def disablelist(self, ctx: Context):
        ids = disabled_channels()
        out = [f'<#{id_num}>' for id_num in ids]
        out.insert(0, 'List of channels the bot is disabled in:')
        await ctx.send('\n'.join(out))

    @commands.command(**help_doc['guide'])
    async def guide(self, ctx):
        await ctx.send('https://docs.google.com/document/d/1ICpPcH3etnkcZk8Zc9wn2Aqz1yeAIH_cAWPPUUVgl9I/edit')

    @commands.command(**help_doc['listroles'])
    async def listroles(self, ctx, *, role: str):
        actual, mems = members_with_str_role(role, self)
        mems.sort(key=lambda x: str(x))
        if 'everyone' in actual:
            await ctx.send('I will literally ban you if you try this again.')
            return
        if len(mems) > 150:
            await ctx.send(f'{actual} is too large of a role, use `.listroles`.')
            return
        desc = ['\n'.join([f'{str(member)} {member.mention}' for member in mems])]
        if actual in self.cache.crews_by_name:
            cr = crew_lookup(actual, self)
            title = f'All {len(mems)} members on crew {actual}'
            color = cr.color
        else:
            title = f'All {len(mems)} members with {actual} role'
            color = discord.Color.dark_gold()

        out = discord.Embed(title=title,
                            description='\n'.join(desc), color=color)
        await send_long_embed(ctx, out)

    @commands.command(**help_doc['pingrole'])
    @role_call(STAFF_LIST)
    async def pingrole(self, ctx, *, role: str):
        actual, mems = members_with_str_role(role, self)
        out = [f'Pinging all members of role {actual}: ']
        for mem in mems:
            out.append(mem.mention)
        await ctx.send(''.join(out))

    @commands.command(**help_doc['overlap'])
    async def overlap(self, ctx, *, two_roles: str = None):
        if 'everyone' in two_roles:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        best = best_of_possibilities(two_roles, self)
        mems = overlap_members(best[0], best[1], self)
        if 'everyone' in best[0] or 'everyone' in best[1]:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        out = f'Overlap between {best[0]} and {best[1]}:\n' + ', '.join([escape(str(mem)) for mem in mems])

        await send_long(ctx, out, ',')

    @commands.command(hidden=True, **help_doc['pingoverlap'])
    @role_call(STAFF_LIST)
    async def pingoverlap(self, ctx, *, two_roles: str = None):
        if 'everyone' in two_roles:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        best = best_of_possibilities(two_roles, self)
        mems = overlap_members(best[0], best[1], self)

        if 'everyone' in best[0] or 'everyone' in best[1]:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        if len(mems) > 10:
            resp = f'You are attempting to ping the overlap between {best[0]} and {best[1]} this ' \
                   f'is {len(mems)} members, are you sure?'
            msg = await ctx.send(resp)
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return

        out = f'Overlap between {best[0]} and {best[1]}:\n' + ', '.join([mem.mention for mem in mems])

        await send_long(ctx, out, ',')

    @commands.command(hidden=True, **help_doc['bigcrew'])
    @role_call(STAFF_LIST)
    async def bigcrew(self, ctx, over: Optional[int] = 40):
        big = []
        for cr in self.cache.crews_by_name.values():
            if cr.member_count >= over:
                big.append(cr)
        desc = []
        for cr in big:
            desc.append(f'{cr.name}: {cr.member_count}')

        embed = discord.Embed(title=f'These Crews have {over} members or more', description='\n'.join(desc))
        await send_long_embed(ctx, embed)

    @commands.command(hidden=True, **help_doc['softlock'])
    @role_call(STAFF_LIST)
    async def softlock(self, ctx, cr: Optional[str] = ''):
        if cr:
            actual = crew_lookup(cr, self)
            usage = crew_usage(actual)
            desc = []
            for mem_id, links in usage.items():
                link_str = ''
                for link in links:
                    link_str += f'[link]({link}) '
                member = self.bot.get_user(mem_id)
                if not member:
                    desc.append(f'{mem_id}: {link_str} (name not found for some reason)')
                    continue
                desc.append(f'{member.display_name}: {link_str}')
            desc.sort()
            embed = discord.Embed(title=f'Usage of each member of {actual.name} from last month ({len(usage)} total)',
                                  description='\n'.join(desc), color=discord.Color.random())
            await send_long_embed(ctx, embed)
        else:
            pass
            #TODO Fix this
            # usage = all_crew_usage()
            # desc = []
            # for number, name, _ in usage:
            #     desc.append(f'{name}: {number}')
            # embed = discord.Embed(title='Number of unique players in cbs last month by each crew',
            #                       description='\n'.join(desc), color=discord.Color.random())
            # await send_long_embed(ctx, embed)

    @commands.command(hidden=True, **help_doc['crnumbers'])
    @role_call(STAFF_LIST)
    async def crnumbers(self, ctx):
        crews = list(self.cache.crews_by_name.values())

        embed = discord.Embed(title=f'Crew numbers for analysis')
        embed.add_field(name='number', value=str(len(crews)))
        embed.add_field(name='average size', value='{:.2f}'.format(crew_avg(crews)))
        embed.add_field(name='stdev of size', value='{:.2f}'.format(crew_stdev(crews)))
        crew_bar_chart(crews)
        await ctx.send(embed=embed, file=discord.File('cr.png'))

    @commands.command(**help_doc['slots'])
    @main_only
    async def slots(self, ctx, *, name: str = None):
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
        left, total, unflairs = extra_slots(actual_crew)
        await ctx.send(f'{actual_crew.name} has ({left}/{total} slots) and {unflairs}/3 unflairs till a new slot.')

    @commands.command(hidden=True, **help_doc['slottotals'])
    @role_call(STAFF_LIST)
    async def slottotals(self, ctx):
        crews = list(self.cache.crews_by_name.values())
        desc = []
        crew_msg = {}
        for cr in crews:
            if cr.member_count == 0:
                continue
            total, base, modifer, rollover = calc_total_slots(cr)
            desc.append(f'{cr.name}: {total} slots: {base} base + {modifer} size mod + {rollover} rollover.')
            total_slot_set(cr, total)
            message = f'{cr.name} has {total} flairing slots this month:\n' \
                      f'{base} base slots\n' \
                      f'{modifer} from size modifier\n' \
                      f'{rollover} rollover slots\n' \
                      f'with an overall minimum of 5 slots\n' \
                      'For more information, refer to message link in #lead_announcements. ' \
                      'This bot will not be able to respond to any questions you have, so use #questions_feedback'
            crew_msg[cr.name] = message

        # for member in self.cache.scs.members:
        #     if self.cache.roles.leader in member.roles:
        #         msg = ''
        #         try:
        #             cr = crew(member, self)
        #             msg = crew_msg[cr]
        #         except ValueError:
        #             await ctx.send(f'{str(member)} is a leader with no crew.')
        #         if msg:
        #             try:
        #                 await member.send(msg)
        #             except discord.errors.Forbidden:
        #                 await ctx.send(f'{str(member)} is not accepting dms.')

        embed = discord.Embed(title=f'Crew total slots.', description='\n'.join(desc))
        await send_long_embed(ctx, embed)

    @commands.command(hidden=True, **help_doc['flaircounts'])
    @role_call(STAFF_LIST)
    async def flaircounts(self, ctx, long: Optional[str]):
        crews = list(self.cache.crews_by_name.values())
        flairs = crew_flairs()
        flair_list = []
        for cr in crews:
            if cr.name in flairs:
                flair_list.append((cr.name, flairs[cr.name]))
            else:
                flair_list.append((cr.name, 0))
        flair_list.sort(key=lambda x: x[1])
        embed = discord.Embed(title=f'Crew flair numbers for analysis')
        embed.add_field(name='number of crews', value=str(len(crews)))
        embed.add_field(name='average flairs', value='{:.2f}'.format(avg_flairs(flair_list)))
        embed.add_field(name='stdev of flairs', value='{:.2f}'.format(flair_stdev(flair_list)))
        flair_bar_chart(flair_list)
        await ctx.send(embed=embed, file=discord.File('fl.png'))
        if long:
            await send_long(ctx, '\n'.join([f'{fl[0]}: {fl[1]}' for fl in flair_list]), '\n')

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
            logfilename = 'logs.log'
            if os.path.exists(logfilename):
                append_write = 'a'  # append if already exists
            else:
                append_write = 'w'  # make a new file if not
            lf = open(logfilename, append_write)
            traceback.print_exception(type(error), error, error.__traceback__, file=lf)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
            lf.close()

    ###########################################################################################
    # Start test commands
    # Test commands should be limited to dev only.
    # No mutation should occur, and they are meant to test discord.py APIs.
    ###########################################################################################

    @commands.group(name='test')
    @role_call(STAFF_LIST)
    async def test_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send('Invalid test sub command')

    @test_group.command(name='confirm')
    @role_call(STAFF_LIST)
    async def test_confirm(self, ctx):
        msg = await ctx.send(datetime.today().strftime("%Y/%m/%d %H:%M:%S"))
        result = await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot)
        await ctx.send(f'{msg.content}: {result}')


def main():
    load_dotenv()
    token = os.getenv('DISCORD_TOKEN')
    bot = commands.Bot(command_prefix=os.getenv('PREFIX'), intents=discord.Intents.all(), case_insensitive=True,
                       allowed_mentions=discord.AllowedMentions(everyone=False))
    bot.remove_command('help')
    cache = Cache()
    bot.add_cog(ScoreSheetBot(bot, cache))
    bot.run(token)

if __name__ == '__main__':
    main()
