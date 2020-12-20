import unittest
from src.helpers import *
from tests import mocks


class HelpersTest(unittest.IsolatedAsyncioTestCase):
    def test_channel_from_key(self):
        test_key = 'aaaa|bbbbb'
        self.assertEqual(channel_from_key(test_key), 'bbbbb')

    def test_key_string(self):
        ctx = mocks.MockContext()
        epxected = str(ctx.guild) + '|' + str(ctx.channel)
        self.assertEqual(key_string(ctx), epxected)

    def test_escape(self):
        input_and_expected = [
            ('\\>`_*|', '\\\\\\>\\`\\_\\*\\|')
        ]

        for input_str, expected in input_and_expected:
            with self.subTest(input_str):
                self.assertEqual(expected, escape(input_str))

    def test_split_str(self):

        input_and_expected = [
            ('123456789', '\n', None),
            ('1 2 3 4 5 6 7 8 9', ' ', ['1 2 ', '3 4 ', '5 6 ', '7 8 9'])
        ]

        for input_str, separator, expected in input_and_expected:
            with self.subTest(input_str):
                if expected is None:
                    raised = False
                    try:
                        split_on_length_and_separator(input_str, 5, separator)
                    except ValueError:
                        raised = True
                    self.assertTrue(raised)
                else:
                    self.assertEqual(expected, split_on_length_and_separator(input_str, 5, separator))

    def test_split_ebmed(self):
        desc = '1\n2\n3\n4\n'
        sent = discord.Embed(color=discord.Color.red(), description=desc, title='Title')
        expected = [discord.Embed(color=discord.Color.red(), description=desc[:4], title='Title'),
                    discord.Embed(color=discord.Color.red(), description=desc[4:])]
        out = split_embed(sent, 5)
        for i in range(len(out)):
            self.assertEqual(out[i].colour, expected[i].colour)
            self.assertEqual(out[i].description, expected[i].description)
            self.assertEqual(out[i].title, expected[i].title)

    def test_usable_emoji(self):
        emoji = mocks.emoji_instance
        bot = mocks.MockBot(emojis=[emoji])

        self.assertTrue(is_usable_emoji(f'<:{emoji.name}:{emoji.id}>', bot))

    def test_unusable_emoji(self):

        bot = mocks.MockBot(emojis=[mocks.emoji_instance])
        self.assertFalse(is_usable_emoji('<:fake:123>', bot))
        self.assertFalse(is_usable_emoji('bad', bot))

    def test_check_roles(self):
        member = mocks.MockMember()
        with self.subTest('None equal'):
            member.roles = [mocks.role_instance]
            self.assertFalse(check_roles(member, [mocks.leader_instance.name]))
        with self.subTest('One equal'):
            member.roles = [mocks.leader_instance, mocks.overflow_role_instance]
            self.assertTrue(check_roles(member, [mocks.leader_instance.name]))
        with self.subTest('Both equal'):
            member.roles = [mocks.overflow_role_instance, mocks.leader_instance]
            self.assertTrue(check_roles(member, [mocks.leader_instance.name, mocks.role_instance.name]))

    async def test_send_sheet(self):
        channel = mocks.MockTextChannel()
        battle = Battle('Team1', 'Team2', 5)
        await send_sheet(channel, battle)
        channel.send.assert_called_once()

    def test_crew(self):
        member = mocks.MockMember(name='John', id=1)
        hk = mocks.HK
        role = mocks.MockRole(name=hk.name)
        overflow_role = mocks.MockRole(name=OVERFLOW_ROLE)
        overflow_member = mocks.MockMember(name='John', id=1, roles=[mocks.overflow_role_instance])
        overflow_guild = mocks.MockGuild(members=[overflow_member], name=OVERFLOW_SERVER)
        bot = mocks.MockSSB(cache=mocks.fake_cache,
                            bot=mocks.MockBot(guilds=[overflow_guild]))
        bot.cache.overflow_server = overflow_guild
        with self.subTest('Not on a crew.'):
            member.roles = []
            with self.assertRaises(Exception):
                crew(member, bot)
        with self.subTest('On a crew.'):
            member.roles = [role]
            self.assertEqual(hk.name, crew(member, bot))
        with self.subTest('On overflow crew.'):
            member.roles = [overflow_role]
            self.assertEqual(mocks.Ballers.name, crew(member, bot))

    async def test_track_cycle(self):
        member = mocks.MockMember()
        scs = mocks.MockGuild(roles=mocks.tracks)
        with self.subTest('No track'):
            res = await track_cycle(member, scs)
            self.assertEqual(0, res)
            self.assertIn(mocks.track1, member.roles)

        with self.subTest('Track 1->2'):
            member.roles = [mocks.track1]
            res = await track_cycle(member, scs)
            self.assertEqual(1, res)
            self.assertIn(mocks.track2, member.roles)
            self.assertNotIn(mocks.track1, member.roles)

        with self.subTest('Track 2->3'):
            member.roles = [mocks.track2]
            res = await track_cycle(member, scs)
            self.assertEqual(2, res)
            self.assertIn(mocks.track3, member.roles)
            self.assertNotIn(mocks.track2, member.roles)

        with self.subTest('Track 3'):
            member.roles = [mocks.track3]
            res = await track_cycle(member, scs)
            self.assertEqual(3, res)

        with self.subTest('full'):
            member.roles = [mocks.true_locked]
            res = await track_cycle(member, scs)
            self.assertEqual(3, res)

    def test_power_level(self):
        member = mocks.MockMember()
        with self.subTest('No power'):
            self.assertEqual(0, power_level(member))
        with self.subTest('Advisor'):
            member.roles = [mocks.advisor]
            self.assertEqual(1, power_level(member))
        with self.subTest('Leader'):
            member.roles = [mocks.advisor, mocks.leader]
            self.assertEqual(2, power_level(member))
        with self.subTest('Admin'):
            member.roles = [mocks.advisor, mocks.leader, mocks.admin]
            self.assertEqual(3, power_level(member))

    def test_compare_crew_and_power(self):
        author = mocks.MockMember(display_name='Bob')
        target = mocks.MockMember(display_name='Joe')
        bot = mocks.MockSSB(cache=mocks.fake_cache)
        with self.subTest('Different crews'):
            author.roles = [mocks.hk_role]
            target.roles = [mocks.fsg_role]
            with self.assertRaises(ValueError) as ve:
                compare_crew_and_power(author, target, bot)
            self.assertEqual(str(ve.exception), f'{author.display_name} on {mocks.hk_role.name} '
                                                f'cannot unflair {target.display_name} on {mocks.fsg_role.name}')
        with self.subTest('Admin'):
            author.roles = [mocks.admin]
            target.roles = [mocks.fsg_role]
            self.assertIsNone(compare_crew_and_power(author, target, bot))
        with self.subTest('Leader:Leader'):
            author.roles = [mocks.hk_role, mocks.leader]
            target.roles = [mocks.hk_role, mocks.leader]
            with self.assertRaises(ValueError) as ve:
                compare_crew_and_power(author, target, bot)
            self.assertEqual(str(ve.exception), f'A majority of leaders must approve unflairing leader{target.mention}.'
                                                f' Tag the Doc Keeper role for assistance.')
        with self.subTest('Advisor:Advisor'):
            author.roles = [mocks.hk_role, mocks.advisor]
            target.roles = [mocks.hk_role, mocks.advisor]
            with self.assertRaises(ValueError) as ve:
                compare_crew_and_power(author, target, bot)
            self.assertEqual(str(ve.exception), f' cannot unflair {target.mention} as you are not powerful enough.')
        with self.subTest('No power.'):
            author.roles = [mocks.hk_role]
            target.roles = [mocks.hk_role]
            with self.assertRaises(ValueError) as ve:
                compare_crew_and_power(author, target, bot)
            self.assertEqual(str(ve.exception), 'You must be an advisor, leader or staff to unflair others.')
        with self.subTest('Leader:Advisor'):
            author.roles = [mocks.hk_role, mocks.leader]
            target.roles = [mocks.hk_role, mocks.advisor]
            self.assertIsNone(compare_crew_and_power(author, target, bot))
        with self.subTest('Leader:Nothing'):
            author.roles = [mocks.hk_role, mocks.leader]
            target.roles = [mocks.hk_role]
            self.assertIsNone(compare_crew_and_power(author, target, bot))
        with self.subTest('Advisor:Nothing'):
            author.roles = [mocks.hk_role, mocks.advisor]
            target.roles = [mocks.hk_role]
            self.assertIsNone(compare_crew_and_power(author, target, bot))

    def test_user_by_id(self):
        bot = mocks.MockSSB(cache=mocks.fake_cache)
        with self.subTest('Too short'):
            with self.assertRaises(ValueError) as ve:
                name = 'too short'
                user_by_id(name, bot)
            self.assertEqual(str(ve.exception), f'{name} is not a mention or an id. Try again.')
        with self.subTest('Non int'):
            with self.assertRaises(ValueError) as ve:
                name = 'Abcdefghijklmnopqrstuvwxyz'
                user_by_id(name, bot)
            self.assertEqual(str(ve.exception), f'{name} is not a mention or an id. Try again.')
        with self.subTest('Not on server'):
            with self.assertRaises(ValueError) as ve:
                name = '1234567891011121314'
                user_by_id(name, bot)
            self.assertEqual(str(ve.exception), f'{name} doesn\'t seem to be on '
                                                f'this server or your input is malformed. Try @user.')

    def test_member_lookup(self):
        bot = mocks.MockSSB(cache=mocks.fake_cache)
        with self.subTest('Mention'):
            self.assertEqual(mocks.bob, member_lookup(mocks.bob.mention, bot))
        with self.subTest('Exact match'):
            self.assertEqual(mocks.bob, member_lookup(mocks.bob.name, bot))
        with self.subTest('Close'):
            self.assertEqual(mocks.bob, member_lookup('Bobbert', bot))
        with self.subTest('Not here'):
            name = 'Lalalalala'
            with self.assertRaises(ValueError) as ve:
                member_lookup(name, bot)
            self.assertEqual(str(ve.exception), f'{name} does not match any member in the server.')

    def test_crew_lookup(self):
        bot = mocks.MockSSB(cache=mocks.fake_cache)
        with self.subTest('Tag'):
            self.assertEqual(mocks.HK, crew_lookup(mocks.HK.abbr, bot))

        with self.subTest('Actual name'):
            self.assertEqual(mocks.HK, crew_lookup(mocks.HK.name, bot))

        with self.subTest('Close name'):
            self.assertEqual(mocks.HK, crew_lookup(f'{mocks.HK.name} extr', bot))

        with self.subTest('No similar'):
            not_close = 'Random name that isn\'nt close'
            with self.assertRaises(ValueError) as ve:
                crew_lookup(not_close, bot)
            self.assertEqual(str(ve.exception), f'{not_close} does not match any crew in the server.')

    def test_ambiguous_lookup(self):

        bot = mocks.MockSSB(cache=mocks.fake_cache)
        with self.subTest('Tag'):
            self.assertEqual(mocks.HK, ambiguous_lookup(mocks.HK.abbr, bot))
        with self.subTest('Mention'):
            self.assertEqual(mocks.bob, ambiguous_lookup(mocks.bob.mention, bot))
        with self.subTest('Crew'):
            self.assertEqual(mocks.HK, ambiguous_lookup(mocks.HK.name, bot))
        with self.subTest('Member'):
            self.assertEqual(mocks.bob, ambiguous_lookup(mocks.bob.name, bot))
        with self.subTest('Member close'):
            self.assertEqual(mocks.bob, ambiguous_lookup(f'{mocks.bob.name} suffix', bot))

