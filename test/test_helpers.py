import unittest
from ..src.helpers import *


class HelpersTest(unittest.TestCase):
    def test_channel_from_key(self):
        test_key = 'aaaa|bbbbb'
        self.assertEqual(channel_from_key(test_key), 'bbbbb')


if __name__ == '__main__':
    unittest.main()
