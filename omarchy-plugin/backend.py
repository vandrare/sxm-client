"""Private stdio bridge for the Omarchy plugin; stdout is JSON state only."""
import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import socket
import sys
import tempfile

from aiohttp import web
from sxm.client import SXMClientAsync
from sxm.http import make_http_handler
from sxm.models import RegionChoice


async def keyring(action, password=None):
    args = ["secret-tool", action]
    if action == "store":
        args += ["--label=Omarchy SiriusXM"]
    args += ["application", "omarchy-sxm"]
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(
            proc.communicate(password.encode() if password is not None else None), 60
        )
    except BaseException:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode and action == "store":
        raise RuntimeError("Desktop keyring could not save the password.")
    if proc.returncode and action == "clear":
        # No matching item also returns nonzero. Confirm nothing remains.
        if await keyring("lookup"):
            raise RuntimeError("Desktop keyring could not forget the password.")
    return output.decode().rstrip("\n") if proc.returncode == 0 else ""


class Backend:
    def __init__(self, state_dir=None):
        self.directory = Path(state_dir or Path(os.environ.get(
            "XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "omarchy-sxm")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        try:
            self.prefs = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.prefs = {}
        self.state = dict(connected=False, busy=False, error="", notice="",
                          username=self.prefs.get("username", ""),
                          region=self.prefs.get("region", "US"),
                          remembered=self.prefs.get("remembered", False),
                          channels=[], favorites=self.prefs.get("favorites", []),
                          channel="", title="", artist="", playing=False, paused=False,
                          volume=self.prefs.get("volume", 70))
        self.client = self.runner = self.handler = self.player = None
        self.player_reader = self.player_writer = None
        self.login_task = None
        self.play_lock = asyncio.Lock()
        self.runtime = tempfile.TemporaryDirectory(prefix="omarchy-sxm-")
        self.socket = str(Path(self.runtime.name) / "mpv.sock")
        self.base = ""

    def emit(self):
        print(json.dumps(self.state), flush=True)

    def save(self):
        temp = self.path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(self.prefs, out)
        temp.replace(self.path)

    async def disconnect(self):
        await self.stop()
        if self.handler:
            await self.handler.cleanup()
            self.handler = None
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        if self.client:
            await self.client.close_session()
            self.client.password = ""
            self.client = None
        self.state.update(connected=False, channels=[], channel="", title="", artist="")

    async def login(self, data):
        self.state.update(busy=True, error="", notice="")
        self.emit()
        try:
            await self.disconnect()
            username = data.get("username", "").strip()
            password = data.get("password", "")
            region = RegionChoice(data.get("region", "US"))
            if not username or not password:
                raise RuntimeError("Enter your SiriusXM username and password.")
            self.client = SXMClientAsync(username, password, region=region)
            async with asyncio.timeout(50):
                if not await self.client.authenticate():
                    raise RuntimeError("SiriusXM did not accept this login.")
                await self.client.configuration
                channels = await self.client.channels
            self.handler = make_http_handler(self.client, precache=False)
            token = secrets.token_urlsafe(24)

            app = web.Application()
            # mpv resolves relative segment URLs beneath this private prefix.
            async def proxy(request):
                if request.match_info["token"] != token:
                    raise web.HTTPNotFound()
                path = "/" + request.match_info["path"]
                return await self.handler(request.clone(rel_url=request.rel_url.with_path(path).with_query(request.query)))

            app.router.add_get("/{token}/{path:.*}", proxy)
            self.runner = web.AppRunner(app, access_log=None)
            await self.runner.setup()
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            await web.SockSite(self.runner, listener).start()
            self.base = f"http://127.0.0.1:{port}/{token}"
            self.state.update(connected=True, username=username, region=region.value,
                channels=[dict(id=c.id, name=c.name, number=str(c.channel_number)) for c in channels])
            remember = bool(data.get("remember", False))
            try:
                if remember:
                    await keyring("store", password)
                else:
                    await keyring("clear")
                self.state["remembered"] = remember
            except (OSError, RuntimeError, TimeoutError):
                self.state["remembered"] = False
                self.state["notice"] = "Signed in, but keyring update failed. Credentials were not saved for automatic login."
            self.prefs.update(username=username, region=region.value,
                              remembered=self.state["remembered"])
            self.save()
        except asyncio.CancelledError:
            await self.disconnect()
            raise
        except Exception as exc:
            await self.disconnect()
            self.state["error"] = (str(exc) if isinstance(exc, RuntimeError) else
                "Login failed. Check your account, region and connection; browser playback should work first.")
        finally:
            self.state["busy"] = False
            self.emit()

    async def stop(self):
        if self.player_writer:
            self.player_writer.close()
            self.player_writer = self.player_reader = None
        if self.player:
            if self.player.returncode is None:
                self.player.terminate()
                try:
                    await asyncio.wait_for(self.player.wait(), 3)
                except TimeoutError:
                    self.player.kill()
                    await self.player.wait()
            self.player = None
        self.state.update(playing=False, paused=False)

    async def ipc(self, command):
        if not self.player_writer:
            raise RuntimeError("Start a channel first.")
        self.player_writer.write((json.dumps({"command": command}) + "\n").encode())
        await self.player_writer.drain()
        while True:
            line = await asyncio.wait_for(self.player_reader.readline(), 3)
            if not line:
                raise RuntimeError("Audio player disconnected. Select the channel again.")
            reply = json.loads(line)
            if "error" in reply:
                if reply["error"] != "success":
                    raise RuntimeError("Audio player could not perform this action.")
                return reply.get("data")

    async def play(self, channel):
        if not self.state["connected"] or channel not in {c["id"] for c in self.state["channels"]}:
            raise RuntimeError("Sign in and select an available channel.")
        await self.stop()
        Path(self.socket).unlink(missing_ok=True)
        self.player = await asyncio.create_subprocess_exec(
            "mpv", "--no-config", "--no-video", "--idle=yes", "--terminal=no",
            "--input-ipc-server=" + self.socket, "--volume=" + str(self.state["volume"]),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        for _ in range(60):
            try:
                self.player_reader, self.player_writer = await asyncio.open_unix_connection(self.socket)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                await asyncio.sleep(.05)
        await self.ipc(["loadfile", self.base + "/" + channel + ".m3u8", "replace"])
        self.state.update(channel=channel, title="", artist="", playing=True, paused=False)

    async def command(self, data):
        op = data.get("op")
        if op in ("login", "forget", "logout", "cancel"):
            if self.login_task and not self.login_task.done():
                self.login_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.login_task
            if op == "login":
                self.login_task = asyncio.create_task(self.login(data))
                return
            await self.disconnect()
            # Sign out disables automatic login; Forget also deletes the keyring item.
            self.state.update(remembered=False, error="", notice="")
            self.prefs["remembered"] = False
            self.save()
            if op == "forget":
                await keyring("clear")
                self.state["username"] = ""
                self.prefs["username"] = ""
                self.save()
        elif op == "play":
            await self.play(data["channel"])
        elif op == "pause":
            value = not self.state["paused"]
            await self.ipc(["set_property", "pause", value])
            self.state["paused"] = value
        elif op == "stop":
            await self.stop()
        elif op == "volume":
            value = max(0, min(100, int(data["value"])))
            if self.player_writer:
                await self.ipc(["set_property", "volume", value])
            self.state["volume"] = self.prefs["volume"] = value
            self.save()
        elif op == "favorite":
            favorites = list(self.state["favorites"])
            channel = data["channel"]
            if channel in favorites:
                favorites.remove(channel)
            else:
                favorites.append(channel)
            self.state["favorites"] = self.prefs["favorites"] = favorites
            self.save()
        self.emit()

    async def poll(self):
        while True:
            await asyncio.sleep(8)
            if not self.state["playing"] or self.state["busy"]:
                continue
            try:
                async with self.play_lock:
                    idle = await self.ipc(["get_property", "idle-active"])
                if idle:
                    self.state.update(playing=False, error="Stream stopped. Select the channel to reconnect.")
                elif not self.state["paused"]:
                    channel = self.state["channel"]
                    async with asyncio.timeout(12):
                        import httpx
                        async with httpx.AsyncClient() as session:
                            response = await session.get(self.base + "/now_playing", params={"channel": channel})
                            data = response.json()
                    if channel == self.state["channel"]:
                        self.state.update(title=data.get("title", ""), artist=data.get("artist", ""))
                self.emit()
            except Exception:
                # Transient metadata failure must not stop working audio.
                pass

    async def run(self):
        self.emit()
        if self.state["remembered"]:
            try:
                password = await keyring("lookup")
                if password:
                    self.login_task = asyncio.create_task(self.login(dict(
                        username=self.state["username"], password=password,
                        region=self.state["region"], remember=True)))
                else:
                    self.state.update(remembered=False, notice="Unlock your keyring or sign in again.")
                    self.emit()
            except (OSError, TimeoutError):
                self.state["notice"] = "Keyring unavailable. Sign in to continue."
                self.emit()
        reader = asyncio.StreamReader(limit=65536)
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
        polling = asyncio.create_task(self.poll())
        try:
            while line := await reader.readline():
                try:
                    async with self.play_lock:
                        self.state["error"] = ""
                        await self.command(json.loads(line))
                except Exception as exc:
                    self.state["error"] = str(exc) if isinstance(exc, RuntimeError) else "Action failed. Check your connection and try again."
                    self.emit()
        finally:
            transport.close()
            polling.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling
            if self.login_task:
                self.login_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.login_task
            await self.disconnect()
            self.runtime.cleanup()


async def main():
    logging.disable(logging.CRITICAL)  # Upstream debug/error logs may contain secrets.
    backend = Backend()
    task = asyncio.create_task(backend.run())
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, task.cancel)
    with contextlib.suppress(asyncio.CancelledError):
        await task


if __name__ == "__main__":
    asyncio.run(main())
