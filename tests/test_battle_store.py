"""Running battles are saved to disk and come back the same after a restart."""
import json
import os
import tempfile
import types
import unittest
import unittest.mock

from src import battle_store
from src.battle import Battle, BattleType, Difficulty, ForfeitMatch, InfoMatch, Match, TimerMatch
from src.character import Character
from src.constants import *
from tests import mocks
from tests.harness import PREFIX, FakeContext, invoke, make_cog


def char(name: str) -> Character:
    return Character(name, bot=None)


def busy_battle() -> Battle:
    """A battle part way through, with every kind of entry in its match log."""
    battle = Battle('Holy Knights', 'FSGood', 3, BattleType.RANKED)
    battle.id = 'ABCDE / 123'
    battle.stream = 'https://twitch.tv/jett'
    battle.add_player('Holy Knights', 'Bob', 'bob#1', 1)
    battle.add_player('FSGood', 'Joe', 'joe#2', 2)
    battle.finish_match(3, 1, char('bjr2'), char('olimar5'))
    battle.add_player('FSGood', 'Steve', 'joe#2', 3)
    battle.timer_stock('FSGood', 'joe#2')
    battle.ext_used('Holy Knights')
    battle.replace_player('Holy Knights', 'Ann', 'ann#4', 4)
    battle.finish_lag(1, 1, char('ness3'), char('link2'))
    battle.confirm('FSGood')
    return battle


def restart(battle: Battle) -> Battle:
    """What `battle` is after being written out and read back."""
    return battle_store.loads(battle_store.dumps({'key|1': battle}))['key|1']


def snapshot(battle: Battle) -> dict:
    return {'saved': battle_store.battle_to_dict(battle), 'text': str(battle), 'embed': battle.embed().to_dict(),
            'header': battle.header, 'timer': battle.time, 'over': battle.battle_over()}


class RoundTripTest(unittest.TestCase):
    def test_a_restored_battle_is_the_same_battle(self):
        battle = busy_battle()
        self.assertEqual(snapshot(battle), snapshot(restart(battle)))

    def test_everything_set_on_a_battle_is_saved(self):
        """Fails when a field is added to a battle, team, player or character without being saved."""
        battle = busy_battle()
        saved = battle_store.battle_to_dict(battle)
        # teams is the two teams again, and the header follows from the type.
        self.assertEqual(set(vars(battle)) - {'teams', 'header'}, set(saved))
        self.assertEqual(set(vars(battle.team1)), set(saved['team1']))
        player = battle.team1.players[0]
        self.assertEqual(set(vars(player)), set(saved['team1']['players'][0]))
        self.assertEqual(vars(player.char), saved['team1']['players'][0]['char'])

    def test_it_is_plain_json_and_the_same_text_every_time(self):
        battle = busy_battle()
        text = battle_store.dumps({'key|1': battle})
        self.assertEqual(battle_store.VERSION, json.loads(text)['version'])
        self.assertEqual(text, battle_store.dumps({'key|1': battle}))
        self.assertEqual(text, battle_store.dumps(battle_store.loads(text)))

    def test_every_kind_of_match_comes_back(self):
        battle = busy_battle()
        battle.forfeit('FSGood')
        restored = restart(battle)
        self.assertEqual([type(match) for match in battle.matches], [type(match) for match in restored.matches])
        self.assertEqual({Match, InfoMatch, TimerMatch, ForfeitMatch}, {type(match) for match in restored.matches})
        self.assertEqual([str(match) for match in battle.matches], [str(match) for match in restored.matches])
        self.assertTrue(restored.battle_over())
        self.assertEqual('Holy Knights', restored.winner().name)

    def test_the_match_log_shares_its_players_with_the_rosters(self):
        """`undo` changes a player through the match that is undone, so it has to be the roster's player."""
        restored = restart(busy_battle())
        for team in restored.teams:
            if team.current_player:
                self.assertTrue(any(team.current_player is player for player in team.players))
        for match in restored.matches:
            if type(match) is Match:
                self.assertTrue(any(match.p1 is player for player in restored.team1.players))
                self.assertTrue(any(match.p2 is player for player in restored.team2.players))
            elif isinstance(match, TimerMatch):
                self.assertTrue(any(match.team is team for team in restored.teams))
                self.assertTrue(any(match.player is player for player in match.team.players))

    def test_undo_works_the_same_after_a_restart(self):
        battle = busy_battle()
        restored = restart(battle)
        while battle.matches:
            self.assertEqual(battle.undo(), restored.undo())
            self.assertEqual(snapshot(battle), snapshot(restored))
        self.assertEqual([], restored.matches)

    def test_a_restored_battle_can_be_played_to_the_end(self):
        battle = busy_battle()
        restored = restart(battle)
        for current in (battle, restored):
            # The teams are 7-4 here, with Ann and Steve on one stock each.
            self.assertEqual((7, 4), (current.team1.stocks, current.team2.stocks))
            current.finish_match(1, 0, char('mario'), char('fox'))
            current.add_player('FSGood', 'Zed', 'joe#2', 5)
            current.finish_match(0, 1, char('mario'), char('wolf'))
            current.resize(4)
            current.forfeit('Holy Knights')
            current.confirm('Holy Knights')
        # The timer restarts whenever a match finishes, which is at a different moment for each of them.
        battle.time = restored.time
        self.assertEqual(snapshot(battle), snapshot(restored))
        self.assertTrue(restored.confirmed())

    def test_the_resend_rule_still_knows_who_has_played(self):
        restored = restart(busy_battle())
        with self.assertRaisesRegex(Exception, 'must send'):
            restored.add_player('Holy Knights', 'Bob', 'bob#1', 1)

    def test_skins_keep_their_own_name(self):
        """Reading a skin's name again would turn some into their base character, so it is saved as it is."""
        battle = Battle('A', 'B', 2, BattleType.MOCK)
        battle.add_player('A', 'Bob', 'bob#1', 1)
        battle.add_player('B', 'Joe', 'joe#2', 2)
        battle.finish_match(3, 0, char('bjr2'), char('steve2'))
        self.assertEqual('bowser_jr', char('larry').emoji_name, 'the name of a skin does not read back as itself')
        restored = restart(battle)
        p1, p2 = restored.matches[0].p1, restored.matches[0].p2
        self.assertEqual(('larry', 'bowser_jr', 'alex2', 'steve'),
                         (p1.char.emoji_name, p1.char.base, p2.char.emoji_name, p2.char.base))

    def test_a_player_who_has_not_played_yet_has_no_character(self):
        battle = Battle('A', 'B', 2, BattleType.MOCK)
        battle.add_player('A', 'Bob', 'bob#1', 1)
        player = restart(battle).team1.current_player
        self.assertEqual(('', 'Bob '), (player.char.emoji, str(player)))

    def test_every_battle_type_and_difficulty(self):
        for battle_type in BattleType:
            with self.subTest(battle_type=battle_type):
                battle = Battle('A', 'B', 5, battle_type)
                restored = restart(battle)
                self.assertEqual((battle_type, battle.header), (restored.battle_type, restored.header))
        for difficulty in Difficulty:
            battle = Battle('A', 'B', 5, BattleType.ARCADE)
            battle.team2.difficulty = difficulty
            self.assertEqual(difficulty, restart(battle).team2.difficulty)

    def test_a_new_battle(self):
        battle = Battle('A', 'B', 5, BattleType.REG)
        self.assertEqual(snapshot(battle), snapshot(restart(battle)))


class FileTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, 'battles.json')

    def write(self, text):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(text)

    def test_battles_come_back_from_the_file(self):
        battles = {'SCS|1': busy_battle(), 'SCS|2': Battle('A', 'B', 5, BattleType.MOCK), 'SCS|3': None}
        battle_store.save_battles(self.path, battle_store.dumps(battles))
        loaded = battle_store.load_battles(self.path)
        self.assertEqual(['SCS|1', 'SCS|2'], sorted(loaded))
        self.assertEqual(snapshot(battles['SCS|1']), snapshot(loaded['SCS|1']))
        self.assertEqual([os.path.basename(self.path)], os.listdir(os.path.dirname(self.path)))

    def test_no_file_means_no_battles(self):
        self.assertEqual({}, battle_store.load_battles(self.path))

    def test_a_file_that_cannot_be_read_is_set_aside(self):
        for text in ('{"version": 1, "battles": {"SCS|1": {"te', '{"version": 0, "battles": {}}'):
            with self.subTest(text=text), self.assertLogs(battle_store.log, 'ERROR'):
                self.write(text)
                self.assertEqual({}, battle_store.load_battles(self.path))
                self.assertFalse(os.path.exists(self.path))
                with open(f'{self.path}.bad', encoding='utf-8') as f:
                    self.assertEqual(text, f.read())

    def test_one_battle_that_cannot_be_read_does_not_lose_the_others(self):
        saved = json.loads(battle_store.dumps({'SCS|1': busy_battle(), 'SCS|2': busy_battle()}))
        saved['battles']['SCS|2']['battle_type'] = 'NOT_A_TYPE'
        self.write(json.dumps(saved))
        with self.assertLogs(battle_store.log, 'ERROR'):
            self.assertEqual(['SCS|1'], list(battle_store.load_battles(self.path)))

    def test_battles_without_a_channel(self):
        battles = {'SCS|1': None, 'Some | server|22': None, 'SCS|3': None}
        self.assertEqual(['Some | server|22'], battle_store.keys_without_channel(battles, [1, 3, 4]))

    def test_where_the_file_is(self):
        with unittest.mock.patch.dict('os.environ', {'BATTLE_FILE': ''}):
            self.assertEqual(battle_store.DEFAULT_PATH, battle_store.battle_file())
            self.assertEqual('battles.json', os.path.basename(battle_store.DEFAULT_PATH))
        with unittest.mock.patch.dict('os.environ', {'BATTLE_FILE': self.path}):
            self.assertEqual(self.path, battle_store.battle_file())


class RestartTest(unittest.IsolatedAsyncioTestCase):
    """The bot itself: commands save the battles, and a new bot picks them up."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, 'battles.json')
        self.cog = self.start_bot()
        self.guild = self.cog.cache.scs
        self.channel = mocks.MockTextChannel(name='⚔-arena-1', id=555, guild=self.guild)
        verified = mocks.MockRole(name=VERIFIED)
        self.author = mocks.MockMember(name='nobody', id=31, display_name='Nobody')
        self.red = mocks.MockMember(name='red', id=12, display_name='Red Player', roles=[verified])
        self.blue = mocks.MockMember(name='blue', id=22, display_name='Blue Player', roles=[verified])

    def start_bot(self):
        cog = make_cog()
        cog.battle_file = self.path
        cog.load_battles()
        return cog

    async def run_command(self, cog, name, *args):
        ctx = FakeContext(cog, self.author, self.channel, self.guild, PREFIX)
        with unittest.mock.patch('src.scoreSheetBot.wait_for_reaction_on_message',
                                 unittest.mock.AsyncMock(return_value=True)):
            await invoke(cog, name, ctx, *args)
        return ctx.sent

    def saved(self):
        with open(self.path, encoding='utf-8') as f:
            return json.load(f)['battles']

    async def play(self, cog):
        await self.run_command(cog, 'mock', 'Red', 'Blue', 2)
        await self.run_command(cog, 'send', self.red, 'Red')
        await self.run_command(cog, 'send', self.blue, 'Blue')
        await self.run_command(cog, 'arena', 'ABCDE')
        await self.run_command(cog, 'end', 'mario', 3, 'fox', 1)

    async def test_a_restarted_bot_carries_on_with_the_battle(self):
        await self.play(self.cog)
        before = await self.run_command(self.cog, 'status')

        restarted = self.start_bot()
        self.assertEqual(list(self.cog.battle_map), list(restarted.battle_map))
        self.assertIsNot(next(iter(self.cog.battle_map.values())), next(iter(restarted.battle_map.values())))
        self.assertEqual(before, await self.run_command(restarted, 'status'))

        for cog in (self.cog, restarted):
            await self.run_command(cog, 'send', self.blue, 'Blue')
            await self.run_command(cog, 'undo')
        after = await self.run_command(restarted, 'status')
        self.assertEqual(await self.run_command(self.cog, 'status'), after)
        self.assertNotEqual(before, after)

    async def test_every_change_is_on_disk_before_the_next_command(self):
        self.assertFalse(os.path.exists(self.path), 'nothing to save yet')
        await self.run_command(self.cog, 'mock', 'Red', 'Blue', 2)
        (key, battle), = self.saved().items()
        self.assertEqual(f'{self.guild}|555', key)
        self.assertEqual([], battle['team1']['players'])
        await self.run_command(self.cog, 'send', self.red, 'Red')
        self.assertEqual(['Red Player'], [p['name'] for p in self.saved()[key]['team1']['players']])
        await self.run_command(self.cog, 'arena', 'ABCDE')
        self.assertEqual('ABCDE', self.saved()[key]['id'])

    async def test_a_finished_battle_is_not_brought_back(self):
        await self.play(self.cog)
        await self.run_command(self.cog, 'clear')
        self.assertEqual({}, self.cog.battle_map)
        self.assertEqual({}, self.saved())
        self.assertEqual({}, self.start_bot().battle_map)

    async def test_the_file_is_only_written_when_a_battle_changed(self):
        await self.play(self.cog)
        with unittest.mock.patch('src.battle_store.save_battles') as save:
            await self.run_command(self.cog, 'status')
            save.assert_not_called()
            await self.run_command(self.cog, 'stream', 'jett')
            save.assert_called_once()

    async def test_a_command_still_works_when_saving_fails(self):
        self.cog.battle_file = os.path.join(self.path, 'not', 'a', 'folder', 'battles.json')
        with self.assertLogs(level='ERROR'):
            sent = await self.run_command(self.cog, 'mock', 'Red', 'Blue', 2)
        self.assertTrue(sent)
        self.assertEqual(1, len(self.cog.battle_map))

    async def test_battles_are_kept_in_memory_only_until_a_file_is_set(self):
        cog = make_cog()
        with unittest.mock.patch('src.battle_store.save_battles') as save:
            await self.run_command(cog, 'mock', 'Red', 'Blue', 2)
        save.assert_not_called()
        self.assertEqual(1, len(cog.battle_map))

    async def test_a_battle_whose_channel_was_deleted_is_dropped(self):
        await self.play(self.cog)
        restarted = self.start_bot()
        bot = restarted.bot
        bot.guilds = [types.SimpleNamespace(unavailable=True)]
        bot.get_all_channels = lambda: []
        self.assertEqual([], restarted.drop_battles_without_a_channel(), 'the channels are not known yet')
        self.assertEqual(1, len(restarted.battle_map))

        bot.guilds = [types.SimpleNamespace(unavailable=False)]
        bot.get_all_channels = lambda: [self.channel]
        self.assertEqual([], restarted.drop_battles_without_a_channel())

        bot.get_all_channels = lambda: [mocks.MockTextChannel(id=556)]
        with self.assertLogs(level='WARNING'):
            self.assertEqual([f'{self.guild}|555'], restarted.drop_battles_without_a_channel())
        self.assertEqual({}, restarted.battle_map)
        self.assertEqual({}, self.saved())


if __name__ == '__main__':
    unittest.main()
