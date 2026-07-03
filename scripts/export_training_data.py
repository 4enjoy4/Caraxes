from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "caraxes.db"
DEFAULT_OUTPUT = ROOT / "training" / "data" / "caraxes_sft.jsonl"

ERROR_MARKERS = (
    "I could not get a response from the local model backend",
    "I could not run the local model yet",
    "Request failed:",
    "[The model returned an empty response.]",
)


def useful_assistant_message(text: str, min_chars: int, include_errors: bool) -> bool:
    clean = (text or "").strip()
    if len(clean) < min_chars:
        return False
    if not include_errors and any(marker in clean for marker in ERROR_MARKERS):
        return False
    return True


def export_jsonl(output: Path, min_assistant_chars: int, include_errors: bool) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select chat_id, role, content, created_at
        from messages
        order by chat_id asc, created_at asc
        """
    ).fetchall()
    conn.close()

    count = 0
    last_user_by_chat: dict[str, str] = {}
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            chat_id = row["chat_id"]
            role = row["role"]
            content = (row["content"] or "").strip()
            if role == "user" and content:
                last_user_by_chat[chat_id] = content
                continue
            if role != "assistant":
                continue
            prompt = last_user_by_chat.get(chat_id, "").strip()
            if not prompt or not useful_assistant_message(content, min_assistant_chars, include_errors):
                continue
            item = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": content},
                ]
            }
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Caraxes chat turns as TRL/Unsloth SFT JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-assistant-chars", type=int, default=120)
    parser.add_argument("--include-errors", action="store_true")
    args = parser.parse_args()

    count = export_jsonl(args.output, args.min_assistant_chars, args.include_errors)
    print(f"Exported {count} examples to {args.output}")
    if count < 50:
        print("Tip: LoRA needs many high-quality examples. Keep using Caraxes and export again later.")


if __name__ == "__main__":
    main()
