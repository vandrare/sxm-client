"""Plugin integration checks without a real SiriusXM account or keyring."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import httpx

spec = importlib.util.spec_from_file_location("backend", Path(__file__).parents[2] / "omarchy-plugin/backend.py")
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class Client:
    password = "test-password"
    async def authenticate(self): return True
    @property
    async def configuration(self): return {}
    @property
    async def channels(self): return [SimpleNamespace(id="octane", name="Octane", channel_number="37")]
    async def close_session(self): pass
    async def get_playlist(self, channel): return "#EXTM3U\nAAC_Data/test.aac\n"
    async def get_segment(self, path): return b"test-audio"
    async def get_channel(self, channel): return SimpleNamespace(id=channel)
    async def get_now_playing(self, channel):
        return {"messages": [{"code": 100}], "moduleList": {"modules": [{"moduleResponse": {
            "liveChannelData": {"markerLists": [{"layer": "cut", "markers": [{"time": 1,
            "cut": {"title": "Test song", "artists": [{"name": "Test artist"}]}}]}]}}}]}}


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = backend.Backend(self.temp.name)
        self.app.emit = lambda: None

    async def asyncTearDown(self):
        await self.app.disconnect()
        self.app.runtime.cleanup()
        self.temp.cleanup()

    async def login(self, remember=True):
        with patch.object(backend, "SXMClientAsync", return_value=Client()), patch.object(backend, "keyring", new_callable=AsyncMock) as key:
            await self.app.login(dict(username="test-user", password="test-password", region="US", remember=remember))
            return key

    async def test_login_stream_metadata_and_secret_storage(self):
        key = await self.login()
        self.assertTrue(self.app.state["connected"], self.app.state["error"])
        key.assert_awaited_once_with("store", "test-password")
        self.assertNotIn("test-password", self.app.path.read_text())
        self.assertNotIn("test-password", json.dumps(self.app.state))
        self.assertEqual(self.app.path.stat().st_mode & 0o777, 0o600)
        async with httpx.AsyncClient() as client:
            response = await client.get(self.app.base + "/octane.m3u8")
            self.assertEqual(response.status_code, 200)
            audio = await client.get(self.app.base + "/AAC_Data/test.aac")
            self.assertEqual(audio.content, b"test-audio")
            track = await client.get(self.app.base + "/now_playing", params={"channel": "octane"})
            self.assertEqual(track.json()["title"], "Test song")
            denied = await client.get(self.app.base.rsplit("/", 1)[0] + "/wrong/octane.m3u8")
            self.assertEqual(denied.status_code, 404)

    async def test_no_remember_clears_previous_secret(self):
        key = await self.login(False)
        key.assert_awaited_once_with("clear")
        self.assertFalse(self.app.prefs["remembered"])

    async def test_keyring_failure_keeps_working_session(self):
        with patch.object(backend, "SXMClientAsync", return_value=Client()), patch.object(backend, "keyring", side_effect=RuntimeError("test")):
            await self.app.login(dict(username="user", password="secret", remember=True))
        self.assertTrue(self.app.state["connected"])
        self.assertFalse(self.app.state["remembered"])
        self.assertIn("keyring", self.app.state["notice"])

    async def test_login_failure_closes_session(self):
        client = Client()
        client.authenticate = AsyncMock(return_value=False)
        client.close_session = AsyncMock()
        with patch.object(backend, "SXMClientAsync", return_value=client):
            await self.app.login(dict(username="user", password="secret"))
        self.assertFalse(self.app.state["connected"])
        self.assertFalse(self.app.state["busy"])
        client.close_session.assert_awaited_once()

    async def test_forget_clears_keyring_and_identity(self):
        await self.login()
        with patch.object(backend, "keyring", new_callable=AsyncMock) as key:
            await self.app.command({"op": "forget"})
        key.assert_awaited_once_with("clear")
        self.assertFalse(self.app.state["connected"])
        self.assertEqual(self.app.prefs["username"], "")
        self.assertFalse(self.app.prefs["remembered"])

    async def test_favorites_and_volume_persist(self):
        await self.app.command({"op": "favorite", "channel": "octane"})
        await self.app.command({"op": "volume", "value": 150})
        saved = json.loads(self.app.path.read_text())
        self.assertEqual(saved["favorites"], ["octane"])
        self.assertEqual(saved["volume"], 100)

    async def test_cancel_login_closes_session(self):
        client = Client()
        entered = asyncio.Event()
        async def slow_auth():
            entered.set()
            await asyncio.sleep(100)
        client.authenticate = slow_auth
        client.close_session = AsyncMock()
        with patch.object(backend, "SXMClientAsync", return_value=client):
            await self.app.command(dict(op="login", username="user", password="secret"))
            await entered.wait()
            await self.app.command({"op": "cancel"})
        self.assertFalse(self.app.state["busy"])
        self.assertFalse(self.app.state["connected"])
        client.close_session.assert_awaited_once()

    @unittest.skipUnless(shutil.which("mpv"), "mpv not installed")
    async def test_real_mpv_controls_and_cleanup(self):
        await self.login()
        create_process = asyncio.create_subprocess_exec
        async def silent_player(*args, **kwargs):
            return await create_process(*args, "--ao=null", **kwargs)
        with patch.object(asyncio, "create_subprocess_exec", side_effect=silent_player):
            await self.app.play("octane")
        player = self.app.player
        await self.app.command({"op": "volume", "value": 42})
        self.assertEqual(await self.app.ipc(["get_property", "volume"]), 42)
        await self.app.command({"op": "pause"})
        self.assertTrue(await self.app.ipc(["get_property", "pause"]))
        await self.app.stop()
        self.assertIsNotNone(player.returncode)
        self.assertFalse(self.app.state["playing"])


if __name__ == "__main__":
    unittest.main()
