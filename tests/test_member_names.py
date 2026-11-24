"""Members are shown by their current nickname in the server, not the username the database first saw."""
import unittest
import unittest.mock

from src.helpers import nick_without_prefix
from tests import mocks
from tests.harness import PREFIX, FakeContext, invoke, make_cog

ABSENT = 404


class NickWithoutPrefixTest(unittest.TestCase):
    def test_the_crew_tag_is_taken_off(self):
        self.assertEqual('Meli', nick_without_prefix('HK | Meli'))
        self.assertEqual('Meli', nick_without_prefix('HK |Meli'))
        self.assertEqual('C', nick_without_prefix('A | B | C'))
        self.assertEqual('Meli', nick_without_prefix('Meli'))

    def test_a_nickname_ending_in_a_bar_is_kept(self):
        # This used to raise an IndexError.
        self.assertEqual('Meli |', nick_without_prefix('Meli |'))
        self.assertEqual('Meli | ', nick_without_prefix('Meli | '))


class RoleListTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.guild = self.cog.cache.scs
        self.channel = mocks.MockTextChannel(name='general', id=5, guild=self.guild)
        self.author = mocks.MockMember(id=1, display_name='Author')
        self.member = mocks.MockMember(id=2, name='old_username', display_name='HK | New*Nick')

    async def run_command(self, name, *args, **kwargs):
        ctx = FakeContext(self.cog, self.author, self.channel, self.guild, PREFIX)
        await invoke(self.cog, name, ctx, *args, **kwargs)
        return '\n'.join(sent['embed']['description'] if sent['embed'] else sent['content'] for sent in ctx.sent)

    async def test_listroles_shows_current_nicknames(self):
        with unittest.mock.patch.object(self.cog, '_role_members',
                                        unittest.mock.AsyncMock(return_value=([self.member], [ABSENT]))), \
                unittest.mock.patch('src.scoreSheetBot.name_from_id', return_value='Gone_Nick') as name_from_id:
            shown = await self.run_command('listroles', role='Holy Knights')
        name_from_id.assert_called_once_with(ABSENT)
        self.assertIn('HK \\| New\\*Nick', shown)
        self.assertIn('Gone\\_Nick: 404', shown)
        self.assertNotIn('old_username', shown)

    async def test_overlaps_show_current_nicknames(self):
        for command in ('overlap', 'noverlap'):
            with self.subTest(command=command), \
                    unittest.mock.patch.object(self.cog, '_overlap_candidates',
                                               unittest.mock.AsyncMock(return_value=[self.member])), \
                    unittest.mock.patch('src.scoreSheetBot.overlap_members', return_value=[self.member]), \
                    unittest.mock.patch('src.scoreSheetBot.noverlap_members', return_value=[self.member]):
                shown = await self.run_command(command, two_roles='Leader Advisor')
                self.assertIn('HK \\| New\\*Nick', shown)
                self.assertNotIn('old_username', shown)
