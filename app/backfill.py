"""Build contact profiles from already-collected history.

Collect-only mode stores messages without ever calling the LLM, so contacts
have rich history but empty profiles. Run this once before switching the
secretary on and every thread starts with full context:

    python -m app.backfill               # profile contacts with >= 5 messages
    python -m app.backfill --min 20      # only substantial threads
    python -m app.backfill --force       # rebuild existing profiles too

Costs one summarization call per contact (fast tier by default).
"""

from __future__ import annotations

import argparse

from app.agent.secretary import summarize_contact
from app.config import settings
from app.store import repo as store


def run(min_messages: int, force: bool) -> None:
    connections = store.list_connections(enabled_only=False)
    if not connections:
        raise SystemExit("No business connections in the database — nothing to backfill.")

    done = skipped = failed = 0
    for conn in connections:
        for contact in store.list_contacts(conn.business_connection_id):
            label = contact.name or f"chat {contact.chat_id}"
            if contact.message_count < min_messages:
                skipped += 1
                continue
            if contact.profile and not force:
                print(f"= {label}: profile exists (use --force to rebuild)")
                skipped += 1
                continue
            history = store.recent_messages(
                conn.business_connection_id, contact.chat_id, settings.history_limit * 3
            )
            profile = summarize_contact(
                history=history,
                contact_name=contact.name,
                existing_profile=contact.profile,
                tier=conn.settings.tier,
            )
            if profile is None:
                print(f"! {label}: summarization failed (no LLM configured?)")
                failed += 1
                continue
            store.update_contact_profile(conn.business_connection_id, contact.chat_id, profile)
            preview = profile.splitlines()[0][:70] if profile else ""
            print(f"✓ {label} ({contact.message_count} msgs): {preview}")
            done += 1

    print(f"\nBackfill complete: {done} profiled, {skipped} skipped, {failed} failed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=int, default=5, help="minimum messages to profile a contact")
    parser.add_argument("--force", action="store_true", help="rebuild existing profiles")
    args = parser.parse_args()
    run(min_messages=args.min, force=args.force)


if __name__ == "__main__":
    main()
