"""Install this checkout's plugin into the current user's Omarchy shell."""
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import os

repo = Path(__file__).resolve().parent.parent
os.environ["OMARCHY_SHELL_IPC_TIMEOUT"] = "20s"
source = repo / "omarchy-plugin"
target = Path.home() / ".config/omarchy/plugins/local.siriusxm"
target.mkdir(parents=True, exist_ok=True)
for name in ("manifest.json", "Service.qml", "Widget.qml", "backend.py"):
    shutil.copy2(source / name, target / name)
launcher = target / "launch-backend"
launcher.write_text("#!/bin/sh\nexec " + shlex.quote(str(repo / ".venv/bin/python"))
                    + " -u " + shlex.quote(str(target / "backend.py")) + "\n")
launcher.chmod(0o755)
subprocess.run(["omarchy", "plugin", "validate", str(target)], check=True)
config = Path.home() / ".config/omarchy/shell.json"
if config.exists():
    backup = config.with_name("shell.json.before-siriusxm-" + str(time.time_ns()))
    shutil.copy2(config, backup)
subprocess.run(["omarchy-shell", "shell", "rescanPlugins"], check=True)
subprocess.run(["omarchy", "plugin", "enable", "local.siriusxm", "--section", "left"], check=True)
print("Installed SiriusXM. Click SXM in the bar to sign in.")
