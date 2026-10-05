"""Parity tests for slash commands that are not hybrids: generated twins and typed front ends."""
import types
import unittest
import unittest.mock

from src.constants import *
from src.helpers import best_of_possibilities, crew_lookup, invocation_attachments, single_crew_plus_string
from src.slash import GROUPS, STAFF_GROUPS, parse_members
from tests import mocks
from tests.harness import (MODES, PREFIX, SLASH, FakeContext, FakeMessage, find_command, invoke, invoke_slash,
                           make_cog, no_external_services)

ROLE_A = types.SimpleNamespace(name='Leader')
ROLE_B = types.SimpleNamespace(name='Advisor')
SHOT = types.SimpleNamespace(filename='a.png')
SHOT2 = types.SimpleNamespace(filename='b.png')
OPPONENT = object()

# Slash options a user fills in -> the arguments the prefix command's callback must receive.
TYPED = {
    'bet': (dict(amount='50', crew='HK'), (), dict(everything='50 HK')),
    'end': (dict(char1='mario', stocks1=3, char2='fox', stocks2=1), ('mario', 3, 'fox', 1), {}),
    'endlag': (dict(char1='mario', stocks1=3, char2='fox', stocks2=1), ('mario', 3, 'fox', 1), {}),
    'multiunflair': (dict(members='<@1> <@2>'), (), dict(everything='<@1> <@2>')),
    'overlap': (dict(role1=ROLE_A, role2=ROLE_B), (), dict(two_roles='Leader Advisor')),
    'noverlap': (dict(role1=ROLE_A, role2=ROLE_B), (), dict(two_roles='Leader Advisor')),
    'pingoverlap': (dict(role1=ROLE_A, role2=ROLE_B), (), dict(two_roles='Leader Advisor')),
    'pingnoverlap': (dict(role1=ROLE_A, role2=ROLE_B), (), dict(two_roles='Leader Advisor')),
    'reg': (dict(crew_name='New Crew', size=5), (), dict(everything='New Crew 5')),
    'result': (dict(opponent=OPPONENT, your_characters='ness3 pika4', your_score=3, opponent_score=2,
                    opponent_characters='palu1'), (OPPONENT,), dict(everything='ness3 pika4 3 2 palu1')),
    'freeze': (dict(crew='HK', length='2W'), (), dict(everything='HK 2W')),
    'pair': (dict(crew1='HK', crew2='FSG'), (), dict(everything='HK FSG')),
    'addforfeit': (dict(winner='HK', loser='FSG', screenshot=SHOT), (),
                   dict(everything='HK FSG', attachments=[SHOT])),
    'addsheet': (dict(winner='HK', loser='FSG', players=5, score=2, screenshot=SHOT, screenshot2=SHOT2), (),
                 dict(everything='HK FSG 5 2', attachments=[SHOT, SHOT2])),
    'failedreg': (dict(winner='HK', registering_crew='New Crew', players=5, score=2, screenshot=SHOT), (),
                  dict(everything='HK New Crew 5 2', attachments=[SHOT])),
    'weirdreg': (dict(losing_crew='HK', registering_crew='New Crew', players=5, score=2, screenshot=SHOT), (),
                 dict(everything='HK New Crew 5 2', attachments=[SHOT])),
}
# Typed front ends covered by their own tests below rather than the table.
TYPED_ELSEWHERE = {'help', 'multiflair', 'register'}


class TypedFrontEndTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.author = mocks.MockMember(id=1, roles=[mocks.admin])
        self.guild = self.cog.cache.scs
        self.ctx = FakeContext(self.cog, self.author, mocks.MockTextChannel(id=5), self.guild, SLASH)

    async def run_typed(self, name, **options):
        with unittest.mock.patch.object(self.cog, 'run_slash', unittest.mock.AsyncMock()) as run:
            await self.cog.slash.by_prefix_name[name].callback(self.ctx.interaction, **options)
        return run

    def test_every_typed_front_end_is_tested(self):
        self.assertEqual(set(self.cog.slash.typed), set(TYPED) | TYPED_ELSEWHERE)

    async def test_options_are_passed_on_the_way_the_prefix_command_expects(self):
        for name, (options, args, kwargs) in TYPED.items():
            with self.subTest(command=name):
                run = await self.run_typed(name, **options)
                run.assert_awaited_once_with(self.ctx.interaction, name, *args, **kwargs)

    async def test_optional_options_can_be_left_out(self):
        run = await self.run_typed('freeze', crew='HK')
        run.assert_awaited_once_with(self.ctx.interaction, 'freeze', everything='HK')
        run = await self.run_typed('help')
        run.assert_awaited_once_with(self.ctx.interaction, 'help')
        run = await self.run_typed('help', command='send')
        run.assert_awaited_once_with(self.ctx.interaction, 'help', 'send')

    async def test_member_lists(self):
        self.ctx.interaction.guild = self.guild
        self.ctx.interaction.response.send_message = unittest.mock.AsyncMock()
        bob, joe = mocks.bob, mocks.joe
        text = f'<@{bob.id}> <@!{joe.id}>'
        run = await self.run_typed('multiflair', members=text, new_crew='HK')
        run.assert_awaited_once_with(self.ctx.interaction, 'multiflair', [bob, joe], 'HK')
        run = await self.run_typed('register', members=text, new_crew='HK')
        run.assert_awaited_once_with(self.ctx.interaction, 'register', [bob, joe], new_crew='HK')

        run = await self.run_typed('multiflair', members='nobody here')
        run.assert_not_awaited()
        self.assertTrue(self.ctx.interaction.response.send_message.await_args.kwargs['ephemeral'])

    def test_parse_members(self):
        bob, joe = mocks.bob, mocks.joe
        self.assertEqual([bob, joe], parse_members(self.guild, f'<@{bob.id}> {joe.id} <@{bob.id}>'))
        with self.assertRaisesRegex(ValueError, '999999999999999999'):
            parse_members(self.guild, '<@999999999999999999>')
        with self.assertRaisesRegex(ValueError, 'Mention each member'):
            parse_members(self.guild, 'bob joe')

    def test_crew_tags_resolve_exactly_in_the_prefix_parsers(self):
        """Crew suggestions fill in the tag, so what the front ends compose has to parse to those crews."""
        cog = self.cog
        self.assertEqual(['Holy Knights', 'FSGood'], best_of_possibilities('HK FSG', cog, True)[:2])
        self.assertEqual(['Ballers', 'Holy Knights'], best_of_possibilities('BAL HK', cog, True)[:2])
        self.assertEqual(['Holy Knights', 'New Crew'], single_crew_plus_string('HK New Crew', cog)[:2])
        self.assertEqual(mocks.FSGood, crew_lookup('FSG', cog))

    async def test_autocomplete(self):
        slash = self.cog.slash
        crews = await slash.crew_autocomplete(None, 'fs')
        self.assertEqual([('FSGood (FSG)', 'FSG')], [(c.name, c.value) for c in crews])
        self.assertEqual(3, len(await slash.crew_autocomplete(None, '')))
        characters = [c.value for c in await slash.character_autocomplete(None, 'pika')]
        self.assertEqual('pikachu', characters[0])
        self.assertLessEqual(len(await slash.character_autocomplete(None, '')), 25)
        names = [c.value for c in await slash.command_autocomplete(None, 'sen')]
        self.assertIn('send', names)
        self.assertNotIn('recache', [c.value for c in await slash.command_autocomplete(None, 'rec')])
        # Sections come first, and the old help categories are not suggested.
        self.assertEqual(['crew', 'crewstats'], [c.value for c in await slash.command_autocomplete(None, 'crew')])


class RunSlashTest(unittest.IsolatedAsyncioTestCase):
    """`run_slash` gives a slash front end everything the prefix command has."""

    def setUp(self):
        self.cog = make_cog()
        self.guild = self.cog.cache.scs
        self.channel = mocks.MockTextChannel(name='staff-chat', id=5, guild=self.guild)
        self.staff = mocks.MockMember(id=1, display_name='Staff', roles=[mocks.admin])
        self.player = mocks.MockMember(id=2, display_name='Player')

    def ctx(self, mode, author, attachments=()):
        return FakeContext(self.cog, author, self.channel, self.guild, mode, attachments)

    async def both(self, author, name, *args, patches=None, confirms=()):
        """Runs a command in each mode and returns what it sent in each."""
        sent = {}
        for mode in MODES:
            self.cog.cache.flairing_allowed = True
            ctx = self.ctx(mode, author)
            patched = dict(patches or {},
                           wait_for_reaction_on_message=unittest.mock.AsyncMock(side_effect=list(confirms)))
            with unittest.mock.patch.multiple('src.scoreSheetBot', **patched):
                await invoke(self.cog, name, ctx, *args)
            sent[mode] = ctx.sent
        return sent

    async def test_twin_does_what_the_prefix_command_does(self):
        cases = [
            ('flairing_off', (), {}, ()),
            ('flairing_on', (), {}, ()),
            ('disable', (self.channel,), dict(remove_disabled_channel=unittest.mock.MagicMock(),
                                               add_disabled_channel=unittest.mock.MagicMock()), (True,)),
            ('disable', (self.channel,), dict(add_disabled_channel=unittest.mock.MagicMock()), (False,)),
            ('charge', (self.player, 5), dict(member_gcoins=lambda member: 3), ()),
            ('charge', (self.player, 5, ), dict(member_gcoins=lambda member: 30, charge=lambda *a: 25), (True,)),
            ('sync', (), dict(sync_slash_commands=unittest.mock.AsyncMock(return_value=120)), ()),
        ]
        for name, args, patches, confirms in cases:
            with self.subTest(command=name, confirms=confirms):
                sent = await self.both(self.staff, name, *args, patches=patches, confirms=confirms)
                self.assertTrue(sent[PREFIX], 'the command should have answered')
                self.assertEqual(sent[PREFIX], sent[SLASH])

    async def test_twin_changes_state(self):
        ctx = self.ctx(SLASH, self.staff)
        await invoke(self.cog, 'flairing_off', ctx)
        self.assertFalse(self.cog.cache.flairing_allowed)

    async def test_guards_of_the_prefix_command_apply(self):
        sent = await self.both(self.player, 'flairing_off')
        self.assertEqual(sent[PREFIX], sent[SLASH])
        self.assertIn('You need to be one of', sent[SLASH][0]['content'])
        self.assertTrue(self.cog.cache.flairing_allowed, 'a refused command must not run')

    async def test_slash_front_end_is_deferred_and_counted_under_the_prefix_name(self):
        ctx = self.ctx(SLASH, self.staff)
        with unittest.mock.patch('src.scoreSheetBot.increment_command_used') as used, \
                unittest.mock.patch.dict('os.environ', {'VERSION': 'PROD'}):
            await invoke(self.cog, 'flairing_off', ctx)
        self.assertTrue(ctx.deferred)
        used.assert_called_once_with('flairing_off')

    async def test_a_silent_command_still_answers_a_slash_command(self):
        """Discord shows a slash command as running until it is answered, so one with nothing to say says so."""
        sent = await self.both(self.staff, 'season')
        self.assertEqual([], sent[PREFIX])
        self.assertEqual(['Done.'], [message['content'] for message in sent[SLASH]])
        sent = await self.both(self.staff, 'flairing_off')
        self.assertEqual(1, len(sent[SLASH]), 'a command that answered needs nothing more')

    async def test_deactivated_command_is_blocked(self):
        ctx = self.ctx(SLASH, self.staff)
        with unittest.mock.patch.object(self.cog, 'slash_context', unittest.mock.AsyncMock(return_value=ctx)), \
                no_external_services(), \
                unittest.mock.patch('src.scoreSheetBot.command_lookup', lambda name: (name, True)):
            await self.cog.run_slash(ctx.interaction, 'flairing_off')
        self.assertIn('flairing_off is deactivated', ctx.sent[0]['content'])
        self.assertTrue(self.cog.cache.flairing_allowed)

    async def test_errors_are_reported_like_prefix_errors(self):
        sent = await self.both(self.staff, 'charge', self.player, 5,
                               patches=dict(member_gcoins=unittest.mock.MagicMock(side_effect=ValueError('db down'))))
        self.assertEqual(sent[PREFIX], sent[SLASH])
        self.assertIn('charge failed because:db down', sent[SLASH][0]['content'])

    async def test_attachments(self):
        prefix = self.ctx(PREFIX, self.staff, attachments=[SHOT])
        self.assertEqual([SHOT], invocation_attachments(prefix))
        slash = self.ctx(SLASH, self.staff)
        self.assertEqual([], invocation_attachments(slash))
        with unittest.mock.patch.object(self.cog, 'slash_context', unittest.mock.AsyncMock(return_value=slash)), \
                no_external_services():
            await self.cog.run_slash(slash.interaction, 'flairing_off', attachments=[SHOT, SHOT2])
        self.assertEqual([SHOT, SHOT2], invocation_attachments(slash))

    async def test_a_sheet_without_a_screenshot_is_refused_in_both_modes(self):
        sent = {}
        for mode in MODES:
            ctx = self.ctx(mode, self.staff)
            if mode == PREFIX:
                await invoke(self.cog, 'addforfeit', ctx, everything='HK FSG')
            else:
                with unittest.mock.patch.object(self.cog, 'slash_context', unittest.mock.AsyncMock(return_value=ctx)), \
                        no_external_services():
                    await self.cog.run_slash(ctx.interaction, 'addforfeit', everything='HK FSG')
            sent[mode] = ctx.sent
        self.assertEqual(sent[PREFIX], sent[SLASH])
        self.assertIn('You need to submit a screenshot', sent[SLASH][0]['content'])

    async def test_typed_front_end_runs_the_prefix_command_end_to_end(self):
        """/staff battle addforfeit with crews picked by tag asks to confirm the same forfeit as the prefix form."""
        sent = {}
        for mode in MODES:
            ctx = self.ctx(mode, self.staff, attachments=[SHOT])
            with unittest.mock.patch('src.scoreSheetBot.wait_for_reaction_on_message',
                                     unittest.mock.AsyncMock(return_value=False)):
                if mode == PREFIX:
                    await invoke(self.cog, 'addforfeit', ctx, everything='Holy Knights FSGood')
                else:
                    await invoke_slash(self.cog, 'addforfeit', ctx, winner='HK', loser='FSG', screenshot=SHOT)
            sent[mode] = ctx.sent
        self.assertEqual(sent[PREFIX], sent[SLASH])
        self.assertIn('FSGood(FSG) forfeits against Holy Knights(HK)', sent[SLASH][0]['embed']['title'])


class HelpTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.cog.bot.walk_commands = self.cog.walk_commands
        self.author = mocks.bob
        self.author.send = unittest.mock.AsyncMock()

    async def ask(self, mode, *args):
        ctx = FakeContext(self.cog, self.author, mocks.MockTextChannel(id=5), self.cog.cache.scs, mode)
        self.author.send.reset_mock()
        if mode == PREFIX:
            await invoke(self.cog, 'help', ctx, *args)
        else:
            await invoke_slash(self.cog, 'help', ctx, command=args[0] if args else None)
        return ctx

    async def test_prefix_help_is_sent_by_dm_and_slash_help_only_to_the_author(self):
        for args in ((), ('cb',), ('send',), ('crew info',), ('notacommand',)):
            with self.subTest(args=args):
                prefix = await self.ask(PREFIX, *args)
                dm = self.author.send.await_args.kwargs['embed'].to_dict()
                self.assertEqual([], prefix.sent)

                slash = await self.ask(SLASH, *args)
                self.author.send.assert_not_awaited()
                self.assertEqual(dm, slash.sent[0]['embed'])
                self.assertTrue(slash.ephemeral[0])

    async def help_embed(self, *args, staff=False):
        with unittest.mock.patch('src.scoreSheetBot.check_roles', return_value=staff):
            await self.ask(PREFIX, *args)
        return self.author.send.await_args.kwargs['embed'].to_dict()

    async def test_help_lists_the_slash_sections(self):
        fields = (await self.help_embed())['fields']
        self.assertEqual([f'/{section}' for section in GROUPS] + ['/help'], [f['name'] for f in fields])
        self.assertEqual([description for description, _ in GROUPS.values()], [f['value'] for f in fields[:-1]])
        self.assertIn('/staff', [f['name'] for f in (await self.help_embed(staff=True))['fields']])

    async def test_help_lists_the_commands_of_a_section_by_their_slash_names(self):
        for section, (_, names) in GROUPS.items():
            with self.subTest(section=section):
                listed = [f['name'] for f in (await self.help_embed(section, staff=True))['fields']]
                self.assertCountEqual([f'/{self.cog.slash.by_prefix_name[name].qualified_name}' for name in names],
                                      listed)
        self.assertNotIn('/crew po', [f['name'] for f in (await self.help_embed('crew'))['fields']])
        # The names of the old help categories still work.
        self.assertEqual(await self.help_embed('crew'), await self.help_embed('crews'))
        self.assertEqual(await self.help_embed('f'), await self.help_embed('flairing'))

    async def test_help_lists_staff_sections_for_staff_only(self):
        groups = (await self.help_embed('staff', staff=True))['fields']
        self.assertEqual([f'/staff {group}' for group in STAFF_GROUPS], [f['name'] for f in groups])
        for group, (_, names) in STAFF_GROUPS.items():
            with self.subTest(group=group):
                listed = [f['name'] for f in (await self.help_embed('staff', group, staff=True))['fields']]
                self.assertCountEqual([f'/staff {group} {name}' for name in names], listed)
        for args in (('staff',), ('staff', 'crew')):
            with unittest.mock.patch('src.scoreSheetBot.check_roles', return_value=False):
                await self.ask(PREFIX, *args)
            self.author.send.assert_awaited_once_with('That section is for staff.')

    async def test_help_for_a_command_shows_its_prefix_and_slash_forms(self):
        for args, title, slash in ((('send',), 'send', '/cb send'), (('cb', 'send'), 'send', '/cb send'),
                                   (('crew', 'info'), 'crew', '/crew info'),
                                   (('gamb', 'start'), 'gamb start', '/gambit start')):
            with self.subTest(args=args):
                embed = await self.help_embed(*args, staff=True)
                self.assertEqual(title, embed['title'])
                self.assertIn(f'`,{title} ', embed['description'])
                self.assertIn(f'`{slash}`', embed['description'])


if __name__ == '__main__':
    unittest.main()
