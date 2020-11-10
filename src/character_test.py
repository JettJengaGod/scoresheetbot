import unittest
from src.character import *

# Tests
input_and_expected = [
    ('pikachu', ':pikachu:'),
    ('pikachu1', ':pikachu:'),
    ('pikachu2', ':pikachu2:'),
    ('pikachu8', ':pikachu8:'),
    ('pikachu0', None),
    ('pikachu9', None),
    ('pika', ':pikachu:'),
    ('pika1', ':pikachu:'),
    ('pika2', ':pikachu2:'),
    ('pika8', ':pikachu8:'),
    ('pika0', None),
    ('pika9', None),
    (':pika:', ':pikachu:'),
    (':pika1:', ':pikachu:'),
    (':pika2:', ':pikachu2:'),
    (':pika8:', ':pikachu8:'),
    (':pika0:', None),
    (':pika9:', None),
    ('idk', None),
    ('', None),
    (':', None),
    ('::', None),
    (':idk:', None),
]


class CharacterTest(unittest.TestCase):
    def test_possible_inputs(self):
        for input_str, expected in input_and_expected:
            if expected is None:
                raised = False
                try:
                    string_to_emote(input_str)
                except ValueError:
                    raised = True
                self.assertTrue(raised)
            else:
                self.assertEqual(string_to_emote(input_str), expected)
