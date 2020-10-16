import unittest

from src.battle import *

TEAM1_NAME = 'Team 1'
TEAM2_NAME = 'Team 2'
TEAM1 = Team(name=TEAM1_NAME, num_players=5, stocks=3 * 5)
TEAM2 = Team(name=TEAM2_NAME, num_players=5, stocks=3 * 5)
PLAYER1_NAME = 'Player 1'
PLAYER1 = Player(name=PLAYER1_NAME, team_name=TEAM1_NAME)
PLAYER1_WITH_CHAR = Player(name=PLAYER1_NAME, team_name=TEAM1_NAME)
PLAYER2_NAME = 'Player 2'
PLAYER2 = Player(name=PLAYER2_NAME, team_name=TEAM2_NAME)
PLAYER2_WITH_CHAR = Player(name=PLAYER2_NAME, team_name=TEAM2_NAME)
Players = [Player(name=f'Player {i}', team_name=f'Team {i + 7 // 7}') for i in range(14)]
Chars = [Character(f'Character {i}') for i in range(14)]

PLAYER1_WITH_CHAR.set_char(Chars[0])
PLAYER2_WITH_CHAR.set_char(Chars[1])


class BattleSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.battle = Battle(TEAM1_NAME, TEAM2_NAME, 5)

    def tearDown(self) -> None:
        self.battle = None

    def test_create_battle(self):
        self.assertEqual(TEAM1, self.battle.team1)
        self.assertEqual(TEAM2, self.battle.team2)

    def test_team_lookup(self):
        self.assertEqual(self.battle.lookup(TEAM1_NAME), TEAM1)
        self.assertEqual(self.battle.lookup(TEAM2_NAME), TEAM2)

    def test_add_player(self):
        self.battle.add_player(team_name=TEAM1_NAME, player_name=PLAYER1_NAME)
        self.assertEqual(self.battle.lookup(TEAM1_NAME).current_player, PLAYER1)
        self.assertIn(PLAYER1, self.battle.lookup(TEAM1_NAME).players)

    def test_ready(self):
        self.battle.add_player(team_name=TEAM1_NAME, player_name=PLAYER1_NAME)
        self.battle.add_player(team_name=TEAM2_NAME, player_name=PLAYER2_NAME)
        self.assertTrue(self.battle.match_ready())

    def test_finish_match_fails_when_not_ready(self):
        with self.assertRaises(StateError):
            self.battle.finish_match(0, 0, Chars[0], Chars[1])

    def test_lookup_fails_with_invalid_team(self):
        with self.assertRaises(StateError):
            self.battle.lookup("invalid")

    def test_winner_and_loser_fail_on_unfinished_battle(self):
        with self.assertRaises(StateError):
            self.battle.winner()
        with self.assertRaises(StateError):
            self.battle.loser()

    def test_resize_battle_correctly_sizes_up(self):
        self.battle.resize(6)
        for team in self.battle.teams:
            assert team.num_players == 6

    def test_resize_battle_correctly_sizes_down(self):
        self.battle.resize(4)
        for team in self.battle.teams:
            assert team.num_players == 4


class BattleInternalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.battle = Battle(TEAM1_NAME, TEAM2_NAME, 5)
        self.battle.add_player(team_name=TEAM1_NAME, player_name=PLAYER1_NAME)
        self.battle.add_player(team_name=TEAM2_NAME, player_name=PLAYER2_NAME)

    def tearDown(self) -> None:
        self.battle = None

    def test_add_player_fails_when_already_exists(self):
        with self.assertRaises(StateError):
            self.battle.add_player(TEAM2_NAME, PLAYER2_NAME)

    def test_replace_current(self):
        self.battle.replace_player(TEAM1_NAME, PLAYER2_NAME)
        self.assertEqual(self.battle.team1.current_player.name, PLAYER2_NAME)
        self.assertEqual(len(self.battle.team1.players), 1)

    def test_fails_if_no_one_won(self):
        with self.assertRaises(AssertionError):
            self.battle.finish_match(0, 0, Chars[1], Chars[2])

    def test_losing_team_has_no_current_player(self):
        self.battle.finish_match(3, 0, Chars[1], Chars[2])
        self.assertIsNone(self.battle.team2.current_player)

    def test_match(self):
        match1 = Match(PLAYER1_WITH_CHAR, PLAYER2_WITH_CHAR, 3, 0, 1)
        actual_match = self.battle.finish_match(3, 0, Chars[0], Chars[1])
        self.assertEqual(match1, actual_match)

    def test_resize_under_current_size_fails(self):
        with self.assertRaises(StateError):
            self.battle.resize(0)
        match1 = Match(PLAYER1_WITH_CHAR, PLAYER2_WITH_CHAR, 3, 0, 1)
        self.battle.finish_match(3, 0, Chars[0], Chars[1])
        self.battle.add_player(TEAM2_NAME, player_name=Players[2].name)
        self.battle.finish_match(3, 0, Chars[0], Chars[2])

        with self.assertRaises(StateError):
            self.battle.resize(1)

    def test_undo_fails_with_no_matches(self):
        with self.assertRaises(StateError):
            self.battle.undo()

    def test_undo(self):
        self.battle.finish_match(3, 0, Chars[0], Chars[1])
        self.battle.undo()
        for team in self.battle.teams:
            self.assertEqual(team.stocks, team.num_players * 3)
        self.assertEqual(self.battle.matches, [])

    def test_battle_over(self):
        battle2 = Battle(TEAM1_NAME, TEAM2_NAME, 1)
        battle2.add_player(team_name=TEAM1_NAME, player_name=PLAYER1_NAME)
        battle2.add_player(team_name=TEAM2_NAME, player_name=PLAYER2_NAME)
        battle2.finish_match(3, 0, Chars[1], Chars[2])
        self.assertTrue(battle2.battle_over())


class BattleBigTest(unittest.TestCase):
    def test_big_battle(self):
        battle = Battle(TEAM1_NAME, TEAM2_NAME, 7)
        battle.add_player(team_name=TEAM1_NAME, player_name=Players[0].name)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[7].name)
        battle.finish_match(3, 2, Chars[0], Chars[7])
        print(battle)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[8].name)
        battle.finish_match(1, 1, Chars[0], Chars[8])
        print(battle)
        battle.add_player(team_name=TEAM1_NAME, player_name=Players[1].name)
        battle.finish_match(2, 2, Chars[1], Chars[8])
        print(battle)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[9].name)
        battle.finish_match(0, 1, Chars[1], Chars[9])
        print(battle)
        battle.add_player(team_name=TEAM1_NAME, player_name=Players[2].name)
        battle.finish_match(3, 1, Chars[2], Chars[9])
        print(battle)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[10].name)
        battle.finish_match(3, 1, Chars[2], Chars[10])
        print(battle)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[11].name)
        battle.finish_match(1, 1, Chars[2], Chars[11])
        print(battle)
        battle.add_player(team_name=TEAM1_NAME, player_name=Players[3].name)
        battle.finish_match(1, 3, Chars[3], Chars[11])
        print(battle)
        battle.add_player(team_name=TEAM1_NAME, player_name=Players[4].name)
        battle.finish_match(1, 0, Chars[4], Chars[11])
        print(battle)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[12].name)
        battle.finish_match(3, 2, Chars[4], Chars[12])
        print(battle)
        battle.add_player(team_name=TEAM2_NAME, player_name=Players[13].name)
        battle.finish_match(1, 1, Chars[4], Chars[13])
        print(battle)
        battle.add_player(team_name=TEAM1_NAME, player_name=Players[4].name)
        battle.finish_match(2, 1, Chars[5], Chars[13])
        print(battle)


if __name__ == '__main__':
    unittest.main()
