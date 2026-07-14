from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


def load_port() -> int:
    with (APP_DIR / "pet_config.json").open("r", encoding="utf-8") as handle:
        return int(json.load(handle)["control_port"])


def send(command: dict) -> None:
    payload = json.dumps(command, ensure_ascii=False).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload, ("127.0.0.1", load_port()))


def main() -> None:
    parser = argparse.ArgumentParser(description="控制 Codex 桌宠")
    subparsers = parser.add_subparsers(dest="command", required=True)

    say = subparsers.add_parser("say", help="显示回答气泡")
    say.add_argument("text")
    say.add_argument("--duration", type=int)

    expression = subparsers.add_parser("expression", help="切换 PNGTuber 表情")
    expression.add_argument("key", choices=list("1234567890") + ["-"])

    state = subparsers.add_parser("state", help="切换任务状态")
    state.add_argument("name", choices=["idle", "running", "needs_input", "ready", "blocked"])
    state.add_argument("--text", default="")

    subparsers.add_parser("open", help="打开 Codex")
    subparsers.add_parser("quit", help="退出桌宠")

    args = parser.parse_args()
    if args.command == "say":
        send({"action": "say", "text": args.text, "duration": args.duration})
    elif args.command == "expression":
        send({"action": "expression", "key": args.key})
    elif args.command == "state":
        send({"action": "state", "state": args.name, "text": args.text})
    elif args.command == "open":
        send({"action": "open_codex"})
    elif args.command == "quit":
        send({"action": "quit"})


if __name__ == "__main__":
    main()

