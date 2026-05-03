import unittest
from unittest.mock import MagicMock
from src.cache import Cache, parse_from_end
from src.constants import *

class TestCache(unittest.TestCase):
    def setUp(self):
        self.cache = Cache()
        self.cache.scs = MagicMock()
        self.cache.overflow_server = MagicMock()
        
    def test_category_roles(self):
        role1 = MagicMock()
        role1.name = "role1"
        role1.position = 1
        
        role2 = MagicMock()
        role2.name = "ㅤㅤㅤㅤㅤ category"
        role2.position = 2
        
        role3 = MagicMock()
        role3.name = "ㅤㅤㅤㅤㅤ category 2"
        role3.position = 0
        
        self.cache.scs.roles = [role1, role2, role3]
        roles = self.cache.category_roles()
        
        self.assertEqual(len(roles), 2)
        self.assertEqual(roles[0], role3)
        self.assertEqual(roles[1], role2)

    def test_members_by_name(self):
        member1 = MagicMock()
        member1.name = "Alice"
        member1.display_name = "Alice_D"
        member1.roles = []
        
        member2 = MagicMock()
        member2.name = "Bob"
        member2.display_name = "Bob"
        member2.roles = []
        
        members = self.cache.members_by_name([member1, member2])
        self.assertIn("Alice", members)
        self.assertIn("Alice_D", members)
        self.assertIn("Bob", members)
        self.assertEqual(len(members), 3)

    def test_flairing_toggle(self):
        self.assertTrue(self.cache.flairing_allowed)
        self.cache.flairing_toggle()
        self.assertFalse(self.cache.flairing_allowed)
        self.cache.flairing_toggle()
        self.assertTrue(self.cache.flairing_allowed)

    def test_parse_from_end(self):
        self.assertEqual(parse_from_end("some text 123"), 123)
        self.assertEqual(parse_from_end("123"), 123)
        with self.assertRaises(ValueError):
            parse_from_end("no numbers here")

if __name__ == '__main__':
    unittest.main()
