import unittest
from src.character import *

# Tests
input_and_expected = [
    ('pikachu', 'pikachu'),
    ('pikachu1', 'pikachu'),
    ('pikachu2', 'pikachu2'),
    ('pikachu8', 'pikachu8'),
    ('pikachu0', None),
    ('pikachu9', None),
    ('pika', 'pikachu'),
    ('pika1', 'pikachu'),
    ('pika2', 'pikachu2'),
    ('pika8', 'pikachu8'),
    ('pika0', None),
    ('pika9', None),
    ('pika', 'pikachu'),
    ('pika1', 'pikachu'),
    ('pika2', 'pikachu2'),
    ('pika8', 'pikachu8'),
    ('pika0', None),
    ('pika9', None),
    ('banjo kazooie', 'banjo_and_kazooie'),
    ('bowser_jr2', 'larry'),
    ('ludwig8', 'ludwig'),
    ('ludwig', 'ludwig'),
    ('olimar5', 'alph5'),
    ('fox', 'foxs'),
    ('foxs7', 'fox7'),
    ('alex2', 'alex2'),
    ('enderman7', 'zombie7'),
    ('zombie', 'steve'),
    ('steve8', 'enderman8'),
    ('<:steve:>', 'steve'),
    ('idk', None),
    ('', None),
    (':', None),
    ('::', None),
    (':idk:', None),
]


class CharacterTest(unittest.TestCase):
    def test_possible_inputs(self):
        for input_str, expected in input_and_expected:
            with self.subTest(input_str):
                if expected is None:
                    raised = False
                    try:
                        string_to_canonical(input_str)
                    except ValueError:
                        raised = True
                    self.assertTrue(raised)
                else:
                    self.assertEqual(string_to_canonical(input_str), expected)
