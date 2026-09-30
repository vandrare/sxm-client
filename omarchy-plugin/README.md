# SiriusXM for Omarchy

An Omarchy Quickshell bar plugin using this checkout's `sxm-client` backend.

## Install

Requires an Omarchy shell with plugin support, Python 3.13+, `uv`, `mpv`,
and `secret-tool` with a working Secret Service desktop keyring.

From the repository root:

```sh
uv sync --frozen
.venv/bin/python omarchy-plugin/install.py
```

The installer copies the plugin into `~/.config/omarchy/plugins/local.siriusxm`,
backs up `shell.json`, and enables the SXM widget in the left bar section.
Its launcher references this checkout's virtual environment: keep the checkout
at the same path, or rerun the installer after moving it.
Rerun the installer to apply source changes. Omarchy hot-reloads the installed files.

## Use

Click **SXM**, enter your streaming username and password, select US or Canada,
and click **Sign in**. **Remember me** stores the password in your desktop
keyring and restores login when the shell starts. It does not automatically
start audio. A locked keyring may present its own unlock prompt.

Choose a channel to play. Search by channel number or name; stars are local
favorites. Pause, resume, stop, and volume control the plugin's own mpv process.
The bar shows the track title; metadata refreshes about every eight seconds.

**Account → Sign out** stops playback and disables automatic login, retaining
the keyring item. **Forget account** additionally removes the keyring item and
saved username. Favorites and volume remain. With Remember me unchecked, a
successful login removes the previous saved password.

Stop the earlier standalone test player/proxy before testing plugin playback
to avoid concurrent SiriusXM sessions. The plugin starts its own proxy; no
terminal server is needed.

## Storage and architecture

- Password: Secret Service item with `application=omarchy-sxm`.
- Username, region, remember preference, favorites, volume:
  `$XDG_STATE_HOME/omarchy-sxm/settings.json` (default `~/.local/state/omarchy-sxm/`), mode 0600.
- QML service starts one Python bridge for all bar instances/monitors.
- Commands and state use private stdin/stdout pipes. Passwords are never placed
  in command arguments, shell.json, state JSON, or emitted state.
- The Python process owns the SXM session, an ephemeral localhost proxy with an
  unguessable URL prefix, and mpv controlled over a private Unix socket.
- Upstream logs are suppressed because its diagnostic paths can contain credentials.
- Closing the panel keeps playback running. Unloading the service closes its
  stdin and cleans up the session, proxy, and player.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests/plugin -v
omarchy plugin validate omarchy-plugin
```

Tests mock SiriusXM and the keyring; they exercise real localhost HTTP routing
and mpv IPC with null audio output. Real account login, keyring unlock/save,
and sustained streaming still require a desktop smoke test.

## Current limits

Live-radio metadata is station metadata, not a timestamp-synchronized view of
buffered/paused audio. Stream failures show a reconnect message; select the
channel again. MPRIS/media-key support, album art, and automatic stream recovery
are not implemented. Login failures currently show a generic account/region/
connection message rather than raw upstream diagnostics.

Disable with `omarchy plugin disable local.siriusxm`. To remove saved credentials,
use Forget account before disabling/removing the plugin.
