import unittest
from src.helpers import *
from tests import mocks


class HelpersTest(unittest.TestCase):
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
