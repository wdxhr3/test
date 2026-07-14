"""Codex lifecycle hook -> local desktop pet event bridge.

The hook is deliberately fail-open: desktop-pet failures never interrupt Codex.
"""
from __future__ import annotations

import json
import re
import socket
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = APP_DIR / "runtime"
PENDING_PATH = RUNTIME_DIR / "pending_events.jsonl"


def read_payload() -> dict:
    raw = sys.stdin.buffer.read().decode("utf-8-sig").strip()
    if not raw and len(sys.argv) > 1:
        raw = sys.argv[1]
    return json.loads(raw) if raw else {}


def safe_session(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(value or "unknown"))[:100]


def session_path(session_id: object) -> Path:
    return RUNTIME_DIR / f"session_{safe_session(session_id)}.json"


def load_prompt(session_id: object) -> str:
    try:
        return str(json.loads(session_path(session_id).read_text(encoding="utf-8")).get("prompt", ""))
    except Exception:
        return ""


def save_prompt(session_id: object, prompt: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    session_path(session_id).write_text(
        json.dumps({"prompt": prompt}, ensure_ascii=False), encoding="utf-8"
    )


def compact_tool(payload: dict) -> str:
    tool = str(payload.get("tool_name", "操作"))
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        detail = tool_input.get("description") or tool_input.get("command") or ""
    else:
        detail = str(tool_input)
    detail = " ".join(str(detail).split())
    return f"Codex 请求批准：{tool}" + (f"\n{detail[:240]}" if detail else "")


def transform(payload: dict) -> dict:
    event = str(payload.get("hook_event_name", payload.get("type", "")))
    session_id = payload.get("session_id", payload.get("thread-id", ""))
    turn_id = payload.get("turn_id", payload.get("turn-id", ""))
    prompt = str(payload.get("prompt", ""))

    if event == "UserPromptSubmit":
        save_prompt(session_id, prompt)
        state, text = "running", "我正在阅读你的问题并处理任务……"
    elif event == "PermissionRequest":
        prompt = load_prompt(session_id)
        state, text = "needs_input", compact_tool(payload)
    elif event in {"Stop", "agent-turn-complete"}:
        prompt = prompt or load_prompt(session_id)
        text = str(
            payload.get("last_assistant_message")
            or payload.get("last-assistant-message")
            or "这轮任务已经完成。"
        )
        state = "ready"
    else:
        state, text = "idle", "Codex 状态已更新。"

    return {
        "action": "codex_event",
        "event": event,
        "state": state,
        "text": text,
        "prompt": prompt,
        "session_id": str(session_id),
        "turn_id": str(turn_id),
    }


def send_event(event: dict) -> None:
    config = json.loads((APP_DIR / "pet_config.json").read_text(encoding="utf-8"))
    port = int(config.get("event_port", 19289))
    data = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.35) as sock:
            sock.sendall(data)
    except OSError:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with PENDING_PATH.open("a", encoding="utf-8") as handle:
            handle.write(data.decode("utf-8"))


def main() -> int:
    try:
        payload = read_payload()
        event_name = str(payload.get("hook_event_name", payload.get("type", "")))
        send_event(transform(payload))
        # Stop requires JSON stdout; an empty JSON object means "continue normally".
        sys.stdout.write("{}")
        sys.stdout.flush()
    except Exception:
        # Hooks must never interfere with the user's Codex turn.
        sys.stdout.write("{}")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

