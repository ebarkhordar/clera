"""Try Clera in 30 seconds — no bot token, no Telegram, no API key.

    python -m app.demo            # you play the contact; Clera plays you
    python -m app.demo --script   # watch a canned conversation instead

Runs the real pipeline (memory store → policy → agent → decision protocol) in
your terminal. With an ANTHROPIC_API_KEY or a local `claude` CLI you get real
replies; with neither, a placeholder shows the flow (and demonstrates the
never-auto-send-a-placeholder rule).
"""

from __future__ import annotations

import argparse
import os
import time

# The demo must never touch a real database: force the in-memory store before
# any app module loads settings.
os.environ["STORE_BACKEND"] = "memory"

from app.agent.secretary import draft_reply  # noqa: E402
from app.config import settings  # noqa: E402
from app.store import repo as store  # noqa: E402

OWNER_ID = 1
CONTACT_ID = 2
CHAT_ID = 100

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
BLUE, GREEN, YELLOW = "\033[34m", "\033[32m", "\033[33m"

_SCRIPT = [
    "hey! are you around this weekend?",
    "we're doing a bbq on saturday, wanna come?",
    "also could you send me the 50 bucks from last time? 😅",
    "ok cool, see you saturday!",
]


def _record(direction: str, sender: int, text: str) -> None:
    store.record_message(
        business_connection_id="demo",
        chat_id=CHAT_ID,
        direction=direction,
        sender_id=sender,
        text=text,
        ts=int(time.time()),
    )
    store.bump_contact("demo", CHAT_ID, name="Sam", ts=int(time.time()))


def _respond(incoming: str) -> None:
    _record("in", CONTACT_ID, incoming)
    history = store.recent_messages("demo", CHAT_ID, settings.history_limit)
    result = draft_reply(
        history=history,
        contact_name="Sam",
        profile="Sam: a good friend of the owner. Casual, friendly tone.",
        tone="friendly and concise",
        tier=settings.default_tier,
    )

    if result.placeholder:
        print(
            f"  {YELLOW}⚠ no LLM configured — this placeholder would NOT be sent; "
            f"the owner would be pinged instead:{RESET}\n"
            f"  {DIM}({result.text}){RESET}\n"
            f"  {DIM}set ANTHROPIC_API_KEY (or install the claude CLI) for real replies{RESET}"
        )
        return
    if result.action == "silent":
        print(f"  {DIM}🤫 Clera stays silent — no reply needed.{RESET}")
        return
    if result.action == "notify":
        print(f"  {YELLOW}👋 escalated to the owner (nothing sent to Sam):{RESET}")
        print(f"  {YELLOW}   “{result.text}”{RESET}")
        return

    _record("out", OWNER_ID, result.text)
    print(f"  {GREEN}{BOLD}You (via Clera):{RESET} {result.text}")
    print(f"  {DIM}model={result.model} · est. cost ${result.cost_usd:.4f}{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", action="store_true", help="run the canned conversation")
    args = parser.parse_args()

    print(f"\n{BOLD}Clera demo{RESET} — you are {BLUE}Sam{RESET}, messaging the owner's phone.")
    print(f"{DIM}Clera answers as the owner: replies, stays silent, or escalates.{RESET}")
    print(f"{DIM}Watch what happens when Sam asks about money. Ctrl-C to quit.{RESET}\n")

    if args.script:
        for line in _SCRIPT:
            print(f"{BLUE}{BOLD}Sam:{RESET} {line}")
            _respond(line)
            print()
        return

    while True:
        try:
            line = input(f"{BLUE}{BOLD}Sam:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}demo over — README has the 5-minute real setup.{RESET}")
            return
        if line:
            _respond(line)
            print()


if __name__ == "__main__":
    main()
