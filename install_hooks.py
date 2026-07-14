"""Install the desktop-pet lifecycle hooks into ~/.codex/hooks.json."""
from __future__ import annotations

import json
import os
from pathlib import Path


EVENTS = {
    "UserPromptSubmit": "正在同步桌宠状态",
    "PermissionRequest": "正在通知桌宠等待批准",
    "Stop": "正在同步完整回答到桌宠",
}


def is_desktop_pet_handler(handler: object) -> bool:
    return isinstance(handler, dict) and "codex_hook.py" in str(
        handler.get("commandWindows") or handler.get("command_windows") or handler.get("command") or ""
    )


def main() -> int:
    script = (Path(__file__).resolve().parent / "codex_hook.py").resolve()
    # Starting the command with a quoted executable is not compatible with
    # the Codex Desktop Windows hook parser. `py` avoids that leading quote.
    script_arg = f'"{script}"' if " " in str(script) else str(script)
    command = f"py -3 {script_arg}"
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    hooks_path = codex_home / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    if hooks_path.exists():
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
    else:
        config = {}
    hooks = config.setdefault("hooks", {})

    for event, status in EVENTS.items():
        cleaned_groups = []
        for group in hooks.get(event, []):
            if not isinstance(group, dict):
                cleaned_groups.append(group)
                continue
            remaining = [
                handler
                for handler in group.get("hooks", [])
                if not is_desktop_pet_handler(handler)
            ]
            if remaining:
                updated = dict(group)
                updated["hooks"] = remaining
                cleaned_groups.append(updated)
        cleaned_groups.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "commandWindows": command,
                        "timeout": 5,
                        "statusMessage": status,
                    }
                ]
            }
        )
        hooks[event] = cleaned_groups

    hooks_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Installed Codex desktop-pet hooks: {hooks_path}")
    print("Open /hooks in Codex and trust the three changed hook definitions once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

