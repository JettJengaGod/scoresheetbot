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
        bot = mocks.MockBot(emojis = [emoji])

        self.assertTrue(is_usable_emoji(f'<:{emoji.name}:{emoji.id}>', bot))

    def test_unusable_emoji(self):

        bot = mocks.MockBot(emojis = [mocks.emoji_instance])
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
