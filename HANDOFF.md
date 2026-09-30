# SiriusXM Omarchy plugin handoff

## User intent

Build a native Omarchy plugin around https://github.com/vandrare/sxm-client.
User confirmed subscription login, audio and metadata work in the original CLI.
Wants login in the plugin frontend and saved username/password. Agreed to use
desktop keyring, not plaintext passwords. Work may span multiple sessions;
keep this handoff current. Session usage percentage is not available to the agent.

## Workspace

- Repo: `/home/scott/Projects/sxm-client`, upstream HEAD initially `b25406d`.
- Environment installed with `uv sync --frozen`, Python 3.14.7, sxm 0.3.3.
- New plugin sources: `omarchy-plugin/`.
- Tests: `tests/plugin/test_backend.py`.
- Installed copy: `~/.config/omarchy/plugins/local.siriusxm/`.
- Plugin enabled in left section of `~/.config/omarchy/shell.json`.
- Backups named `shell.json.before-siriusxm-*` next to shell.json.
- Original client source files are unchanged; plugin development is kept in the
  directories above. User requested committing and pushing this work to origin/master.

## Implemented

QML singleton service + themed bar/popup, username/password form, region selector,
Remember me, cancellation, sign out/forget, channel search, favorites, title/artist,
play/pause/stop/volume. Python stdio bridge owns SXMClientAsync, token-prefixed
ephemeral localhost stream proxy, mpv Unix IPC, Secret Service password storage.
Restores saved login on shell startup; audio starts only on channel selection.

Read `omarchy-plugin/README.md` for commands, security/storage details and limits.
Installer copies files and creates a launcher pointing to this repo's .venv.
Reinstall source changes with `.venv/bin/python omarchy-plugin/install.py`.

## Verified

- Eight account-free integration tests passed, including real loopback routing,
  metadata query forwarding, denied invalid proxy token, non-persistence of password,
  keyring failures, login cancellation, forget account, favorites/volume,
  and real mpv IPC with silent output plus process cleanup.
- Manifest validator and QML parser passed.
- Installed widget loaded, shell ping returned ok, panel summoned successfully.
- Visually inspected login panel against desktop theme; refined the form to use
  native Omarchy Dropdown, Toggle and PanelSlider components.

## Next validation / known limits

User needs to test real account login through the plugin and keyring save/unlock,
channel playback and saved login after shell restart. Do not ask for password in chat
or inspect keyring contents. Stop earlier standalone player/proxy to avoid multiple
SiriusXM sessions. Original localhost:9999 proxy was unavailable at last probe.
No MPRIS, album art or automatic stream recovery yet. Metadata can differ from
buffered/paused audio. Upstream credential-bearing logs are suppressed.

## Environment notes

Use Omarchy skill for desktop modifications; `/usr/share/omarchy` is read-only.
Native Ui APIs documented in local QML there. Shell IPC, Wayland and loopback
tests require sandbox escalation in this agent environment. Initial installer
enable timed out at default 2s during shell reload but did enable the widget;
installer now requests a 20s IPC timeout. Avoid mistaking sandbox isolation
for a stopped desktop shell. Quickshell logs contain unrelated existing plugin
warnings; filter for local.siriusxm. No subagent delegation authorized.

## UI updates — 2026-09-30

- Hold the bar widget width steady while its popup is open so changing channels
  or receiving a new song title cannot move the popup horizontally.
- Use shared compact caption-sized buttons for Account, About, Close, Pause/Resume
  and Stop; Account/About have matching widths and mutually exclusive toggles.
- About view displays `From: The Rathole` and `By: Vandrare`.
- Updated source Widget.qml and installed copy; manifest/QML syntax checks passed.
- Desktop runtime loaded without plugin QML errors. A full `omarchy restart shell`
  was needed because plugin rescans retained cached QML; playback stops on restart.
- User requested committing and pushing these UI changes to GitHub.
