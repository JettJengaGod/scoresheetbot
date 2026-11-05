"""Tests for giving rejoining members their roles back, the last leader check, softcap's names and unflairing
someone who has left the server."""
import types
import unittest
import unittest.mock

import discord

from src import helpers
from src.crew import Crew
from tests import mocks
from tests.harness import make_cog


def channel_bot():
    """A stand in for the cog with just the flairing info channel and Doc Keeper role `leader_unflaired` uses."""
    channels = types.SimpleNamespace(flairing_info=unittest.mock.MagicMock(send=unittest.mock.AsyncMock()))
    roles = types.SimpleNamespace(docs=types.SimpleNamespace(mention='@Doc Keeper'))
    return types.SimpleNamespace(cache=types.SimpleNamespace(channels=channels, roles=roles))


class RejoinTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.cog.bot.intents = discord.Intents.default()
        self.scs = self.cog.cache.scs
        self.scs.id = 100
        self.kept = mocks.MockRole(name='Kept', id=5)
        self.scs.get_role = {5: self.kept}.get

    def welcome(self, member, message_type=discord.MessageType.new_member, guild=None):
        return types.SimpleNamespace(type=message_type, guild=guild or self.scs, author=member)

    async def test_a_welcome_message_gives_back_the_roles_and_marks_them_in_the_server(self):
        member = mocks.MockMember(id=7, guild=self.scs)
        with unittest.mock.patch.dict('os.environ', {'VERSION': 'PROD'}), \
                unittest.mock.patch('src.scoreSheetBot.update_member_status') as status, \
                unittest.mock.patch('src.scoreSheetBot.find_member_roles', return_value=[5, 6]):
            await self.cog.on_message(self.welcome(member))
        status.assert_called_once_with((7,), ())
        # Role 6 has been deleted since they left, so only the role still there is given back.
        self.assertIn(self.kept, member.roles)

    async def test_other_messages_and_servers_are_ignored(self):
        member = mocks.MockMember(id=7, guild=self.scs)
        self.cog._member_joined = unittest.mock.AsyncMock()
        await self.cog.on_message(self.welcome(member, message_type=discord.MessageType.default))
        await self.cog.on_message(self.welcome(member, guild=types.SimpleNamespace(id=200)))
        self.cog.bot.intents.members = True
        await self.cog.on_message(self.welcome(member))
        self.cog._member_joined.assert_not_awaited()


class LastLeaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_the_last_leader_leaving_is_announced(self):
        bot = channel_bot()
        cr = Crew(name='Holy Knights', abbr='HK', leaders=['first', 'second'], leader_ids=[1, 2])
        await helpers.leader_unflaired(cr, 1, bot)
        bot.cache.channels.flairing_info.send.assert_not_awaited()
        self.assertEqual((['second'], [2]), (cr.leaders, cr.leader_ids))
        await helpers.leader_unflaired(cr, 2, bot)
        bot.cache.channels.flairing_info.send.assert_awaited_once_with(
            "@Doc Keeper: Holy Knights's last leader just unflaired")


class SoftcapNamesTest(unittest.TestCase):
    def test_names_come_from_the_database(self):
        cog = make_cog()
        with unittest.mock.patch('src.scoreSheetBot.member_names', return_value={1: 'Zed', 2: 'Amy'}):
            lines = cog._usage_lines({1: ['a'], 2: ['b', 'c'], 3: ['d']})
        self.assertEqual(['3: [link](d)  (name not found for some reason)', 'Amy: [link](b) [link](c) ',
                          'Zed: [link](a) '], lines)


class GoneMemberUnflairTest(unittest.IsolatedAsyncioTestCase):
    async def test_every_role_unflair_takes_is_removed(self):
        roles = {name: types.SimpleNamespace(id=number, name=name) for number, name in enumerate(
            ('overflow', 'leader', 'advisor', 'fortyman', 'crew_staff', 'join_cd', 'track1', 'track2', 'track3',
             'true_locked'), start=10)}
        bot = channel_bot()
        bot.cache.roles = types.SimpleNamespace(poach_me=None, docs=bot.cache.roles.docs, **roles)
        bot.cache.channels.flair_log = unittest.mock.MagicMock(send=unittest.mock.AsyncMock())
        cr = Crew(name='Holy Knights', abbr='HK', role_id=1, leaders=['gone'], leader_ids=[777777777777777777])
        ctx = unittest.mock.MagicMock(author=types.SimpleNamespace(id=1), send=unittest.mock.AsyncMock())
        held = [1, roles['leader'].id, roles['crew_staff'].id, roles['fortyman'].id]
        with unittest.mock.patch('src.helpers.find_member_crew', return_value='Holy Knights'), \
                unittest.mock.patch('src.helpers.power_level', return_value=3), \
                unittest.mock.patch('src.helpers.crew_lookup', return_value=cr), \
                unittest.mock.patch('src.helpers.all_member_roles', return_value=held), \
                unittest.mock.patch('src.helpers.remove_member_role') as removed, \
                unittest.mock.patch('src.helpers.add_member_role'), \
                unittest.mock.patch('src.helpers.update_member_crew') as crew_change, \
                unittest.mock.patch('src.helpers.record_unflair', return_value=(1, 2, 3)), \
                unittest.mock.patch('src.helpers.response_message', unittest.mock.AsyncMock()):
            await helpers.unflair_gone_member(ctx, '777777777777777777', bot)
        self.assertCountEqual([1, roles['leader'].id, roles['crew_staff'].id, roles['fortyman'].id],
                              [call.args[1] for call in removed.call_args_list])
        crew_change.assert_called_once_with(777777777777777777, None)
        bot.cache.channels.flairing_info.send.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
