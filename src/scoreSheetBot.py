import logging
import math
from asyncio import sleep

from discord.ext import commands, tasks, menus
from discord.ext.commands import Greedy

from elo_helpers import rating_update
from sheet_helpers import update_gambit_sheet, update_ba_sheet, update_bf_sheet, update_mc_player_sheet, \
    update_mc_sheet, update_trinity_sheet, update_destiny_sheet, update_wisdom_sheet
from helpers import *
from db_helpers import *
from cache import Cache
from battle import Battle
from character import all_emojis, string_to_emote, all_alts, CHARACTERS
from decorators import *
from help import help_doc
from constants import *
from bracket import Bracket, Questions, NUMBER_QUESTIONS, current_bracket, draw_bracket
import logging

logging.basicConfig(level=logging.INFO)

Context = discord.ext.commands.Context

class ScoreSheetBot(commands.Cog):
    def __init__(self, bot: commands.bot, cache: Cache):
        self.bot = bot
        self.battle_map: Dict[str, Battle] = {}
        self.cache_value = cache
        self.cache_time = time.time()
        self.auto_cache.start()
        self._gambit_message = None

    @property
    def cache(self) -> Cache:
        if self.cache_time + CACHE_TIME_BACKUP < time.time():
            self.cache_time = time.time()
            asyncio.create_task(self._cache_process(True), name='recache')
        return self.cache_value

    async def _cache_process(self, backup=False):
        self.cache_time = time.time()
        if self.cache_value.channels and os.getenv('VERSION') == 'PROD':
            if backup:
                await self.cache_value.channels.recache_logs.send('(Backup)')
            await self.cache_value.channels.recache_logs.send('Starting recache.')

        await self.cache_value.update(self)
        crew_update(self)
        print(time.time() - self.cache_time)
        if os.getenv('VERSION') == 'PROD':
            await clear_current_cbs(self)
            for battle_type in BattleType:
                summary = battle_summary(self, battle_type)
                if summary:
                    await send_long_embed(self.cache.channels.current_cbs, summary)

            # await handle_decay(self)
            await handle_unfreeze(self)
            if self.cache_value.scs:
                await overflow_anomalies(self)
            await cooldown_handle(self)
            await track_handle(self)
            await self.cache_value.channels.recache_logs.send('Successfully recached.')
            update_wisdom_sheet()
            # update_trinity_sheet()
            # update_destiny_sheet()
            # update_all_sheets()
        print(time.time() - self.cache_time)
        self.cache_time = time.time()

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

    async def _reg_crew_lookup(self, ctx: Context):
        author_crew = crew_or_none(ctx.author, self)
        if author_crew:
            if author_crew != self._current(ctx).team1.name:
                await response_message(ctx, f'You are on {author_crew} which is not participating in this battle.'
                                            f'If you should no longer be on this crew, please unflair.')
                return
            if not check_roles(ctx.author, [LEADER, ADVISOR, MINION, ADMIN]):
                await response_message(ctx, f'You need to be a leader to run this command.')
                return

        if not author_crew:
            author_crew = self._current(ctx).team2.name
        return author_crew

    async def _reject_outsiders(self, ctx: Context):
        if self._current(ctx).battle_type in (BattleType.MOCK, BattleType.REG):
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
        if ctx.channel.id in BOT_LIMITED_CHANNELS and not check_roles(ctx.author, STAFF_LIST):
            await ctx.message.delete()
            msg = await ctx.send(f'Jettbot is disabled for non staff in channel please use <#{BOT_CORNER_ID}> instead.')
            await msg.delete(delay=5)
            raise ValueError('Jettbot is Disabled for non staff in this channel.')
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
        await self._cache_process()

    @auto_cache.before_loop
    async def wait_for_bot(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_remove(self, user):
        update_member_status((), (user.id,))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if os.getenv('VERSION') == 'PROD':
            if before.display_name != after.display_name:
                record_nicknames([(after.id, after.display_name)])
            if before.roles != after.roles:
                update_member_roles(after)
                try:
                    after_crew = crew(after, self)
                except ValueError:
                    after_crew = None
                if not crew_correct(after, after_crew):
                    if after_crew:
                        after_crew = crew_lookup(after_crew, self)
                    update_member_crew(after.id, after_crew)
                    self.cache.minor_update(self)

                await set_categories(after, self.cache.categories)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if os.getenv('VERSION') == 'PROD':
            role_ids = find_member_roles(member)
            if role_ids:
                roles = [discord.utils.get(member.guild.roles, id=role_id) for role_id in role_ids if
                         role_id not in (803364975539781662, 842888594519097394)]
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

    @commands.command(**help_doc['lock'], aliases=['mohamed', 'nohamed', 'lk'])
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
        if current and not current.battle_type == BattleType.MOCK:
            if not check_roles(ctx.author, STAFF_LIST):
                await self._reject_outsiders(ctx)
            overwrites: Dict = ctx.channel.overwrites
            muted_overwite = discord.PermissionOverwrite(send_messages=False, add_reactions=False,
                                                         manage_messages=False)

            crew_overwrite = discord.PermissionOverwrite(send_messages=True, add_reactions=True)
            if crew_lookup(current.team1.name, self).overflow:
                _, mems, _ = members_with_str_role(current.team1.name, self)
                for mem in mems:
                    if not check_roles(mem, [MUTED]):
                        overwrites[mem] = crew_overwrite
            else:
                cr_role_1 = discord.utils.get(ctx.guild.roles, name=current.team1.name)
                overwrites[cr_role_1] = crew_overwrite
                for mem in overlap_members(MUTED, current.team1.name, self):
                    overwrites[mem] = muted_overwite
            if crew_lookup(current.team2.name, self).overflow:
                _, mems, _ = members_with_str_role(current.team2.name, self)
                for mem in mems:
                    if not check_roles(mem, [MUTED]):
                        overwrites[mem] = crew_overwrite
            else:
                cr_role_2 = discord.utils.get(ctx.guild.roles, name=current.team2.name)
                overwrites[cr_role_2] = crew_overwrite
                for mem in overlap_members(MUTED, current.team2.name, self):
                    overwrites[mem] = muted_overwite
            everyone_overwrite = discord.PermissionOverwrite(send_messages=False, manage_messages=False,
                                                             add_reactions=False, create_public_threads=False,
                                                             create_private_threads=False)
            overwrites[self.cache.roles.everyone] = everyone_overwrite
            out = f'Room Locked to only {current.team1.name} and {current.team2.name}.'
            if streamer:
                if check_roles(streamer, [MUTED]):
                    out += f'{streamer.mention} is muted and does not get speaking perms.'
                else:
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

    @commands.command(**help_doc['battle'], aliases=['wisdom'], group='CB')
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
            actual_user = crew_lookup(user_crew, self)
            actual_opp = crew_lookup(opp_crew, self)
            if actual_user.triforce > 0 and actual_user.triforce == actual_opp.triforce:
                await ctx.send(
                    f"{ctx.author.mention} If this is your assigned weekly battle please `,clear` this battle and use"
                    "`,power` or `,courage` instead!")
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, BattleType.WISDOM))

            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['mock'])
    @no_battle
    @ss_channel
    async def mock(self, ctx: Context, team1: str, team2: str, size: int):
        if size < 1:
            await ctx.send('Please enter a size greater than 0.')
            return
        await self._set_current(ctx, Battle(team1, team2, size, BattleType.MOCK))
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help_doc['reg'])
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def reg(self, ctx: Context, *, everything: str):
        split = everything.split(' ')
        if not split:
            await response_message(ctx, 'Format for this command is `,reg RegisteringCrewName size`')
            return
        try:
            size = int(split[-1])
        except ValueError:
            await response_message(ctx, 'Format for this command is `,reg RegisteringCrewName size`')
            return
        registering_crew = ' '.join(split[:-1])
        if size < 1:
            await ctx.send('Please enter a size greater than 0.')
            return
        try:
            real_crew = crew(ctx.author, self)
        except ValueError:
            await response_message(ctx, f'You have to be on a crew to challenge a registering crew.')
            return
        await self._set_current(ctx, Battle(real_crew, registering_crew, size, BattleType.REG))
        await ctx.send(embed=self._current(ctx).embed())

    @commands.command(**help_doc['battle'], aliases=['straw'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def strawhat(self, ctx: Context, user: discord.Member, size: int):
        if size < 6:
            await ctx.send('Please enter a size greater than 5.')
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
            user_actual = crew_lookup(user_crew, self)
            opp_actual = crew_lookup(opp_crew, self)
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, BattleType.SH_PLAYOFF))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['battle'], aliases=['cowybattle'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def cowy(self, ctx: Context, user: discord.Member, size: int):
        if size < 7:
            await ctx.send('Please enter a size 7 or greater.')
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
            user_actual = crew_lookup(user_crew, self)
            opp_actual = crew_lookup(opp_crew, self)
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, BattleType.COWY))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['battle'], aliases=['playoff', 'pob'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def trinity(self, ctx: Context, user: discord.Member, size: int):
        if size < 7:
            await ctx.send('Please enter a size greater than 6.')
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
            user_actual = crew_lookup(user_crew, self)
            opp_actual = crew_lookup(opp_crew, self)
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, BattleType.TRINITY_PLAYOFF))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['battle'], aliases=['top'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def power(self, ctx: Context, user: discord.Member, size: int):
        if size < 7:
            await ctx.send('Please enter a size 7 or greater.')
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
            user_actual = crew_lookup(user_crew, self)
            if user_actual.triforce != 2:
                await ctx.send(f'{user_crew} is not in Triforce of Power.')
                return
            opp_actual = crew_lookup(opp_crew, self)
            if opp_actual.triforce != 2:
                await ctx.send(f'{opp_crew} is not in Triforce of Power.')
                return
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, BattleType.POWER))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['battle'], aliases=['courage'], group='CB')
    @main_only
    @no_battle
    @is_lead
    @ss_channel
    async def mid(self, ctx: Context, user: discord.Member, size: int):
        if size < 6:
            await ctx.send('Please enter a size 6 or greater.')
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
            user_actual = crew_lookup(user_crew, self)
            if user_actual.triforce != 1:
                await ctx.send(f'{user_crew} is not in Triforce of Courage.')
                return
            opp_actual = crew_lookup(opp_crew, self)
            if opp_actual.triforce != 1:
                await ctx.send(f'{opp_crew} is not in Triforce of Courage.')
                return
            await self._set_current(ctx, Battle(user_crew, opp_crew, size, BattleType.COURAGE))
            await send_sheet(ctx, battle=self._current(ctx))
        else:
            await ctx.send('You can\'t battle your own crew.')

    @commands.command(**help_doc['countdown'])
    @ss_channel
    async def countdown(self, ctx: Context, seconds: Optional[int] = 10):
        if seconds > 10 or seconds < 1:
            await ctx.send('You can only countdown from 10 or less!')
            return
        await ctx.send(f'Counting down from {seconds}')
        while seconds > 0:
            await ctx.send(f'{seconds}')
            seconds -= 1
            await sleep(1)
        await ctx.send('Finished!')

    @commands.command(**help_doc['send'], aliases=['s'])
    @has_sheet
    @ss_channel
    @is_lead
    async def send(self, ctx: Context, user: discord.Member, team: str = None):
        if self._current(ctx).battle_type == BattleType.REG:
            if not check_roles(user, [VERIFIED]):
                await response_message(ctx,
                                       f'{user.mention} does not have the DC Verified role. Which is required for '
                                       f'crew battle participation.'
                                       f'They can verify by typing `/verify` in any channel and then clicking the '
                                       f'"Click me to verify!" link in the Double Counter dm.')
                return
            author_crew = crew_or_none(ctx.author, self)
            if author_crew:
                if author_crew != self._current(ctx).team1.name:
                    await response_message(ctx, f'You are on {author_crew} which is not participating in this battle.'
                                                f'If you should no longer be on this crew, please unflair.')
                    return
                if not check_roles(ctx.author, [LEADER, ADVISOR, MINION, ADMIN]):
                    await response_message(ctx, f'You need to be a leader to run this command.')
                    return
                player_crew = await self._battle_crew(ctx, user)
                if author_crew == player_crew:
                    if check_roles(user, [WATCHLIST]):
                        await ctx.send(f'Watch listed player {user.mention} cannot play in ranked battles.')
                        return
                    if check_roles(user, [JOIN_CD]):
                        await ctx.send(
                            f'{user.mention} joined this crew less than '
                            f'12 hours ago and must wait to play ranked battles.')
                        return
                    self._current(ctx).add_player(author_crew, escape(user.display_name), ctx.author.mention, user.id)
                else:
                    await ctx.send(f'{escape(user.display_name)} is not on {author_crew} please choose someone else.')
                    return
            if not author_crew:
                author_crew = self._current(ctx).team2.name
                player_crew = crew_or_none(user, self)
                if player_crew:
                    await response_message(ctx, f'{user.mention} is on {player_crew} which is not participating '
                                                f'in this battle.'
                                                f'If they should no longer be on this crew, please unflair.')
                else:
                    self._current(ctx).add_player(author_crew, escape(user.display_name), ctx.author.mention, user.id)

        elif self._current(ctx).battle_type == BattleType.MOCK:
            if not team:
                team = self._current(ctx).team_from_member(ctx.author.mention)
            if team:
                self._current(ctx).add_player(team, escape(user.display_name), ctx.author.mention, user.id)
            else:
                await ctx.send(f'During a mock you need to send with a teamname, like this'
                               f' `,send @playername teamname`.')
                return
        else:
            if not check_roles(user, [VERIFIED]):
                await response_message(ctx,
                                       f'{user.mention} does not have the DC Verified role. Which is required for '
                                       f'crew battle participation.'
                                       f'They can verify by typing `/verify` in any channel and then clicking the '
                                       f'"Click me to verify!" link in the Double Counter dm.')
                return
            if not check_roles(user, [FOURTYMAN]) and self._current(ctx).battle_type == BattleType.POWER:
                await response_message(ctx,
                                       f'{user.mention} does not have the `40-Man` role and is not on the roster.')
                return
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
                        f'12 hours ago and must wait to play ranked battles.')
                    return
                self._current(ctx).add_player(author_crew, escape(user.display_name), ctx.author.mention, user.id)
            else:
                await ctx.send(f'{escape(user.display_name)} is not on {author_crew} please choose someone else.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['use_ext'])
    @has_sheet
    @ss_channel
    @is_lead
    async def use_ext(self, ctx: Context, team: str = None):
        if self._current(ctx).battle_type == BattleType.REG:
            author_crew = await self._reg_crew_lookup(ctx)
            if self._current(ctx).ext_used(author_crew):
                await ctx.send(f'{team} has already used their extension.')
                return
            else:
                await ctx.send(f'{author_crew} just used their extension. '
                               f'They now get 5 more minutes for their next player to be in the arena.')
                return

        elif self._current(ctx).battle_type == BattleType.MOCK:
            if not team:
                team = self._current(ctx).team_from_member(ctx.author.mention)
            if team:
                if self._current(ctx).ext_used(team):
                    await ctx.send(f'{team} has already used their extension.')
                    return
                else:
                    await ctx.send(f'{team} just used their extension. '
                                   f'They now get 5 more minutes for their next player to be in the arena.')
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

    @commands.command(**help_doc['forfeit'], aliases=['ff'])
    @has_sheet
    @ss_channel
    @is_lead
    async def forfeit(self, ctx: Context, team: str = None):
        if self._current(ctx).battle_type == BattleType.REG:
            author_crew = await self._reg_crew_lookup(ctx)
            msg = await ctx.send(f'{ctx.author.mention}:{author_crew} has '
                                 f'{self._current(ctx).lookup(author_crew).stocks} stocks left, '
                                 f'are you sure you want to forfeit?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
        elif self._current(ctx).battle_type == BattleType.MOCK:
            if not team:
                team = self._current(ctx).team_from_member(ctx.author.mention)
            if team:
                msg = await ctx.send(f'{ctx.author.mention}:{team} has {self._current(ctx).lookup(team).stocks} stocks '
                                     f'left, are you sure you want to forfeit?')
                if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                    await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                    return
                self._current(ctx).forfeit(team)
            else:
                await ctx.send(f'During a mock you need to forfeit, like this'
                               f' `,forfeit teamname`')
                return
        else:
            await self._reject_outsiders(ctx)
            author_crew = await self._battle_crew(ctx, ctx.author)
            msg = await ctx.send(f'{ctx.author.mention}:{author_crew} has '
                                 f'{self._current(ctx).lookup(author_crew).stocks} stocks left, '
                                 f'are you sure you want to forfeit?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return
            self._current(ctx).forfeit(author_crew)
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['ext'])
    @has_sheet
    @ss_channel
    async def ext(self, ctx):
        await ctx.send(self._current(ctx).ext_str())

    @commands.command(**help_doc['replace'], aliases=['r'])
    @has_sheet
    @ss_channel
    @is_lead
    async def replace(self, ctx: Context, user: discord.Member, team: str = None):
        if self._current(ctx).battle_type == BattleType.REG:
            if not check_roles(user, [VERIFIED]):
                await response_message(ctx,
                                       f'{user.mention} does not have the DC Verified role. Which is required for '
                                       f'crew battle participation.'
                                       f'They can verify by typing `/verify` in any channel and then clicking the '
                                       f'"Click me to verify!" link in the Double Counter dm.')
                return
            author_crew = crew_or_none(ctx.author, self)
            if author_crew:
                if author_crew != self._current(ctx).team1.name:
                    await response_message(ctx, f'You are on {author_crew} which is not participating in this battle.'
                                                f'If you should no longer be on this crew, please unflair.')
                    return
                if not check_roles(ctx.author, [LEADER, ADVISOR, MINION, ADMIN]):
                    await response_message(ctx, f'You need to be a leader to run this command.')
                    return
                player_crew = await self._battle_crew(ctx, user)
                if author_crew == player_crew:
                    if check_roles(user, [WATCHLIST]):
                        await ctx.send(f'Watch listed player {user.mention} cannot play in ranked battles.')
                        return
                    if check_roles(user, [JOIN_CD]):
                        await ctx.send(
                            f'{user.mention} joined this crew less than '
                            f'12 hours ago and must wait to play ranked battles.')
                        return
                    self._current(ctx).replace_player(author_crew, escape(user.display_name), ctx.author.mention,
                                                      user.id)
                else:
                    await ctx.send(f'{escape(user.display_name)} is not on {author_crew} please choose someone else.')
                    return
            if not author_crew:
                author_crew = self._current(ctx).team2.name
                player_crew = crew_or_none(user, self)
                if player_crew:
                    await response_message(ctx, f'{user.mention} is on {player_crew} which is not participating '
                                                f'in this battle.'
                                                f'If they should no longer be on this crew, please unflair.')
                else:
                    self._current(ctx).replace_player(author_crew, escape(user.display_name), ctx.author.mention,
                                                      user.id)
        elif self._current(ctx).battle_type == BattleType.MOCK:
            if not team:
                team = self._current(ctx).team_from_member(ctx.author.mention)
            if team:
                self._current(ctx).replace_player(team, escape(user.display_name), ctx.author.mention, user.id)
            else:
                await ctx.send(f'During a mock you need to replace with a teamname, like this'
                               f' `,replace @playername teamname`.')
                return
        else:
            if not check_roles(user, [VERIFIED]):
                await response_message(ctx,
                                       f'{user.mention} does not have the DC Verified role. Which is required for '
                                       f'crew battle participation.'
                                       f'They can verify by typing `/verify` in any channel and then clicking the '
                                       f'"Click me to verify!" link in the Double Counter dm.')
                return
            await self._reject_outsiders(ctx)
            current_crew = await self._battle_crew(ctx, ctx.author)
            if not check_roles(user, [FOURTYMAN]) and self._current(ctx).battle_type == BattleType.POWER:
                await response_message(ctx,
                                       f'{user.mention} does not have the `40-Man` role and is not on the roster.')
                return
            if current_crew == await self._battle_crew(ctx, user):
                if check_roles(user, [WATCHLIST]):
                    await ctx.send(f'Watch listed player {user.mention} cannot play in ranked battles.')
                    return
                if check_roles(user, [JOIN_CD]):
                    await ctx.send(
                        f'{user.mention} joined this crew less than '
                        f'12 hours ago and must wait to play ranked battles.')
                    return
                self._current(ctx).replace_player(current_crew, escape(user.display_name), ctx.author.mention, user.id)

            else:
                await ctx.send(f'{escape(user.display_name)} is not on {current_crew}, please choose someone else.')
                return
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['end'], aliases=['e'])
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

    @commands.command(**help_doc['resize'], aliases=['extend'])
    @is_lead
    @has_sheet
    @ss_channel
    async def resize(self, ctx: Context, new_size: int):
        if new_size > 9999:
            await ctx.send('Too big. Pls stop')
            return
        await self._reject_outsiders(ctx)
        self._current(ctx).resize(new_size)
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['arena'], aliases=['id', 'arena_id', 'lobby'])
    @has_sheet
    @ss_channel
    async def arena(self, ctx: Context, id_str: str = ''):
        if id_str and (check_roles(ctx.author, [LEADER, ADVISOR, ADMIN, MINION, STREAMER, CERTIFIED]
                                   ) or self._current(ctx).battle_type == BattleType.MOCK):
            self._current(ctx).id = id_str
            await ctx.send(f'Updated the id to {id_str}')
            return
        await ctx.send(f'The lobby id is {self._current(ctx).id}')

    @commands.command(**help_doc['stream'], aliases=['streamer', 'stream_link'])
    @has_sheet
    @ss_channel
    async def stream(self, ctx: Context, stream: str = ''):
        if stream and (check_roles(ctx.author, [LEADER, ADVISOR, ADMIN, MINION, STREAMER, CERTIFIED]
                                   ) or self._current(ctx).battle_type == BattleType.MOCK):
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

    # @commands.command(**help_doc['difficulty'], aliases=['d'])
    # @main_only
    # @has_sheet
    # @ss_channel
    # @is_lead
    # async def difficulty(self, ctx):
    #     await self._reject_outsiders(ctx)
    #     if not self._current(ctx).battle_type == BattleType.ARCADE:
    #         await response_message(ctx, 'You can only set the difficulty in an Arcade match.')
    #         return
    #     if not self._current(ctx).check_difficulty(crew(ctx.author, self)) == Difficulty.UNSET:
    #         await response_message(ctx, 'Difficulty is already set and cannot be changed.')
    #         return
    #     await response_message(ctx, f' check your dms!')
    #     author_crew = await self._battle_crew(ctx, ctx.author)
    #     msg = await ctx.author.send(f'For your battle {self._current(ctx).team1.name} vs '
    #                                 f'{self._current(ctx).team2.name} what difficulty do you choose?\n'
    #                                 f'Easy {YES}\n'
    #                                 f'Normal {NORMAL}\n'
    #                                 f'Hard {NO}')
    #     await msg.add_reaction(YES)
    #     await msg.add_reaction(NORMAL)
    #     await msg.add_reaction(NO)
    #     diff = Difficulty.UNSET
    #
    #     def check_reaction(reaction, user):
    #         return user == ctx.author and str(reaction.emoji) in (
    #             YES, NO, NORMAL)
    #
    #     while True:
    #         try:
    #             react, reactor = await self.bot.wait_for('reaction_add', timeout=30, check=check_reaction)
    #         except asyncio.TimeoutError:
    #             await ctx.author.send(f'Timed out')
    #             return False
    #         if react.message.id != msg.id:
    #             continue
    #         if str(react.emoji) == YES and reactor == ctx.author:
    #             diff = Difficulty.EASY
    #             break
    #         elif str(react.emoji) == NO and reactor == ctx.author:
    #             diff = Difficulty.HARD
    #             break
    #         elif str(react.emoji) == NORMAL and reactor == ctx.author:
    #             diff = Difficulty.NORMAL
    #             break
    #
    #     self._current(ctx).set_difficulty(author_crew, diff)
    #     await ctx.author.send(f'Your difficulty of {diff.name} is confirmed!')
    #     await ctx.send(f'{author_crew} selected difficulty!')

    @commands.command(**help_doc['confirm'])
    @has_sheet
    @ss_channel
    @is_lead
    async def confirm(self, ctx: Context):
        await self._reject_outsiders(ctx)
        current = self._current(ctx)
        if current.battle_over():

            if current.battle_type == BattleType.REG:

                current.confirm(await self._reg_crew_lookup(ctx))
                await send_sheet(ctx, battle=current)
                if current.confirmed():
                    today = date.today()

                    output_channels = [discord.utils.get(ctx.guild.channels, name=DOCS_UPDATES),
                                       discord.utils.get(ctx.guild.channels, name=OUTPUT)]
                    winner = current.winner().name
                    final_score = current.winner().stocks
                    loser = current.loser().name
                    current = self._current(ctx)
                    if not current:
                        return
                    await self._clear_current(ctx)
                    links = []
                    for output_channel in output_channels:
                        link = await send_sheet(output_channel, current)
                        links.append(link)
                    successful = (current.winner() == current.team2 or final_score < 5)

                    new_message = (f'**{today.strftime("%B %d, %Y")} (Registration) - {winner}⚔{loser}**\n'
                                   f'**Winner:** {winner} \n'
                                   f'**Loser:** {loser}\n')
                    if successful:
                        new_message += (f'Successful registration battle! Please allow doc keepers to finish the'
                                        f' registration process and submit this crew battle using `,addsheet '
                                        f'{winner} {loser} {current.team1.num_players} {final_score}`')
                    else:
                        new_message += (f'{current.team2.name} failed to register. Doc keepers can submit this battle'
                                        f'using `,failedreg {winner} {loser} {current.team1.num_players} '
                                        f'{final_score}`')
                    for link in links:
                        await link.edit(content=new_message)
                    # TODO Make this work for registration battles
                    # winner_elo, winner_change, loser_elo, loser_change = battle_elo_changes(battle_id)
                    # battle_weight_changes(battle_id)
                    # winner_crew = crew_lookup(winner, self)
                    # loser_crew = crew_lookup(loser, self)
                    # new_message = (f'**{today.strftime("%B %d, %Y")} (SCL 2021) - {winner}⚔{loser}**\n'
                    #                f'**Winner:** {winner_crew.abbr} '
                    #                f'[{winner_elo}+{winner_change}={winner_elo + winner_change}]\n'
                    #                f'**Loser:** {loser_crew.abbr} '
                    #                f'[{loser_elo}{loser_change}={loser_elo + loser_change}]\n'
                    #                f'**Battle:** {battle_id} from {ctx.channel.mention}')
                    # if current.battle_type == BattleType.MASTER:
                    #     bf_winner_elo, bf_winner_change, bf_loser_elo, bf_loser_change = battle_elo_changes(battle_id,
                    #                                                                                         True)
                    #     master_weight_changes(battle_id)
                    #     new_message = (f'**{today.strftime("%B %d, %Y")} (SCL 2021) - {winner}⚔{loser}**\n'
                    #                    '**Master Class**\n'
                    #                    f'**Winner:** {winner_crew.abbr} '
                    #                    f'[{winner_elo}+{winner_change}={winner_elo + winner_change}]\n'
                    #                    f'**Loser:** {loser_crew.abbr} '
                    #                    f'[{loser_elo}{loser_change}={loser_elo + loser_change}]\n'
                    #                    f'** Battle Frontier**\n'
                    #                    f'**Winner:** {winner_crew.abbr} '
                    #                    f'[{bf_winner_elo}+{bf_winner_change}={bf_winner_elo + bf_winner_change}]\n'
                    #                    f'**Loser:** {loser_crew.abbr} '
                    #                    f'[{bf_loser_elo}{bf_loser_change}={bf_loser_elo + bf_loser_change}]\n'
                    #                    f'**Battle:** {battle_id} from {ctx.channel.mention}')
                    #     update_mc_sheet()
                    # for link in links:
                    #     await link.edit(content=new_message)
                    await ctx.send(
                        f'The battle between {current.team1.name} and {current.team2.name} '
                        f'has been confirmed by both sides and posted in {output_channels[0].mention}. ')
                    # f'(Battle number:{battle_id})')
            elif current.battle_type == BattleType.MOCK:
                await self._clear_current(ctx)
                await ctx.send(f'This battle was confirmed by {ctx.author.mention}.')
            elif current.battle_type in (BattleType.POWER, BattleType.COURAGE):
                current.confirm(await self._battle_crew(ctx, ctx.author))
                await send_sheet(ctx, battle=current)
                if current.confirmed():
                    today = date.today()
                    if current.battle_type == BattleType.POWER:
                        name = 'Triforce of Power'
                        league_id = 22
                        channel_id = POWER_CHANNEL_ID
                    else:
                        name = 'Triforce of Courage'
                        league_id = 21
                        channel_id = COURAGE_CHANNEL_ID
                    output_channels = [
                        discord.utils.get(ctx.guild.channels, id=channel_id),
                        discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
                        discord.utils.get(ctx.guild.channels, name=OUTPUT)]
                    winner = current.winner().name
                    loser = current.loser().name
                    current = self._current(ctx)
                    if not current:
                        return
                    await self._clear_current(ctx)
                    links = []
                    for output_channel in output_channels:
                        link = await send_sheet(output_channel, current)
                        links.append(link)
                    battle_id = add_finished_battle(current, links[0].jump_url, league_id)
                    battle_weight_changes(battle_id)
                    winner_crew = crew_lookup(winner, self)
                    loser_crew = crew_lookup(loser, self)
                    new_message = (
                        f'**{today.strftime("%B %d, %Y")} ({name}) - {winner}⚔{loser}**\n'
                        f'**Winner:** <@&{winner_crew.role_id}> ({winner_crew.abbr})\n '
                        f'**Loser:** <@&{loser_crew.role_id}> ({loser_crew.abbr}) \n'
                        f'**Battle:** {battle_id} from {ctx.channel.mention}')
                    for link in links:
                        await link.edit(content=new_message)
                    await ctx.send(
                        f'The battle between {current.team1.name} and {current.team2.name} '
                        f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
                        f'(Battle number:{battle_id})')

                    await links[0].add_reaction(YES)
                    for cr in (winner_crew, loser_crew):
                        if not extra_slot_used(cr):
                            if battles_since_sunday(cr) >= 3:
                                mod_slot(cr, 1)
                                await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')
                                set_extra_used(cr)
            else:
                current.confirm(await self._battle_crew(ctx, ctx.author))
                await send_sheet(ctx, battle=current)
                if current.confirmed():
                    today = date.today()

                    output_channels = [discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
                                       discord.utils.get(ctx.guild.channels, name=OUTPUT)]
                    winner = current.winner().name
                    loser = current.loser().name
                    league_id = CURRENT_LEAGUE_ID
                    current = self._current(ctx)
                    if not current:
                        return
                    await self._clear_current(ctx)
                    links = []
                    for output_channel in output_channels:
                        link = await send_sheet(output_channel, current)
                        links.append(link)
                    battle_id = add_finished_battle(current, links[0].jump_url, league_id)
                    battle_weight_changes(battle_id)
                    winner_crew = crew_lookup(winner, self)
                    loser_crew = crew_lookup(loser, self)
                    winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k = battle_elo_changes(
                        battle_id)
                    w_placement = (200 - winner_k) / 30 + 1
                    l_placement = (200 - loser_k) / 30 + 1
                    if w_placement < 6:
                        w_placement_message = f'Placement round {int(w_placement)}'
                        differential = winner_k / 50
                        winner_k_message = f'({winner_change // differential}* {differential})'
                    else:
                        w_placement_message = ''
                        winner_k_message = winner_change
                    if l_placement < 6:
                        l_placement_message = f'Placement round {int(l_placement)}'
                        differential = loser_k / 50
                        loser_k_message = f'({loser_change // differential}* {differential})'
                    else:
                        l_placement_message = ''
                        loser_k_message = loser_change
                    battle_name = 'Triforce of Wisdom'
                    new_message = (
                        f'**{today.strftime("%B %d, %Y")} ({battle_name}) - {winner} ({winner_crew.abbr})⚔'
                        f'{loser} ({loser_crew.abbr})**\n'
                        f'**Winner:** <@&{winner_crew.role_id}> [{winner_elo} '
                        f'+ {winner_change} = {winner_elo + winner_change}] \n'
                        f'**Loser:** <@&{loser_crew.role_id}> [{loser_elo} '
                        f'- {abs(loser_change)} = {loser_elo + loser_change}] \n'
                        f'**Battle:** {battle_id} from {ctx.channel.mention}')
                    for link in links:
                        await link.edit(content=new_message)
                    await ctx.send(
                        f'The battle between {winner}({w_placement_message}) and {loser}({l_placement_message}) '
                        f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
                        f'(Battle number:{battle_id})')
                    for cr in (winner_crew, loser_crew):
                        if not extra_slot_used(cr):
                            if battles_since_sunday(cr) >= 3:
                                mod_slot(cr, 1)
                                await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')
                                set_extra_used(cr)
        else:
            await ctx.send('The battle is not over yet, wait till then to confirm.')

    @commands.command(**help_doc['clear'])
    @has_sheet
    @ss_channel
    @is_lead
    async def clear(self, ctx):
        if not check_roles(ctx.author, STAFF_LIST):
            await self._reject_outsiders(ctx)
        if self._current(ctx).battle_type == BattleType.MOCK:
            await ctx.send('If you just cleared a crew battle to troll people, be warned this is a bannable offence.')

        msg = await ctx.send(f'Are you sure you want to clear this crew battle?')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            resp = await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            await resp.delete(delay=10)
            await ctx.message.delete()
            await msg.delete(delay=5)
            return

        await self._clear_current(ctx)
        await ctx.send(f'{ctx.author.mention} cleared the crew battle.')

    @commands.command(**help_doc['status'])
    @has_sheet
    @ss_channel
    async def status(self, ctx):
        await send_sheet(ctx, battle=self._current(ctx))

    @commands.command(**help_doc['timer'], aliases=['🤓'])
    @has_sheet
    @ss_channel
    async def timer(self, ctx):
        await ctx.send(self._current(ctx).timer())

    @commands.command(**help_doc['timerstock'])
    @has_sheet
    @ss_channel
    @is_lead
    async def timerstock(self, ctx, team: str = None):
        if self._current(ctx).battle_type == BattleType.MOCK:
            if not team:
                team = self._current(ctx).team_from_member(ctx.author.mention)
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

    ''' *************************************** BATTLE ARENA COMMANDS ********************************************'''

    @commands.group(name='ba', brief='Commands for battle_arena', invoke_without_command=True)
    async def ba(self, ctx):
        await self.help(ctx, 'crews')

    @commands.command(**help_doc['result'])
    async def result(self, ctx: Context, opponent: discord.Member, *, everything: str):
        if ctx.channel.id != 808957203447808000:
            msg = await response_message(ctx, 'This command can only be used in <#808957203447808000>')
            await msg.delete(delay=3)
            return
        split = everything.split()
        score_split = 0
        while not split[score_split].isdigit():
            score_split += 1
            if score_split == len(split):
                await response_message(ctx, f'Format of result is: '
                                            f'`@opponent yourchar yourchar2 yourscore opponentscore opponentchar\n'
                                            f'eg `,result @EvilJett#0995 ness3 pika4 3 2 palu1`')
                return
        p1_chars = [Character(sp, self.bot) for sp in split[0:score_split]]
        p2_chars = [Character(sp, self.bot) for sp in split[score_split + 2:]]
        if not p1_chars or not p2_chars:
            await response_message(ctx, f'Both players need at least 1 character.\n'
                                        f'Format of result is: '
                                        f'`@opponent yourchar yourchar2 yourscore opponentscore opponentchar\n'
                                        f'eg `,result @EvilJett#0995 ness3 pika4 3 2 palu1`')
            return
        p1_score = int(split[score_split])
        if not split[score_split + 1].isdigit():
            await response_message(ctx, f'Format of result is: '
                                        f'`@opponent yourchar yourchar2 yourscore opponentscore opponentchar\n'
                                        f'eg `,result @EvilJett#0995 ness3 pika4 3 2 palu1`')
            return
        p2_score = int(split[score_split + 1])
        if not ((p1_score == 3) != (p2_score == 3)) or not (0 <= p1_score <= 3 and 0 <= p2_score <= 3):
            await response_message(ctx, f'A score of {p1_score} - {p2_score} is not valid for a best of 5')
            return
        if p1_score > p2_score:
            winner_score = p1_score
            loser_score = p2_score
            winner_member = ctx.author
            winner_chars = p1_chars
            loser_member = opponent
            loser_chars = p2_chars
        else:
            winner_score = p2_score
            loser_score = p1_score
            winner_member = opponent
            loser_member = ctx.author
            winner_chars = p2_chars
            loser_chars = p1_chars

        embed = discord.Embed(title=f'{ctx.author.display_name} vs {opponent.display_name}',
                              color=discord.Color.random())
        embed.add_field(name=f'{p1_score}', value=' '.join([str(char) for char in p1_chars]), inline=True)
        embed.add_field(name=f'{p2_score}', value=' '.join([str(char) for char in p2_chars]), inline=True)
        embed.add_field(name=f'**Winner: {winner_member.display_name}**', inline=False,
                        value=f'Loser: {loser_member.display_name}')
        msg = await ctx.send(f'{opponent.mention} please confirm this match.', embed=embed)
        if not await wait_for_reaction_on_message(YES, NO, msg, opponent, self.bot, 600.0):
            resp = await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            await resp.delete(delay=10)
            await ctx.message.delete()
            await msg.delete(delay=5)
            return
        win_elo = get_member_elo(winner_member.id)
        lose_elo = get_member_elo(loser_member.id)
        winner_change, loser_change = rating_update(win_elo, lose_elo, 1)
        add_ba_match(win_elo, lose_elo, winner_chars, loser_chars, winner_change, loser_change, winner_score,
                     loser_score)
        result_embed = discord.Embed(
            title=f'{winner_member.display_name} {winner_score}-{loser_score} {loser_member.display_name}',
            color=winner_member.color)
        result_embed.add_field(name=f'{winner_member.display_name}', value=f'{win_elo.rating}+{winner_change}',
                               inline=True)
        result_embed.add_field(name=f'{loser_member.display_name}', value=f'{lose_elo.rating}{loser_change}',
                               inline=True)
        await ctx.send(embed=result_embed)
        update_ba_sheet()

    ''' *************************************** CREW COMMANDS ********************************************'''

    @commands.group(name='crews', brief='Commands for crews, including stats and rankings', invoke_without_command=True)
    async def crews(self, ctx):
        await self.help(ctx, 'crews')

    @commands.command(**help_doc['rankings'])
    async def rankings(self, ctx):

        crew_ranking_str = [f'{cr[2]}: **{cr[1]}**'
                            for cr
                            in wisdom_rankings()]

        pages = menus.MenuPages(source=Paged(crew_ranking_str, title='Triforce of Wisdom Rankings'),
                                clear_reactions_after=True)
        await pages.start(ctx)

        pages = menus.MenuPages(source=TriforceStatsPaged(power_rankings(), courage_rankings()),
                                clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['umbralotto'])
    async def umbralotto(self, ctx, rank: int):
        if 0 > rank or rank > 6:
            await response_message(ctx, 'There are no crews at that rank')
            return
        possibles = []
        rank_ups = set()
        for cr in self.cache.crews_by_name.values():
            if cr.rank == rank:
                possibles.append(cr.name)
            if cr.rank_up:
                rank_ups.add(cr.name)
                rank_ups.add(cr.rank_up)
        if not possibles:
            await response_message(ctx, 'There are no crews at that rank')
            return
        for i, cr in reversed(list(enumerate(possibles))):
            if cr in rank_ups:
                possibles.pop(i)
        await ctx.send(f'You got {random.choice(possibles)} as a rank {rank} crew.')

    @commands.command(**help_doc['umbralotto'])
    async def umbralottotest(self, ctx, rank: int):
        if 0 > rank or rank > 6:
            await response_message(ctx, 'There are no crews at that rank')
            return
        possibles = []
        for cr in self.cache.crews_by_name.values():
            if cr.rank == rank:
                possibles.append(cr.name)
        if not possibles:
            await response_message(ctx, 'There are no crews at that rank')
            return
        possibles_dict = {name: 0 for name in possibles}
        for _ in range(100000):
            choice = random.choice(possibles)
            possibles_dict[choice] += 1
        outstring = ''
        for possible in possibles_dict:
            outstring += f'{possible}: {possibles_dict[possible]}\n'
        await ctx.send(outstring)

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
        pages = menus.MenuPages(source=PlayerStatsPaged(member, self))
        await pages.start(ctx)

    @commands.command(**help_doc['stats'], aliases=['TAH'])
    @main_only
    async def stats(self, ctx, *, name: str = None):
        if name:
            ambiguous = ambiguous_lookup(name, self)
            if isinstance(ambiguous, discord.Member):

                pages = menus.MenuPages(source=PlayerStatsPaged(ambiguous, self))
                await pages.start(ctx)
                return
            else:
                actual_crew = ambiguous
        else:
            pages = menus.MenuPages(source=PlayerStatsPaged(ctx.author, self))
            await pages.start(ctx)
            return
        record = crew_record(actual_crew, 20)
        if not record[2]:
            await ctx.send(f'{actual_crew.name} does not have any recorded crew battles with the bot.')
            return
        title = f'{actual_crew.name}: {record[1]}-{int(record[2]) - int(record[1])}'
        pages = menus.MenuPages(
            source=Paged(crew_matches(actual_crew), title=title, color=actual_crew.color, thumbnail=actual_crew.icon),
            clear_reactions_after=True)
        await pages.start(ctx)

    @commands.command(**help_doc['history'])
    @main_only
    async def history(self, ctx, *, name: str = None):
        in_server = True
        if name:
            if name.isdigit() and len(name) > 16:
                try:
                    member = user_by_id(name, self)
                except ValueError:
                    in_server = False
            else:
                member = member_lookup(name, self)

        else:
            member = ctx.author
        if in_server:
            member_id = member.id
            member_name = member.display_name
            member_color = member.colour
        else:
            member_id, member_name = name, nickname_lookup(int(name))
            if not member_name:
                raise ValueError(f'Member {name} has never been recorded on this server.')
            member_color = discord.Color.blurple()
        if member_id == 775586622241505281:
            await ctx.send('Don\'t use EvilJett for this')
            return
        embed = discord.Embed(title=f'Crew History for {member_name}', color=member_color)
        desc = []
        current = member_crew_and_date(member_id)
        if current:
            desc.append(f'**Current crew:** {current[0]} Joined: {current[1].strftime("%m/%d/%Y")}')
        past = member_crew_history(member_id)
        desc.append('**Past Crew              Date            Action**')
        for cr_name, timing, which in past:
            j = timing.strftime('%m/%d/%Y')
            action = 'Flaired' if which else 'Unflaired'
            desc.append(f'**{cr_name}** {j}       {action}')
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
        if not check_roles(member, [VERIFIED]):
            await response_message(ctx, f'{member.mention} does not have the DC Verified role. Which is required for '
                                        f'leadership.'
                                        f'They can verify by typing `/verify` in any channel and then clicking the '
                                        f'"Click me to verify!" link in the Double Counter dm.')
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
        if not check_roles(member, [VERIFIED]):
            await response_message(ctx, f'{member.mention} does not have the DC Verified role. '
                                        f'They can verify by typing `/verify` in any channel and then clicking the '
                                        f'"Click me to verify!" link in the Double Counter dm.')
            return
        if check_roles(member, [LEADER]):
            await response_message(ctx, f'{member.mention} is already a leader.')
            return
        if check_roles(member, [LEAD_RESTRICT]):
            await response_message(ctx, f'{member.mention} is leadership restricted and can\'t be made a leader.')
            return
        before = set(member.roles)
        await promote(member, self, True)
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
                if 'on this server' in str(e):
                    await unflair_gone_member(ctx, user, self)
                else:
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
                await member.remove_roles(self.cache.roles.fortyman)
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
            unflairs, left, total = record_unflair(member.id, user_crew, True)
            await ctx.send(
                f'{str(member)} was on 12h cooldown so {user_crew.name} gets back a slot ({left}/{total})')
        else:
            unflairs, remaining, total = record_unflair(member.id, user_crew, False)
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
                                   f'{flairing_crew.name} is recruitment frozen till '
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
        # if len(crew_members(flairing_crew, self)) == 40:
        #     message = 'You have just flaired the 40th person for your crew. When the first of the month hits, ' \
        #               'this will make you eligible for soft cap restrictions. Check out the SCS rules or use the ' \
        #               '<#492166249174925312> channel if you are unsure what this means.'
        #     try:
        #         await ctx.author.send(message)
        #     except discord.errors.Forbidden:
        #         await ctx.send(f'{ctx.author.mention}  {message}')
        await self.cache.channels.flair_log.send(
            embed=role_change(before, after, ctx.author, member, of_before, of_after))

    @commands.command(**help_doc['multiflair'])
    @main_only
    @flairing_required
    async def multiflair(self, ctx: Context, members: Greedy[discord.Member], new_crew: str = None):
        for member in set(members):
            await self.flair(ctx, member, new_crew=new_crew)

    @commands.command(**help_doc['multiunflair'])
    @main_only
    @flairing_required
    async def multiunflair(self, ctx: Context, *, everything: str):
        members = everything.split(' ')
        for member in set(members):
            await self.unflair(ctx, member)

    ''' ***********************************GAMBIT COMMANDS ************************************************'''

    @commands.command(**help_doc['predictions'])
    async def predictions(self, ctx):
        await ctx.message.add_reaction(emoji='✉')
        await ctx.message.delete(delay=5)
        crew_names = ['Black Halo', 'Arpeggio', 'Dream Casters', 'Holy Knights', 'Valerian',
                      'Sound of Perfervid', 'Midnight Sun', 'Phantom Troupe', 'Flow State Gaming',
                      'Wombo Combo', 'Black Gang', 'Phantasm', 'Down B Queens', 'Lazarus']
        bye = Crew(name='Bye (Do not click)', abbr='Bye', db_id=528, color=discord.Color.from_rgb(255, 255, 255),
                   icon='https://cdn.discordapp.com/attachments/792632199241400341/895178019990278254/bracket.png')
        bracket_crews = [crew_lookup(cr, self) for cr in crew_names]
        bracket_crews.insert(1, bye)
        bracket_crews.insert(9, bye)
        br = Bracket(bracket_crews, ctx.author)
        predictions = get_bracket_predictions(ctx.author.id)
        for prediction in predictions:
            br.report_winner(prediction[0])
        answers = get_bracket_questions(ctx.author.id)
        out_str = ['Your extra predictions!']
        for i, question in enumerate(NUMBER_QUESTIONS):
            out_str.append(question + ': ' + str(answers[i][0]))
        await ctx.author.send(content='\n'.join(out_str))

    @commands.command(**help_doc['predict'])
    async def predict(self, ctx):
        crew_names = ['Black Halo', 'Arpeggio', 'Dream Casters', 'Holy Knights', 'Valerian',
                      'Sound of Perfervid', 'Midnight Sun', 'Phantom Troupe', 'Flow State Gaming',
                      'Wombo Combo', 'Black Gang', 'Phantasm', 'Down B Queens', 'Lazarus']
        bye = Crew(name='Bye (Do not click)', abbr='Bye', db_id=528, color=discord.Color.from_rgb(255, 255, 255),
                   icon='https://cdn.discordapp.com/attachments/792632199241400341/895178019990278254/bracket.png')
        bracket_crews = [crew_lookup(cr, self) for cr in crew_names]
        bracket_crews.insert(1, bye)
        bracket_crews.insert(9, bye)
        await ctx.message.add_reaction(emoji='✉')
        await ctx.message.delete(delay=5)
        await ctx.author.send('Please answer both of the following to completion! You can check your predictions after'
                              ' with `,predictions` or modify your predictions by using `,predict` again.')
        await ctx.author.send('Bracket choosing', view=Bracket(bracket_crews, ctx.author))
        await ctx.author.send('Extra questions! (10 points each)', view=Questions(ctx.author))

    @commands.command(**help_doc['coins'])
    @main_only
    async def coins(self, ctx: Context, member: Optional[discord.Member] = None):
        member = member or ctx.author
        await ctx.send(f'{str(member)} has {member_gcoins(member)} G-Coins.')

    @commands.group(name='gamb', invoke_without_command=True)
    @main_only
    @role_call([MINION, ADMIN, LU])
    async def gamb(self, ctx: Context):
        if current_gambit():
            await ctx.send(f'{current_gambit()}')
        else:
            await ctx.send('No Current gambit.')

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN, LU, GAMB_OL])
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
    @role_call([MINION, ADMIN, LU, GAMB_OL])
    async def close(self, ctx: Context, stream: Optional[str] = '', channel: Optional[discord.TextChannel] = ''):
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
            ch = channel.mention if channel else ''
            await response_message(ctx, f'Gambit between {cg.team1} and {cg.team2} locked by {ctx.author.mention}.')
            await self.cache.channels.gambit_announce.send(
                f'{self.cache.roles.gambit.mention}: {cg.team1} vs {cg.team2} has started! {stream} {ch} ',
                embed=cg.embed(crew_lookup(cg.team1, self).abbr, crew_lookup(cg.team2, self).abbr))
            if self._gambit_message:
                await self._gambit_message.delete()

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN, LU, GAMB_OL])
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
            if member:
                total = refund_member_gcoins(member, amount)
                msg = (f'The gambit between {cg.team1} and {cg.team2} was canceled, '
                       f'you have been refunded {amount} G-Coins for your bet on {cr}.\n'
                       f'You now have {total} G-Coins.')

                try:
                    await member.send(msg)
                except discord.errors.Forbidden:
                    await ctx.send(f'{str(member)} is not accepting dms.')
        cancel_gambit()
        await ctx.send(f'Gambit between {cg.team1} and {cg.team2} cancelled. All participants have been refunded.')

    @gamb.command()
    @main_only
    @role_call([MINION, ADMIN, LU, GAMB_OL])
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
                    if member:
                        total = refund_member_gcoins(member, final)
                        if final > top_win[0]:
                            top_win = [final, str(member)]

                        msg = (f'You won {final} G-Coins on your bet of {amount} on {cr} over {loser}! '
                               f'Congrats you now have {total} G-Coins!')
                        try:
                            await member.send(msg)
                        except discord.errors.Forbidden:
                            await ctx.send(f'{str(member)} is not accepting dms.')
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
    @role_call([MINION, ADMIN, LU, GAMB_OL])
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
        left, total, uf = extra_slots(actual_crew)

        await ctx.send(f'{actual_crew.name} current slots: {left}/{total}  ({uf}/3) for unflair.')
        new = cur_slot_set(actual_crew, num)
        await ctx.send(f'Set {actual_crew.name} slots to {new}.')

    @commands.command(**help_doc['setslots'])
    @role_call(STAFF_LIST)
    @main_only
    async def tri(self, ctx, *, name: str = None):
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
        if actual_crew.triforce >= 0:
            msg = await ctx.send(
                f'{ctx.author.mention}: {actual_crew.name} is already in Triforce of {TRIFORCE[actual_crew.triforce]}\n'
                f'Do you want to reset that?'
            )
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
                await response_message(ctx, 'Canceled or timed out.')
                return
        msg = await ctx.send(
            f'{ctx.author.mention}: Do you want to place {actual_crew.name} in '
            f'\nTriforce of Courage {OPTIONS[0]}'
            f'\nTriforce of Power   {OPTIONS[1]}'
        )
        answer = await wait_choice(2, msg, ctx.author, self.bot, 120)
        if answer == -1:
            await response_message(ctx, 'Canceled or timed out.')
            return

        divs = COURAGE_DIVS if answer == 0 else POWER_DIVS
        message = ['Which division do you want to place them in?']
        for i in range(1, 5):
            message.append(f'{divs[i]}: {OPTIONS[i - 1]}')
        msg = await ctx.send('\n'.join(message))
        division = await wait_choice(4, msg, ctx.author, self.bot, 120)
        if division == -1:
            await response_message(ctx, 'Canceled or timed out.')
            return
        msg = await ctx.send(
            f'To confirm, you want to put {actual_crew.name} in the '
            f'Triforce of {"Courage" if answer == 0 else "Power"} {divs[division + 1]}?')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return
        update_crew_tf(actual_crew, answer + 1, division + 1)
        await ctx.send(f'{actual_crew.name} triforce status updated!')

    @commands.command(**help_doc['setreturnslots'])
    @role_call(STAFF_LIST)
    @main_only
    async def setreturnslots(self, ctx, num: int, *, name: str = None):
        if num not in (0, 1, 2, 3):
            msg = await response_message(ctx, f'{num} must be 0,1,2 or 3 ')
            await msg.delete(delay=5)
            return
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
        left, total, uf = extra_slots(actual_crew)

        await ctx.send(f'{actual_crew.name} current slots: {left}/{total}  ({uf}/3) for unflair.')
        uf, left, total = set_return_slots(actual_crew, num)
        await ctx.send(f'Set {actual_crew.name} new slots: {left}/{total}  ({uf}/3) for unflair.')

    @commands.command(hidden=True)
    @main_only
    @flairing_required
    @role_call(STAFF_LIST)
    async def fixunflair(self, ctx, *, name: str = None):
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
        left, total, uf = extra_slots(actual_crew)
        if uf > 0:
            uf += 2
            uf %= 3
            left += 1
            await self.setreturnslots(ctx, uf, name=actual_crew.name)
            await self.setslots(ctx, left, name=actual_crew.name)
        else:

            uf += 2
            await self.setreturnslots(ctx, uf, name=actual_crew.name)

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

    @commands.command(**help_doc['charge'])
    @role_call([MINION, ADMIN])
    async def charge(self, ctx, member: discord.Member, amount: int, *, reason: str = 'None Specified'):
        current = member_gcoins(member)
        if amount > current:
            await response_message(ctx,
                                   f'{member.mention} only has {current} G-Coins, they cannot be charged {amount}.')
            return
        msg = await ctx.send(
            f'{ctx.author.mention}: are you sure you want to charge {member.mention} {amount} G-Coins? For {reason}'
        )
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return
        final = charge(member.id, amount, reason)
        await ctx.send(f'{member.mention} sucessfully was charged {amount} G-Coins for {reason}! They now have {final}'
                       f' G-Coins.')

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

    @commands.command(**help_doc['opt'])
    @main_only
    @role_call(STAFF_LIST)
    async def opt(self, ctx, *, name: str = None):
        cr = crew_lookup(name, self)
        if cr.destiny_opt_out:
            msg = await ctx.send(f'{cr.name} is opted out for destiny, would you like to opt them back in?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
                await response_message(ctx, 'Canceled or timed out.')
                return
            destiny_opt(cr.db_id, False)
            await ctx.send(f'{cr.name} opted back in to destiny! (Rc to see)')
        else:
            msg = await ctx.send(f'Would you like to opt {cr.name} out for destiny?\n'
                                 f'This will reset their rank if they ever opt back in.')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
                await response_message(ctx, 'Canceled or timed out.')
                return
            destiny_opt(cr.db_id, True)
            await ctx.send(f'{cr.name} opted out of destiny! (Rc to see)')

    @commands.command(**help_doc['pair'])
    @main_only
    @role_call(STAFF_LIST)
    async def pair(self, ctx: Context, *, everything: str):

        best = best_of_possibilities(everything, self, True)

        crew_1 = crew_lookup(best[0], self)
        crew_2 = crew_lookup(best[1], self)

        for cr in (crew_1, crew_2):
            if cr.current_destiny != 100:
                await response_message(ctx, f'{cr.name} only has {cr.current_destiny} destiny and needs 100.')
                return
            if cr.destiny_opponent:
                msg = await ctx.send(f'{cr.name} already has'
                                     f' {cr.destiny_opponent} as an opponent would you like to clear it?.')
                if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
                    await response_message(ctx, 'Canceled or timed out.')
                    return
                opp = crew_lookup(cr.destiny_opponent, self)

                destiny_unpair(cr.db_id, opp.db_id)
                await response_message(ctx, f'{cr.name} and {opp.name} destiny opp reset.')
                return
            if cr.destiny_opt_out:
                await response_message(ctx, f'{cr.name} is opted out for destiny.')
                return
        msg = await ctx.send(f'Would you like to pair {crew_1.name} with {crew_2.name}?')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return
        destiny_pair(crew_1.db_id, crew_2.db_id)
        crew_1.destiny_opponent = crew_2.name
        crew_2.destiny_opponent = crew_1.name
        await ctx.send(f'{crew_1.name} has been paired with {crew_2.name} for destiny!')

    @commands.command(**help_doc['addforfeit'], hidden=True, aliases=['addff'])
    @main_only
    @role_call(STAFF_LIST)
    async def addforfeit(self, ctx: Context, *, everything: str):
        today = date.today()

        if not ctx.message.attachments:
            await response_message(ctx, 'You need to submit a screenshot of the forfeit with this.')
            return

        two_crews = everything
        best = best_of_possibilities(two_crews, self, True)

        winner_crew = crew_lookup(best[0], self)
        loser_crew = crew_lookup(best[1], self)

        embed = discord.Embed(
            title=f'{loser_crew.name}({loser_crew.abbr}) forfeits against {winner_crew.name}({winner_crew.abbr})',
            description=f''
        )
        msg = await ctx.send(f'{ctx.author.mention}: Are you sure you want to confirm this forfeit?', embed=embed)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return

        output_channels = [discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
                           discord.utils.get(ctx.guild.channels, name=OUTPUT)]
        links = []
        for output_channel in output_channels:
            files = [await attachment.to_file() for attachment in ctx.message.attachments]
            link = await output_channel.send(files=files)
            links.append(link)

        league_id = CURRENT_LEAGUE_ID
        battle_id = add_non_ss_battle(winner_crew, loser_crew, 0, 1, links[0].jump_url, league_id)
        winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k = battle_elo_changes(
            battle_id, forfeit=True)

        new_message = (
            f'**{today.strftime("%B %d, %Y")} (Trinity League) - {winner_crew.name} ({winner_crew.abbr})⚔'
            f'{loser_crew.name} ({loser_crew.abbr})**\n'
            f'**Winner:** <@&{winner_crew.role_id}> [{winner_elo} '
            f'+ {winner_change} = {winner_elo + winner_change}]'
            f'** Destiny**: [+{d_winner_change}->{d_final}]\n'
            f'**Loser:** <@&{loser_crew.role_id}> [{loser_elo} '
            f'- {abs(loser_change)} = {loser_elo + loser_change}] \n'
            f'**Battle:** {battle_id} from {ctx.channel.mention}')
        for link in links:
            await link.edit(content=new_message)
        await ctx.send(
            f'{loser_crew.name}\'s forfeit to {winner_crew.name}'
            f'has been confirmed and posted in {output_channels[0].mention}. '
            f'(Battle number:{battle_id})')

    @commands.command(**help_doc['addsheet'])
    @main_only
    @role_call(STAFF_LIST)
    async def addsheet(self, ctx: Context, *, everything: str):

        if not ctx.message.attachments:
            await response_message(ctx, 'You need to submit a screenshot of the scoresheet with this.')
            return

        everything = everything.split(' ')
        try:
            score = int(everything[-1])
            players = int(everything[-2])
        except ValueError:
            await response_message(ctx,
                                   'This command needs to be formatted like this `,addsheet WinningCrew LosingCrew '
                                   'Size FinalScore`')
            return
        # TODO split by triforce
        two_crews = ' '.join(everything[:-2])
        best = best_of_possibilities(two_crews, self, True)

        winner_crew = crew_lookup(best[0], self)
        loser_crew = crew_lookup(best[1], self)

        embed = discord.Embed(
            title=f'{winner_crew.name}({winner_crew.abbr}) defeats {loser_crew.name}({loser_crew.abbr})',
            description=f'{winner_crew.name} wins {score} - 0 in a {players} vs {players} battle'
        )
        msg = await ctx.send(f'{ctx.author.mention}: Are you sure you want to confirm this crew battle?', embed=embed)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return

        output_channels = [discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
                           discord.utils.get(ctx.guild.channels, name=OUTPUT)]
        links = []
        for output_channel in output_channels:
            files = [await attachment.to_file() for attachment in ctx.message.attachments]
            link = await output_channel.send(files=files)
            links.append(link)

        league_id = CURRENT_LEAGUE_ID
        battle_id = add_non_ss_battle(winner_crew, loser_crew, players, score, links[0].jump_url, league_id)

        today = date.today()

        winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k = battle_elo_changes(
            battle_id)
        w_placement = (200 - winner_k) / 30 + 1
        l_placement = (200 - loser_k) / 30 + 1
        if w_placement < 6:
            w_placement_message = f'Placement round {int(w_placement)}'
            differential = winner_k / 50
            winner_k_message = f'({winner_change // differential}* {differential})'
        else:
            w_placement_message = ''
            winner_k_message = winner_change
        if l_placement < 6:
            l_placement_message = f'Placement round {int(l_placement)}'
            differential = loser_k / 50
            loser_k_message = f'({loser_change // differential}* {differential})'
        else:
            l_placement_message = ''
            loser_k_message = loser_change
        battle_name = 'Triforce of Wisdom'
        new_message = (
            f'**{today.strftime("%B %d, %Y")} ({battle_name}) - {winner_crew.name} ({winner_crew.abbr})⚔'
            f'{loser_crew.name} ({loser_crew.abbr})**\n'
            f'**Winner:** <@&{winner_crew.role_id}> [{winner_elo} '
            f'+ {winner_change} = {winner_elo + winner_change}]'
            f'**Loser:** <@&{loser_crew.role_id}> [{loser_elo} '
            f'- {abs(loser_change)} = {loser_elo + loser_change}] \n'
            f'**Battle:** {battle_id} from {ctx.channel.mention}')
        for link in links:
            await link.edit(content=new_message)
        await ctx.send(
            f'The battle between {winner_crew.name}({w_placement_message}) and {loser_crew.name}({l_placement_message}) '
            f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
            f'(Battle number:{battle_id})')
        for cr in (winner_crew, loser_crew):
            if not extra_slot_used(cr):
                if battles_since_sunday(cr) >= 3:
                    mod_slot(cr, 1)
                    await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')
                    set_extra_used(cr)

    #
    #     elif current.battle_type in (BattleType.POWER, BattleType.COURAGE):
    #     current.confirm(await self._battle_crew(ctx, ctx.author))
    #     await send_sheet(ctx, battle=current)
    #     if current.confirmed():
    #         today = date.today()
    #         if current.battle_type == BattleType.POWER:
    #             name = 'Triforce of Power'
    #             league_id = 22
    #             channel_id = POWER_CHANNEL_ID
    #         else:
    #             name = 'Triforce of Courage'
    #             league_id = 21
    #             channel_id = COURAGE_CHANNEL_ID
    #         output_channels = [
    #             discord.utils.get(ctx.guild.channels, id=channel_id),
    #             discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
    #             discord.utils.get(ctx.guild.channels, name=OUTPUT)]
    #         winner = current.winner().name
    #         loser = current.loser().name
    #         current = self._current(ctx)
    #         if not current:
    #             return
    #         await self._clear_current(ctx)
    #         links = []
    #         for output_channel in output_channels:
    #             link = await send_sheet(output_channel, current)
    #             links.append(link)
    #         battle_id = add_finished_battle(current, links[0].jump_url, league_id)
    #         battle_weight_changes(battle_id)
    #         winner_crew = crew_lookup(winner, self)
    #         loser_crew = crew_lookup(loser, self)
    #         new_message = (
    #             f'**{today.strftime("%B %d, %Y")} ({name}) - {winner}⚔{loser}**\n'
    #             f'**Winner:** <@&{winner_crew.role_id}> ({winner_crew.abbr}) '
    #             f'**Loser:** <@&{loser_crew.role_id}> ({loser_crew.abbr}) \n'
    #             f'**Battle:** {battle_id} from {ctx.channel.mention}')
    #         for link in links:
    #             await link.edit(content=new_message)
    #         await ctx.send(
    #             f'The battle between {current.team1.name} and {current.team2.name} '
    #             f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
    #             f'(Battle number:{battle_id})')
    #
    #         await links[0].add_reaction(YES)
    #         for cr in (winner_crew, loser_crew):
    #             if not extra_slot_used(cr):
    #                 if battles_since_sunday(cr) >= 3:
    #                     mod_slot(cr, 1)
    #                     await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')
    #                     set_extra_used(cr)
    #
    # else:

    @commands.command(**help_doc['failedreg'])
    @main_only
    @role_call(STAFF_LIST)
    async def failedreg(self, ctx: Context, *, everything: str):
        today = date.today()

        if not ctx.message.attachments:
            await response_message(ctx, 'You need to submit a screenshot of the scoresheet with this.')
            return

        everything = everything.split(' ')

        try:
            score = int(everything[-1])
            players = int(everything[-2])
        except ValueError:
            await response_message(ctx,
                                   'This command needs to be formatted like this `,addsheet WinningCrew LosingCrew'
                                   'Size FinalScore`')
            return
        two_crews = ' '.join(everything[:-2])
        best = single_crew_plus_string(two_crews, self)

        winner_crew = crew_lookup(best[0], self)
        loser_crew = best[1]

        embed = discord.Embed(
            title=f'{winner_crew.name}({winner_crew.abbr}) defeats {loser_crew} in a failed registration battle',
            description=f'{winner_crew.name} wins {score} - 0 in a {players} vs {players} battle'
        )
        msg = await ctx.send(f'{ctx.author.mention}: Are you sure you want to confirm this crew battle?', embed=embed)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return

        output_channels = [discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
                           discord.utils.get(ctx.guild.channels, name=OUTPUT)]
        links = []
        for output_channel in output_channels:
            files = [await attachment.to_file() for attachment in ctx.message.attachments]
            link = await output_channel.send(files=files)
            links.append(link)

        league_id = CURRENT_LEAGUE_ID
        battle_id = add_failed_reg_battle(winner_crew, players, score, links[0].jump_url, league_id)
        reset_fake_crew_rating(league_id)
        winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k = battle_elo_changes(
            battle_id)
        w_placement = (200 - winner_k) / 30 + 1
        l_placement = (200 - winner_k) / 30 + 1
        if w_placement < 6:
            w_placement_message = f'Placement round {int(w_placement)}'
            differential = winner_k / 50
            winner_k_message = f'({winner_change // differential}* {differential})'
        else:
            w_placement_message = ''
            winner_k_message = winner_change

        battle_name = 'Triforce of Wisdom - Failed Registration'
        new_message = (
            f'**{today.strftime("%B %d, %Y")} ({battle_name}) - {winner_crew.name} ({winner_crew.abbr})⚔'
            f'{loser_crew} (Failed Reg Crew)**\n'
            f'**Winner:** <@&{winner_crew.role_id}> [{winner_elo} '
            f'+ {winner_change} = {winner_elo + winner_change}] \n'
            f'**Loser:** <@&{loser_crew.role_id}> [{loser_elo} '
            f'- {abs(loser_change)} = {loser_elo + loser_change}] \n'
            f'**Battle:** {battle_id} from {ctx.channel.mention}')
        for link in links:
            await link.edit(content=new_message)
        await ctx.send(
            f'The battle between {winner_crew.name}({w_placement_message}) and {loser_crew}(Failed Reg Crew) '
            f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
            f'(Battle number:{battle_id})')
        if not extra_slot_used(winner_crew):
            if battles_since_sunday(winner_crew) >= 3:
                mod_slot(winner_crew, 1)
                await ctx.send(f'{winner_crew.name} got a slot back for playing 3 battles this week!')
                set_extra_used(winner_crew)

    @commands.command(**help_doc['weirdreg'])
    @main_only
    @role_call(STAFF_LIST)
    async def weirdreg(self, ctx: Context, *, everything: str):
        today = date.today()

        if not ctx.message.attachments:
            await response_message(ctx, 'You need to submit a screenshot of the scoresheet with this.')
            return

        everything = everything.split(' ')

        try:
            score = int(everything[-1])
            players = int(everything[-2])
        except ValueError:
            await response_message(ctx,
                                   'This command needs to be formatted like this `,addsheet LosingCrew WinningRegCrew'
                                   'Size FinalScore`')
            return
        two_crews = ' '.join(everything[:-2])
        best = single_crew_plus_string(two_crews, self)

        loser_crew = crew_lookup(best[0], self)
        winner_crew = best[1]

        embed = discord.Embed(
            title=f'{winner_crew} defeats {loser_crew.name}({loser_crew.abbr}) in a failed registration battle',
            description=f'{winner_crew} wins {score} - 0 in a {players} vs {players} battle'
        )
        msg = await ctx.send(f'{ctx.author.mention}: Are you sure you want to confirm this crew battle?', embed=embed)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot, 120):
            await response_message(ctx, 'Canceled or timed out.')
            return

        output_channels = [discord.utils.get(ctx.guild.channels, name=SCORESHEET_HISTORY),
                           discord.utils.get(ctx.guild.channels, name=OUTPUT)]
        links = []
        for output_channel in output_channels:
            files = [await attachment.to_file() for attachment in ctx.message.attachments]
            link = await output_channel.send(files=files)
            links.append(link)
        league_id = CURRENT_LEAGUE_ID
        battle_id = add_weird_reg_battle(loser_crew, players, score, links[0].jump_url, league_id)
        reset_fake_crew_rating(league_id)

        winner_elo, winner_change, loser_elo, loser_change, d_winner_change, d_final, winner_k, loser_k = battle_elo_changes(
            battle_id)
        w_placement = (200 - winner_k) / 30 + 1
        l_placement = (200 - winner_k) / 30 + 1
        if w_placement < 6:
            w_placement_message = f'Placement round {int(w_placement)}'
            differential = winner_k / 50
            winner_k_message = f'({winner_change // differential}* {differential})'
        else:
            w_placement_message = ''
            winner_k_message = winner_change
        if l_placement < 6:
            l_placement_message = f'Placement round {int(l_placement)}'
            differential = loser_k / 50
            loser_k_message = f'({loser_change // differential}* {differential})'
        else:
            l_placement_message = ''
            loser_k_message = loser_change

        new_message = (
            f'**{today.strftime("%B %d, %Y")} (Trinity League) - {winner_crew}⚔'
            f'{loser_crew.name} ({loser_crew.abbr})**\n'
            f'**Winner:** {winner_crew} \n'
            f'**Loser:** <@&{loser_crew.role_id}> [{loser_elo} '
            f'- {abs(loser_change)} = {loser_elo + loser_change}] \n'
            f'**Battle:** {battle_id} from {ctx.channel.mention}')
        for link in links:
            await link.edit(content=new_message)
        await ctx.send(
            f'The battle between {winner_crew} and {loser_crew.name}({l_placement_message}) '
            f'has been confirmed by both sides and posted in {output_channels[0].mention}. '
            f'(Battle number:{battle_id})')
        for cr in (loser_crew,):
            if not extra_slot_used(cr):
                if battles_since_sunday(cr) >= 3:
                    mod_slot(cr, 1)
                    await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')
                    set_extra_used(cr)

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
        await send_long_embed(ctx, battle_summary(self))

    @commands.command(**help_doc['register'])
    @main_only
    @role_call(STAFF_LIST)
    @flairing_required
    async def register(self, ctx: Context, members: Greedy[discord.Member], *, new_crew: str = None):

        await self.cache.update(self)
        success = []
        fail_not_overflow = []
        fail_on_crew = []
        if not new_crew and members:
            await ctx.send(f'{members[-1].mention} is breaking register, try using the full name of the crew.')
            return
        flairing_crew = crew_lookup(new_crew, self)
        if not flairing_crew.db_id:
            flairing_crew.db_id = id_from_crew(flairing_crew)
            if not flairing_crew.db_id:
                await ctx.send(f'{flairing_crew.name} does not have a database id set for some reason. Please make sure'
                               f'everything has been properly set up, including role and docs then recache.')
                return

        msg = await ctx.send(f'Are you sure you want to register {len(members)} members for {flairing_crew.name}')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
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
        init_rating(flairing_crew, 1500, 200)

        embed = discord.Embed(title=f'Crew Reg for {flairing_crew.name}', description='\n'.join(desc),
                              color=flairing_crew.color)

        await send_long_embed(ctx, embed)
        await send_long_embed(self.cache.channels.flair_log, embed)

    @commands.command(**help_doc['fixslot'], hidden=True)
    @role_call(STAFF_LIST)
    async def fixslot(self, ctx, *, name: str = None):
        if name:
            cr = crew_lookup(name, self)
        else:
            await ctx.send('You must send in a crew name.')
            return
        message = f'{ctx.author.mention}: You are attempting to give {cr.name}, a slot for playing 3 cbs' \
                  f' are you sure?'
        msg = await ctx.send(message)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            return
        mod_slot(cr, 1)
        await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')

    @commands.command(**help_doc['freeze'])
    @role_call([DOCS, MINION, ADMIN, VIOS])
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
            await member.remove_roles(self.cache.roles.advisor, self.cache.roles.leader, self.cache.roles.poach_me,
                                      reason=f'Unflaired in disband by {ctx.author.name}')

        await cr_role.delete(reason=f'disbanded by {ctx.author.name}')
        response_embed = discord.Embed(title=f'{dis_crew.name} has been disbanded',
                                       description='\n'.join(
                                           [f'{mem.mention}, {mem.id}, {str(mem)}' for mem in members]),
                                       color=dis_crew.color)

        disband_crew(dis_crew)
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

    @commands.command(**help_doc['recache'], hidden=True, aliases=['rc'])
    @role_call(STAFF_LIST)
    async def recache(self, ctx: Context):
        await self._cache_process()
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

    @commands.command(**help_doc['stagelist'])
    async def stagelist(self, ctx: Context):
        await ctx.send(
            'https://media.discordapp.net/attachments/906245865386160229/1102303503558385714/SCSStagelist2023.png')

    @commands.command(**help_doc['invite'])
    async def invite(self, ctx: Context):
        await ctx.send('https://smashcrewserver.com')

    @commands.command(**help_doc['records'])
    async def records(self, ctx: Context):
        await ctx.send('https://elo.smashcrewserver.com')

    @commands.command(**help_doc['thank'])
    @banned_channels(['crew_flairing', 'scs_docs_updates'])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def thank(self, ctx: Context):

        await ctx.send(f'Thanks for all the hard work you do on the bot alexjett!\n'
                       f'{add_thanks(ctx.author)} \n(If you want to thank him with money you can do so here. '
                       f'https://www.buymeacoffee.com/alexjett)')

    @commands.command(**help_doc['thankboard'])
    @banned_channels(['crew_flairing', 'scs_docs_updates'])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def thankboard(self, ctx: Context):

        await ctx.send(embed=thank_board(ctx.author))

    @commands.command(**help_doc['coin'])
    async def coin(self, ctx: Context, member: discord.Member = None):

        flip = bool(random.getrandbits(1))
        if member:
            msg = await ctx.send(f'{ctx.author.display_name} has asked you to call a coin {member.mention} '
                                 f'what do you choose'
                                 f'({YES} for heads {NO} for tails?)')
            choice = await wait_for_reaction_on_message(YES, NO, msg, member, self.bot, 60)
            choice_name = 'heads' if choice else 'tails'
            if choice == flip:
                await ctx.send(f'{member.display_name} chose {choice_name} and won the flip!')
            else:
                await ctx.send(f'{member.display_name} chose {choice_name} and lost the flip!')
        res = 'heads' if flip else 'tails'
        await ctx.send(f'Your coin flip landed on {res}', file=discord.File(f'./src/img/{res}.png'))

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
        actual, mems, extra = members_with_str_role(role, self)
        mems.sort(key=lambda x: str(x))
        if 'everyone' in actual:
            await ctx.send('I will literally ban you if you try this again.')
            return
        if len(mems) > 150:
            await ctx.send(f'{actual} is too large of a role, use `.listroles`.')
            return
        desc = ['\n'.join([f'{str(member)} {member.mention}' for member in mems])]
        if extra:
            desc.append('These members are flaired for the crew, but not in the server')
            desc.extend(['\n'.join([f'{name_from_id(mem_id)}: {str(mem_id)}' for mem_id in extra])])
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

    @commands.command(**help_doc['listroles'])
    async def roster(self, ctx, *, role: str = ''):
        if role:
            ambiguous = ambiguous_lookup(role, self)
            if isinstance(ambiguous, discord.Member):
                actual_crew = crew_lookup(crew(ambiguous, self), self)
            else:
                actual_crew = ambiguous
        else:
            actual_crew = crew_lookup(crew(ctx.author, self), self)

        actual, mems, extra = members_with_str_role(actual_crew.name, self)
        mems.sort(key=lambda x: str(x))
        mems = [member for member in mems if self.cache.roles.fortyman in member.roles]
        desc = ['\n'.join([f'{str(member)} {member.mention}' for member in mems])]
        cr = crew_lookup(actual, self)
        title = f'All {len(mems)} members on the roster for {actual}'
        color = cr.color

        out = discord.Embed(title=title,
                            description='\n'.join(desc), color=color)
        await send_long_embed(ctx, out)

    @commands.command(**help_doc['pingrole'])
    @role_call(STAFF_LIST)
    async def pingrole(self, ctx, *, role: str):
        actual, mems, _ = members_with_str_role(role, self)
        out = [f'Pinging all members of role {actual}: ']
        for mem in mems:
            out.append(mem.mention)
        await ctx.send(''.join(out))

    @commands.command(**help_doc['vote'])
    @role_call([LEADER])
    async def vote(self, ctx, option: int):
        options = ('', 'Keep slot system unchanged',
                   'Keep slot system, but add a modifier where low ranked crews get additional slots (scaled by rank)',
                   'Keep slot system, but change it so 2 unflairs is a returned slot rather than 3',
                   'Remove slots, reimplement old merge rules (this option is no longer valid)')
        cr = crew_lookup(crew(ctx.author, self), self)
        current_vote = get_crew_vote(cr)
        if current_vote:
            msg = await ctx.send(f'Your crew {cr.name} has already voted for \n```{options[current_vote[1]]} ```\n '
                                 f'made by {current_vote[2]}. Would you like to overwrite this?')
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!', delete_after=5)
                await ctx.message.delete()
                await msg.delete()
                return
            await msg.delete()
        else:
            await response_message(ctx, 'Only crews that voted in the first vote are allowed to revote. '
                                        f'Your crew {cr.name} did not.')
            return
        if not (0 < option < 4):
            await response_message(ctx, 'You must input a number between 1 and 3')
            return

        msg = await ctx.send(f'Your crew {cr.name} selected \n```{options[option]} ```\n '
                             f'made by {ctx.author.mention}. Please confirm')
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!', delete_after=5)
            await ctx.message.delete()
            await msg.delete()
            return
        await ctx.send(f'{ctx.author.mention}: Confirmed your above choice.', delete_after=5)

        await msg.delete()
        await ctx.message.delete()
        set_crew_vote(cr, option, ctx.author.id)

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
        if len(mems) > 100:
            await ctx.send(f'This is over 100 members, file outputs will be implemented soon.')
            return
        out = f'Overlap between {best[0]} and {best[1]}:\n' + ', '.join([escape(str(mem)) for mem in mems])

        await send_long(ctx, out, ',')

    @commands.command(**help_doc['noverlap'])
    async def noverlap(self, ctx, *, two_roles: str = None):
        if 'everyone' in two_roles:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        best = best_of_possibilities(two_roles, self)
        mems = noverlap_members(best[0], best[1], self)
        if 'everyone' in best[0] or 'everyone' in best[1]:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        if len(mems) > 100:
            await ctx.send(f'This is over 100 members, file outputs will be implemented soon.')
            return
        out = f'Members that have {best[0]} but not {best[1]}:\n' + ', '.join([escape(str(mem)) for mem in mems])

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

    @commands.command(hidden=True, **help_doc['pingoverlap'])
    @role_call(STAFF_LIST)
    async def pingnoverlap(self, ctx, *, two_roles: str = None):
        if 'everyone' in two_roles:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        best = best_of_possibilities(two_roles, self)
        mems = noverlap_members(best[0], best[1], self)

        if 'everyone' in best[0] or 'everyone' in best[1]:
            await ctx.send(f'{ctx.author.mention}: do not use this command with everyone. Use `,listroles`.')
            return
        if len(mems) > 10:
            resp = f'You are attempting to ping all {best[0]} bot not {best[1]} this ' \
                   f'is {len(mems)} members, are you sure?'
            msg = await ctx.send(resp)
            if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
                await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
                return

        out = f'Members that have {best[0]} but not {best[1]}:\n' + ', '.join([mem.mention for mem in mems])

        await send_long(ctx, out, ',')

    @commands.command(hidden=True, **help_doc['bigcrew'])
    @role_call(STAFF_LIST)
    async def bigcrew(self, ctx, over: Optional[int] = 40):
        big = []
        for cr in self.cache.crews_by_name.values():
            if cr.member_count >= over:
                big.append(cr)
        desc = []
        thing = ''
        for cr in big:
            thing += f'{cr.db_id}, '
            desc.append(f'{cr.name}: {cr.member_count}')
        print(thing)
        embed = discord.Embed(title=f'These Crews have {over} members or more', description='\n'.join(desc))
        await send_long_embed(ctx, embed)

    @commands.command(hidden=True, **help_doc['softcap'])
    async def softcap(self, ctx, cr: Optional[str] = ''):
        if not cr:
            if not check_roles(ctx.author, STAFF_LIST):
                cr = crew(ctx.author, self)
        if cr:
            actual = crew_lookup(cr, self)
            if datetime.now().month == 1:
                usage = crew_usage_jan(actual, 1)
            else:
                usage = crew_usage(actual, 1)
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
            await send_long_embed(ctx.author, embed)
            usage = crew_usage(actual, 0)
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
            embed = discord.Embed(title=f'Usage of each member of {actual.name} from this month ({len(usage)} total)',
                                  description='\n'.join(desc), color=discord.Color.random())
            await send_long_embed(ctx.author, embed)
            await ctx.message.add_reaction(emoji='✉')
        else:
            if datetime.now().month == 1:
                usage = all_crew_usage_jan(1)
            else:
                usage = all_crew_usage(1)
            desc = []
            for number, name, _ in usage:
                desc.append(f'{name}: {number}')
            embed = discord.Embed(title='Number of unique players in cbs last month by each crew',
                                  description='\n'.join(desc), color=discord.Color.random())
            await send_long_embed(ctx.author, embed)
            usage = all_crew_usage()
            desc = []
            for number, name, _ in usage:
                desc.append(f'{name}: {number}')
            embed = discord.Embed(title='Number of unique players in cbs this month by each crew',
                                  description='\n'.join(desc), color=discord.Color.random())
            await send_long_embed(ctx.author, embed)
            await ctx.message.add_reaction(emoji='✉')

    @commands.command(hidden=True, **help_doc['crnumbers'])
    @role_call(STAFF_LIST)
    async def rate(self, ctx):
        # everyone = get_all_predictions()
        # actual = everyone['Predictor']
        # count = -1
        # for member in everyone:
        #     correct = True
        #     for match in actual:
        #
        #         if actual[match] != everyone[member][match]:
        #             correct = False
        #             break
        #     if correct:
        #         print(member)
        #         count += 1
        # print(count)

        bracket_crews = playoff_crews(self)
        br = Bracket(bracket_crews, ctx.author)
        predictions = get_bracket_predictions(420)
        for prediction in predictions:
            br.report_winner(prediction[0])
        await ctx.send(file=draw_bracket(br.matches))
        # await channel.send(everything)
        # await ctx.message.delete(delay=5)
        # crew_names = ['Black Halo', 'Valerian', 'Arpeggio', 'Dream Casters', 'Holy Knights', 'No Style',
        #               'EVA^', 'Midnight Sun', 'Phantom Troupe', 'Sound of Perfervid', 'Flow State Gaming',
        #               'Wombo Combo', 'Black Gang', 'Phantasm', 'Down B Queens', 'Lazarus']
        # bracket_crews = [crew_lookup(cr, self) for cr in crew_names]
        # await ctx.message.add_reaction(emoji='✉')
        # await ctx.message.delete(delay=5)
        # await ctx.author.send('Please answer both of the following to completion! You can check your predictions after'
        #                       ' with `,predictions` or modify your predictions by using `,predict` again.')
        # await ctx.author.send('Bracket choosing', view=Bracket(bracket_crews, ctx.author))
        # await ctx.author.send('Extra questions! (10 points each)', view=Questions(ctx.author))
        # for cr in self.cache.crews_by_name.values():
        #     if not extra_slot_used(cr):
        #         if battles_since_sunday(cr) >= 3:
        #             mod_slot(cr, 1)
        #             await ctx.send(f'{cr.name} got a slot back for playing 3 battles this week!')
        #             set_extra_used(cr)
        # await track_handle(self)
        # track_down_out(382324766851465216)
        # crew_msg = {}
        pass
        # for cr in all_votes():
        #     msg = f'Voting on slots modifier is now active, you can change your vote if you choose ' \
        #           f'or you can do nothing and keep your previous vote. ' \
        #           f'This is available to you since your crew {cr} voted in the first one. ' \
        #           f'See <#852278918274482206> for details.'
        #     crew_msg[cr] = msg
        # for i, member in enumerate(self.cache.scs.members):
        #     if i % 100 == 0:
        #         print(f'{i}/{len(self.cache.scs.members)} pt 2')
        #     if self.cache.roles.leader in member.roles:
        #         msg = ''
        #         try:
        #             cr = crew(member, self)
        #             if cr in crew_msg:
        #                 msg = crew_msg[cr]
        #         except ValueError:
        #             await ctx.send(f'{str(member)} is a leader with no crew.')
        #         if msg:
        #             try:
        #                 await member.send(msg)
        #             except discord.errors.Forbidden:
        #                 await ctx.send(f'{str(member)} is not accepting dms.')
        # in_server, out_server = members_in_server()
        # final_in: List[int] = []
        # for i, mem in enumerate(self.cache.scs.members):
        #     if mem.id in in_server:
        #         in_server.remove(mem.id)
        #     else:
        #         final_in.append(mem.id)
        #     print(i, len(self.cache.scs.members))
        #     if i < 12500:
        #         continue
        #     update_member_roles(mem)
        #
        # update_member_status(tuple(final_in), tuple(in_server))

    @commands.command(hidden=True, **help_doc['crnumbers'])
    @role_call(STAFF_LIST)
    async def dele(self, ctx):
        await clear_current_cbs(self)
        for battle_type in BattleType:
            summary = battle_summary(self, battle_type)
            if summary:
                await send_long_embed(self.cache.channels.current_cbs, summary)

    @commands.command(hidden=True, **help_doc['crnumbers'])
    @role_call(STAFF_LIST)
    async def categoryrole(self, ctx, member: discord.Member):
        # for i, member in (enumerate(ctx.guild.members)):
        #     print(i + 1, len(ctx.guild.members))

        await set_categories(member, self.cache.categories)

    @commands.command(hidden=True, **help_doc['cancelcb'])
    @role_call(STAFF_LIST)
    async def cancelcb(self, ctx, battle_id: int, *, reason: str = ''):
        crew1, crew2, finished, link = battle_info(battle_id)
        embed = discord.Embed(title='Are you sure you want to cancel this crew battle?',
                              description=f'{crew1} vs {crew2}\n'
                                          f'On: {finished} [link]({link})', color=discord.Color.random())
        msg = await ctx.send(embed=embed)
        if not await wait_for_reaction_on_message(YES, NO, msg, ctx.author, self.bot):
            resp = await ctx.send(f'{ctx.author.mention}: {ctx.command.name} canceled or timed out!')
            await ctx.message.delete(delay=5)
            await msg.delete(delay=2)
            await resp.delete(delay=5)
            return
        link = battle_cancel(battle_id)
        split = link.split('/')
        channel_id = int(split[-2])
        message_id = int(split[-1])
        channel = ctx.guild.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        await message.edit(content=f'{NO}Canceled by {ctx.author} {reason}\n' + message.content)

        await ctx.send(f'Successfully canceled cb {battle_id}.')

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

    @commands.command(hidden=True, **help_doc['crnumbers'])
    @role_call(STAFF_LIST)
    async def stupid(self, ctx):
        # await handle_decay(self)
        for battle in all_battle_ids():
            print(battle)
            battle_weight_changes(battle[0], season=True)
        # message = []
        # for cr in self.cache.crews_by_name.values():
        #     filled = 25 if cr.current_umbra >= cr.max_umbra else 0
        #     rating = 1425 + 75 * cr.rank + filled
        #     if cr.abbr == 'SG':
        #         rating += 51
        #     message.append(f'{cr.name}: rank:{cr.rank} meter{cr.current_umbra}/{cr.max_umbra} -> {rating}')
        #     init_rating(cr, rating, 200)
        #
        # await send_long(ctx, '\n'.join(message), '\n')
        #
        # update_destiny_sheet()

    # Deprecated
    # @commands.command(hidden=True, **help_doc['ofrank'])
    # @role_call(STAFF_LIST)
    # async def ofrank(self, ctx):
    #     crews = list(self.cache.crews_by_name.values())
    #
    #     crews.sort(key=lambda x: x.scl_rating)
    #     desc = []
    #     for cr in crews:
    #         if cr.overflow:
    #             desc.append(
    #                 f'{cr.name}: Rank {cr.scl_rating}, members, {cr.member_count} {str(first_crew_flair(cr))}')
    #     embed = discord.Embed(title=f'Overflow crew numbers', description='\n'.join(desc))
    #
    #     await send_long_embed(ctx, embed)

    @commands.command(hidden=True, **help_doc['ofrank'])
    @role_call(STAFF_LIST)
    async def initalize_ratings(self, ctx):
        start = 1500
        current = 0
        for cid in crews_by_rating():
            current += 1
            if current > 20:
                current = 0
                start += 50
            init_crew_rating(cid, start, 20)
            print(cid, start)
        # TODO set new elo for wisdom

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

    @commands.command(**help_doc['slots'])
    @role_call(STAFF_LIST)
    @main_only
    async def update_elos(self, ctx, *, name: str = None):
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
        for i, cr in enumerate(crews):
            print(f'{i}/{len(crews)} pt 1')
            if cr.member_count == 0:
                continue
            total, base, modifer, rollover = calc_total_slots(cr)
            left, cur_total = slots(cr)
            desc.append(f'{cr.name}: This month({left}/{cur_total}) ({cr.member_count} members) \n'
                        f'Next month {total} slots: {base} base + {modifer} size mod + {rollover} rollover.')

            # total_slot_set(cr, total)
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

    @commands.command(hidden=True, **help_doc['slottotals'])
    @role_call(STAFF_LIST)
    async def slotfinals(self, ctx):
        crews = list(self.cache.crews_by_name.values())
        desc = []
        crew_msg = {}
        for i, cr in enumerate(crews):
            print(f'{i}/{len(crews)} pt 1')
            if cr.member_count == 0:
                continue
            total, base, modifer, rollover = calc_total_slots(cr)
            left, cur_total = slots(cr)
            desc.append(f'{cr.name}: This month({left}/{cur_total}) \n'
                        f'Next month {total} slots: {base} base + {modifer} size mod  + {rollover} rollover.')

            total_slot_set(cr, total)
            message = f'{cr.name} has {total} flairing slots this month:\n' \
                      f'{base} base slots\n' \
                      f'{modifer} from size modifier\n' \
                      f'{rollover} rollover slots\n' \
                      'For more information, refer to <#430364791245111312>. ' \
                      'This bot will not be able to respond to any questions you have, so use <#786842350822490122>.'

            # if cr.member_count >= 40:
            #     softcap_set(cr, round(cr.member_count / 3))
            #     message += f'\nIn additon, because you have over 40 members, you will need have at least ' \
            #                f'{round(cr.member_count / 3)} unique members play in crew battles this month to avoid ' \
            #                f'being registration frozen.'
            crew_msg[cr.name] = message

        for i, member in enumerate(self.cache.scs.members):
            if i % 100 == 0:
                print(f'{i}/{len(self.cache.scs.members)} pt 2')
            if self.cache.roles.leader in member.roles:
                msg = ''
                try:
                    cr = crew(member, self)
                    msg = crew_msg[cr]
                except ValueError:
                    await ctx.send(f'{str(member)} is a leader with no crew.')
                if msg:
                    try:
                        await member.send(msg)
                    except discord.errors.Forbidden:
                        await ctx.send(f'{str(member)} is not accepting dms.')

        embed = discord.Embed(title=f'Crew total slots.', description='\n'.join(desc))
        await send_long_embed(ctx, embed)

    @commands.command(**help_doc['slots'])
    @role_call(STAFF_LIST)
    @main_only
    async def savenicks(self, ctx):
        members = ctx.guild.members
        tuples = []
        for i, mem in enumerate(members):
            tuples.append((mem.id, mem.display_name))
            print(f'{i + 1}/{len(members)}')
        record_nicknames(tuples)

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
