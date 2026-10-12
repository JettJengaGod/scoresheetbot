"""Tests for refreshing the cache: failures are survived and reported, and a failed refresh changes nothing."""
import asyncio
import os
import unittest
import unittest.mock

from google.auth.exceptions import RefreshError

from src.cache import SIGN_IN_NEEDED, Cache
from tests import mocks
from tests.harness import FakeContext, find_command, make_cog


class RecacheTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = make_cog()
        self.cache = self.cog.cache_value
        self.cache.update = unittest.mock.AsyncMock()
        self.cache.channels = unittest.mock.MagicMock()
        self.cache.channels.recache_logs.send = unittest.mock.AsyncMock()
        self.logged = self.cache.channels.recache_logs.send
        self.jobs = []
        patches = [
            unittest.mock.patch.multiple('src.scoreSheetBot', current_league_name=lambda: ('League', None, True),
                                         crew_update=unittest.mock.DEFAULT, logfile=unittest.mock.mock_open()),
            unittest.mock.patch.dict(os.environ, {'VERSION': 'PROD'}),
            unittest.mock.patch.object(type(self.cog), '_recache_jobs', lambda cog: self.jobs),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def messages(self):
        return [call.args[0] for call in self.logged.await_args_list]

    async def test_a_failed_refresh_is_reported_and_does_not_raise(self):
        self.cache.update.side_effect = ValueError('sheet unreachable')
        job = unittest.mock.AsyncMock()
        self.jobs = [('Job', job)]
        with self.assertLogs(level='ERROR'):
            failed = await self.cog._cache_process()
        self.assertEqual(['Recache: ValueError: sheet unreachable'], failed)
        self.assertEqual(['Starting recache.', 'Recache failed: ValueError: sheet unreachable'], self.messages())
        job.assert_not_awaited()

    async def test_each_job_runs_even_if_one_before_it_fails(self):
        first = unittest.mock.AsyncMock(side_effect=RuntimeError('discord down'))
        second = unittest.mock.AsyncMock()
        third = unittest.mock.MagicMock()  # some jobs aren't coroutines
        self.jobs = [('First', first), ('Second', second), ('Third', third)]
        with self.assertLogs(level='ERROR'):
            failed = await self.cog._cache_process()
        second.assert_awaited_once()
        third.assert_called_once()
        self.assertEqual(['First: RuntimeError: discord down'], failed)
        self.assertEqual(['Starting recache.', 'First failed: RuntimeError: discord down',
                          'Recached, but these failed: First'], self.messages())

    async def test_a_clean_refresh_says_so(self):
        self.assertEqual([], await self.cog._cache_process())
        self.assertEqual(['Starting recache.', 'Successfully recached.'], self.messages())

    async def test_only_one_refresh_runs_at_a_time(self):
        release = asyncio.Event()
        runs = []

        async def slow_update(bot):
            runs.append(len(runs))
            await release.wait()

        self.cache.update.side_effect = slow_update
        running = asyncio.create_task(self.cog._cache_process())
        await asyncio.sleep(0)
        self.assertEqual([], await self.cog._cache_process(backup=True))
        self.assertEqual(1, len(runs))
        waiting = asyncio.create_task(self.cog._cache_process(wait=True))
        await asyncio.sleep(0)
        self.assertEqual(1, len(runs))
        release.set()
        await asyncio.gather(running, waiting)
        self.assertEqual(2, len(runs))

    async def recache_command(self, loop_running):
        loop = unittest.mock.MagicMock()
        loop.is_running.return_value = loop_running
        ctx = FakeContext(self.cog, mocks.MockMember(id=1), mocks.MockTextChannel(id=5), self.cache.scs)
        with unittest.mock.patch.object(self.cog, 'auto_cache', loop):
            await find_command(self.cog, 'recache').callback(self.cog, ctx)
        return loop, ctx

    async def test_the_recache_command_starts_a_stopped_refresh_loop(self):
        loop, ctx = await self.recache_command(loop_running=False)
        loop.start.assert_called_once()
        loop.restart.assert_not_called()
        self.assertEqual('The cache has been reset, everything should be updated now.', ctx.sent[0]['content'])
        loop, _ = await self.recache_command(loop_running=True)
        loop.restart.assert_called_once()
        loop.start.assert_not_called()

    async def test_the_recache_command_says_what_failed(self):
        self.cache.update.side_effect = ValueError('sheet unreachable')
        with self.assertLogs(level='ERROR'):
            loop, ctx = await self.recache_command(loop_running=False)
        loop.start.assert_called_once()
        self.assertEqual('The cache could not be fully refreshed:\nRecache: ValueError: sheet unreachable',
                         ctx.sent[0]['content'])


class CacheUpdateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = Cache()
        self.cache.crews_by_name = {'Old Crew': 'old'}
        self.cache.channels = 'old channels'
        self.cache.flairing_allowed = False

    async def test_a_failed_refresh_leaves_the_cache_as_it_was(self):
        async def build(new, bot):
            new.channels = 'new channels'
            raise ValueError('sheet unreachable')

        with unittest.mock.patch.object(Cache, '_build', build), self.assertRaises(ValueError):
            await self.cache.update(unittest.mock.MagicMock())
        self.assertEqual(('old channels', {'Old Crew': 'old'}), (self.cache.channels, self.cache.crews_by_name))

    async def test_a_refresh_replaces_everything_but_what_commands_set(self):
        async def build(new, bot):
            new.channels = 'new channels'
            new.crews_by_name = {'New Crew': 'new'}

        with unittest.mock.patch.object(Cache, '_build', build):
            await self.cache.update(unittest.mock.MagicMock())
        self.assertEqual(('new channels', {'New Crew': 'new'}), (self.cache.channels, self.cache.crews_by_name))
        self.assertFalse(self.cache.flairing_allowed)


class GoogleSignInTest(unittest.IsolatedAsyncioTestCase):
    async def update_crews(self, creds, version):
        flow = unittest.mock.MagicMock()
        with unittest.mock.patch('src.cache.os.path.exists', return_value=creds is not None), \
                unittest.mock.patch('src.cache.pickle.load', return_value=creds), \
                unittest.mock.patch('src.cache.pickle.dump'), \
                unittest.mock.patch('src.cache.open', unittest.mock.mock_open(), create=True), \
                unittest.mock.patch('src.cache.InstalledAppFlow', flow), \
                unittest.mock.patch('src.cache.build', side_effect=RuntimeError('stop after signing in')), \
                unittest.mock.patch.dict(os.environ, {'VERSION': version}):
            with self.assertRaises(RuntimeError) as raised:
                await Cache().update_crews()
        return str(raised.exception), flow

    def expired(self):
        creds = unittest.mock.MagicMock(valid=False, expired=True, refresh_token='token')
        creds.refresh.side_effect = RefreshError('invalid_grant')
        return creds

    async def test_the_server_never_waits_for_a_browser_sign_in(self):
        for creds in (None, self.expired()):
            with self.subTest(creds=creds):
                message, flow = await self.update_crews(creds, 'PROD')
                self.assertEqual(SIGN_IN_NEEDED, message)
                flow.from_client_secrets_file.assert_not_called()

    async def test_elsewhere_a_browser_sign_in_is_offered(self):
        message, flow = await self.update_crews(self.expired(), 'ALPHA')
        self.assertEqual('stop after signing in', message)
        flow.from_client_secrets_file.return_value.run_local_server.assert_called_once()


if __name__ == '__main__':
    unittest.main()
