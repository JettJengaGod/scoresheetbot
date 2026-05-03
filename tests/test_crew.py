import unittest
from datetime import datetime
import discord
from src.crew import Crew, DbCrew

class TestCrew(unittest.TestCase):
    def test_crew_initialization(self):
        c = Crew(name="Test Crew", abbr="TC")
        self.assertEqual(c.name, "Test Crew")
        self.assertEqual(c.abbr, "TC")
        self.assertEqual(c.member_count, 0)
        self.assertFalse(c.overflow)

    def test_from_db_crew(self):
        dbc = DbCrew(
            discord_id=123, tag="TC", name="Test Crew", rank=1, overflow=False,
            watch_listed=True, freeze_date=datetime(2025, 1, 1), verify=False,
            strikes=1, slots_total=5, slots_left=4, decay_level=0,
            last_battle=datetime(2025, 1, 2), last_opp="Opp", db_id=1,
            softcap_max=50, member_count=10, triforce=1, hardcap=60,
            softcap_used=10, current_destiny=50, destiny_opponent="Dest",
            destiny_rank=2, destiny_opt_out=False
        )
        c = Crew(name="Test Crew", abbr="TC")
        c.fromDbCrew(dbc)

        self.assertTrue(c.wl)
        self.assertEqual(c.freeze, "01/01/2025")
        self.assertEqual(c.strikes, 1)
        self.assertEqual(c.total_slots, 5)
        self.assertEqual(c.remaining_slots, 4)
        self.assertEqual(c.db_id, 1)
        self.assertEqual(c.member_count, 10)
        self.assertEqual(c.hardcap, 60)

    def test_crew_embed(self):
        c = Crew(name="Test Crew", abbr="TC", member_count=10, hardcap=50)
        embed = c.embed
        self.assertIsInstance(embed, discord.Embed)
        self.assertEqual(embed.title, "Test Crew")
        self.assertIn("**Tag:** TC", embed.description)
        self.assertIn("**Total Members:** 10", embed.description)

if __name__ == '__main__':
    unittest.main()
