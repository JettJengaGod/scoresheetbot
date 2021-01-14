import os
import sys
import traceback
import time
import discord
import functools
from datetime import date
from discord.ext import commands, tasks, menus
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

Context = discord.ext.commands.Context

class ScoreSheetBot(commands.Cog):
    def __init__(self, bot: commands.bot, cache: Cache):
        self.bot = bot
        self.battle_map: Dict[str, Battle] = {}
        self.cache = cache
        self.auto_cache.start()

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

    async def _set_current(self, ctx: Context, battle: Battle):
        self.battle_map[key_string(ctx)] = battle

    async def _clear_current(self, ctx):
        self.battle_map.pop(key_string(ctx), None)
        await update_channel_open('', ctx.channel)

    def cog_unload(self):
        self.auto_cache.cancel()

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
                    update_member_crew(after_crew, self)
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
                            if isinstance(cmd, discord.ext.commands.Group):
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
            await self._set_current(ctx, Battle(user_crew, opp_crew, size))
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

        if self._current(ctx).battle_over():
            if self._current(ctx).mock:
                await self._clear_current(ctx)
                await ctx.send(f'This battle was confirmed by {ctx.author.mention}.')
            else:
                self._current(ctx).confirm(await self._battle_crew(ctx, ctx.author))
                await send_sheet(ctx, battle=self._current(ctx))
                if self._current(ctx).confirmed():
                    today = date.today()

                    output_channels = [discord.utils.get(ctx.guild.channels, name=DOCS_UPDATES),
                                       discord.utils.get(ctx.guild.channels, name=OUTPUT)]
                    winner = self._current(ctx).winner().name
                    loser = self._current(ctx).loser().name
                    for output_channel in output_channels:
                        await output_channel.send(
                            f'**{today.strftime("%B %d, %Y")}- {winner} vs. {loser} **\n'
                            f'{self.cache.crews_by_name[winner].rank} crew defeats'
                            f' {self.cache.crews_by_name[loser].rank} crew in a '
                            f'{self._current(ctx).team1.num_players}v{self._current(ctx).team2.num_players} battle!\n'
                            f'from  {ctx.channel.mention}.')
                        link = await send_sheet(output_channel, self._current(ctx))
                    add_finished_battle(self._current(ctx), link.jump_url, 1)
                    await ctx.send(
                        f'The battle between {self._current(ctx).team1.name} and {self._current(ctx).team2.name} '
                        f'has been confirmed by both sides and posted in {output_channels[0].mention}.')
                    await self._clear_current(ctx)
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

    @commands.command(**help_doc['guide'])
    async def rankings(self, ctx):

        crews_sorted_by_ranking = sorted([cr for cr in self.cache.crews_by_name.values() if cr.ladder],
                                         key=lambda x: int(x.ladder[1:x.ladder.index('/')]))
        crew_ranking_str = [f'{cr.name} {cr.rank}' for cr in crews_sorted_by_ranking]

        pages = menus.MenuPages(source=Paged(crew_ranking_str, title='Legacy Crews Rankings'),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['battles'])
    async def battles(self, ctx):

        pages = menus.MenuPages(source=Paged(all_battles(), title='Battles'), clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['playerstats'])
    @main_only
    async def playerstats(self, ctx, *, name: str = None):
        if name:
            member = member_lookup(name, self)

        else:
            member = ctx.author
        taken, lost = player_stocks(member)
        title = f'Stats for {str(member)}'
        embed = discord.Embed(title=title, color=member.color)
        embed.add_field(name='Stocks Taken/Lost', value=f'{taken}/{lost}', inline=False)
        pc = player_chars(member)
        embed.add_field(name='Characters played', value='how many battles played in ', inline=False)
        for char in pc:
            emoji = string_to_emote(char[1], self.bot)
            embed.add_field(name=emoji, value=f'{char[0]}', inline=True)
        await ctx.send(embed=embed)

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
        if not record[0] or not record[1]:
            await ctx.send(f'{actual_crew.name} does not have any recorded crew battles with the bot.')
            return
        title = f'{actual_crew.name}: {record[0]}-{int(record[1]) - int(record[0])}'
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
        try:
            await flair(member, flairing_crew, self, check_roles(ctx.author, STAFF_LIST))
        except ValueError as ve:
            await response_message(ctx, str(ve))
            return
        await response_message(ctx, f'Successfully flaired {member.mention} for {flairing_crew.name}.')

        after = set(ctx.guild.get_member(member.id).roles)
        if flairing_crew.overflow:
            overflow_server = discord.utils.get(self.bot.guilds, name=OVERFLOW_SERVER)
            of_after = set(overflow_server.get_member(member.id).roles)
        await self.cache.channels.flair_log.send(
            embed=role_change(before, after, ctx.author, member, of_before, of_after))

    ''' ***********************************STAFF COMMANDS ************************************************'''

    @commands.group(name='staff', brief='Commands for staff', invoke_without_command=True)
    async def staff(self, ctx):
        await self.help(ctx, 'staff')

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
        overflow_role = set()
        for member in self.cache.scs.members:
            if check_roles(member, OVERFLOW_ROLE):
                overflow_role.add(f'{str(member)} | {member.id}')
        other_set = set()
        other_members = self.cache.overflow_server.members
        for member in other_members:
            if any((role.name in self.cache.crews for role in member.roles)):
                other_set.add(f'{str(member)} | {member.id}')
                continue
        first = overflow_role - other_set
        second = other_set - overflow_role
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

    @commands.command(**help_doc['pending'], hidden=True)
    @role_call(STAFF_LIST)
    async def pending(self, ctx: Context):
        await ctx.send('Printing all current battles.')
        for key, battle in self.battle_map.items():
            if battle:
                chan = discord.utils.get(ctx.guild.channels, id=channel_id_from_key(key))
                await ctx.send(chan.mention)
                await send_sheet(ctx, battle)

    @commands.command(**help_doc['disband'], hidden=True)
    @role_call(STAFF_LIST)
    async def disband(self, ctx, *, name: str = None):
        if name:
            dis_crew = crew_lookup(name, self)
        else:
            await ctx.send('You must send in a crew name.')
            return
        if not dis_crew.overflow:
            await ctx.send('You can only disband overflow crews like this')
            return

        members = crew_members(dis_crew, self)
        message = f'{ctx.author.mention}: You are attempting to disband {dis_crew.name}, all {len(members)} members' \
                  f' will have their crew roles stripped, are you sure?'
        msg = await ctx.send(message)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
        desc = [f'({len(members)}):', '\n'.join([str(mem) for mem in members])]
        out = discord.Embed(title=f'{dis_crew.name} these players will have all crew roles stripped.',
                            description='\n'.join(desc), color=dis_crew.color)

        await send_long_embed(ctx, out)

        desc = [f'({len(members)}):', '\n'.join([str(mem) for mem in members])]
        out = discord.Embed(title=f'{dis_crew.name} is disbanding, here is their players:',
                            description='\n'.join(desc), color=dis_crew.color)

        output = split_embed(out, 2000)
        for put in output:
            await self.cache.channels.doc_keeper.send(embed=put)
        for member in members:
            if check_roles(member, [self.cache.roles.overflow.name]):
                user = discord.utils.get(self.cache.overflow_server.members, id=member.id)
                await member.remove_roles(self.cache.roles.overflow,
                                          reason=f'Unflaired in disband by {ctx.author.name}')
                if not user:
                    continue
                await member.edit(nick=nick_without_prefix(member.display_name))
                role = discord.utils.get(self.cache.overflow_server.roles, name=dis_crew.name)
                overflow_adv = discord.utils.get(self.cache.overflow_server.roles, name=ADVISOR)
                overflow_leader = discord.utils.get(self.cache.overflow_server.roles, name=LEADER)
                await user.remove_roles(role, overflow_adv, overflow_leader, reason=f'Unflaired by {ctx.author.name}')

            await member.remove_roles(self.cache.roles.advisor, self.cache.roles.leader,
                                      reason=f'Unflaired in disband by {ctx.author.name}')
        response_embed = discord.Embed(title=f'{dis_crew.name} has been disbanded',
                                       description='\n'.join([mem.mention for mem in members]),
                                       color=dis_crew.color)
        await send_long_embed(ctx, response_embed)

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
                overflow_adv = discord.utils.get(self.cache.overflow_server.roles, name=ADVISOR)
                overflow_leader = discord.utils.get(self.cache.overflow_server.roles, name=LEADER)
                await user.remove_roles(of_role, overflow_adv, overflow_leader,
                                        reason=f'Unflaired by {ctx.author.name}')
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

    @commands.command(**help_doc['guide'])
    async def guide(self, ctx):
        await ctx.send('https://docs.google.com/document/d/1ICpPcH3etnkcZk8Zc9wn2Aqz1yeAIH_cAWPPUUVgl9I/edit')

    @commands.command(**help_doc['overlap'])
    async def overlap(self, ctx, *, two_roles: str = None):
        if 'everyone' in two_roles:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `.list_roles`.')
        best = best_of_possibilities(two_roles, self)
        mems = overlap_members(best[0], best[1], self)
        out = f'Overlap between {best[0]} and {best[1]}:\n' + ', '.join([escape(str(mem)) for mem in mems])

        await send_long(ctx, out, ',')

    @commands.command(hidden=True, **help_doc['pingoverlap'])
    @role_call(STAFF_LIST)
    async def pingoverlap(self, ctx, *, two_roles: str = None):
        if 'everyone' in two_roles:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `.list_roles`.')
        best = best_of_possibilities(two_roles, self)
        mems = overlap_members(best[0], best[1], self)
        if len(mems) > 10:
            resp = f'You are attempting to ping the overlap between {best[0]} and {best[1]} this ' \
                   f'is {len(mems)} members, are you sure?'
            msg = await ctx.send(resp)
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
        out = f'Overlap between {best[0]} and {best[1]}:\n' + ', '.join([mem.mention for mem in mems])
        await send_long(ctx, out, ',')

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


def main():
    load_dotenv()
    token = os.getenv('DISCORD_TOKEN')
    bot = commands.Bot(command_prefix=os.getenv('PREFIX'), intents=discord.Intents.all(), case_insensitive=True)
    bot.remove_command('help')
    cache = Cache()
    bot.add_cog(ScoreSheetBot(bot, cache))
    bot.run(token)

if __name__ == '__main__':
    main()
