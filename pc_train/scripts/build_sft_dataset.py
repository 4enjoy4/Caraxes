from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "datasets" / "catalog.json"
OUT_DIR = ROOT / "data"

PROMPT_KEYS = [
    "instruction", "prompt", "question", "problem", "query", "task", "description",
    "input", "text", "title",
]
RESPONSE_KEYS = [
    "output", "response", "answer", "solution", "completion", "code", "accepted_solution",
    "canonical_solution", "explanation",
]


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "safe", "helpful"}
    return False


def clean_text(value: Any, limit: int = 80_000) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value[:5]:
            if isinstance(item, dict):
                parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        value = "\n\n".join(parts)
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value).replace("\r\n", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text[:limit]


def first_present(example: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        if key in example and clean_text(example[key]):
            return clean_text(example[key])
    return ""


def convert_messages(example: dict[str, Any]) -> list[dict[str, str]] | None:
    messages = example.get("messages")
    if isinstance(messages, list) and messages:
        converted = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") or msg.get("from")
            content = msg.get("content") or msg.get("value")
            if role in {"human", "user"}:
                role = "user"
            elif role in {"gpt", "assistant"}:
                role = "assistant"
            if role in {"user", "assistant", "system"} and clean_text(content):
                converted.append({"role": role, "content": clean_text(content)})
        if any(item["role"] == "assistant" for item in converted):
            return converted

    conversations = example.get("conversations")
    if isinstance(conversations, list) and conversations:
        converted = []
        for msg in conversations:
            if not isinstance(msg, dict):
                continue
            role = msg.get("from") or msg.get("role")
            content = msg.get("value") or msg.get("content")
            if role in {"human", "user"}:
                role = "user"
            elif role in {"gpt", "assistant"}:
                role = "assistant"
            if role in {"user", "assistant", "system"} and clean_text(content):
                converted.append({"role": role, "content": clean_text(content)})
        if any(item["role"] == "assistant" for item in converted):
            return converted
    return None


def parse_anthropic_transcript(text: str) -> list[dict[str, str]] | None:
    text = clean_text(text)
    if "\n\nHuman:" not in text and not text.startswith("Human:"):
        return None
    parts = re.split(r"\n\n(Human|Assistant):", "\n\n" + text.lstrip(), flags=re.IGNORECASE)
    messages: list[dict[str, str]] = []
    for index in range(1, len(parts), 2):
        role_name = parts[index].lower()
        content = clean_text(parts[index + 1] if index + 1 < len(parts) else "")
        if not content:
            continue
        role = "user" if role_name == "human" else "assistant"
        messages.append({"role": role, "content": content})
    if messages and messages[-1]["role"] == "assistant":
        return messages
    return None


def convert_preference_example(example: dict[str, Any], source: str) -> dict[str, Any] | None:
    # Anthropic HH-RLHF and many DPO datasets use chosen/rejected transcripts.
    chosen = clean_text(example.get("chosen"))
    if chosen:
        messages = parse_anthropic_transcript(chosen)
        if messages:
            return {"messages": messages, "source": source}
        prompt = first_present(example, PROMPT_KEYS)
        if prompt and len(chosen) > 10 and prompt != chosen:
            return {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": chosen},
                ],
                "source": source,
            }

    # PKU-SafeRLHF style: pick a safe response, preferring the annotated better response.
    if "response_0" in example and "response_1" in example:
        prompt = first_present(example, PROMPT_KEYS)
        if not prompt:
            return None
        candidates = [
            (0, clean_text(example.get("response_0")), truthy(example.get("is_response_0_safe"))),
            (1, clean_text(example.get("response_1")), truthy(example.get("is_response_1_safe"))),
        ]
        better = example.get("better_response_id")
        try:
            better = int(better)
        except Exception:
            better = None
        safe = [item for item in candidates if item[2] and item[1]]
        if not safe:
            return None
        response = next((text for idx, text, _ in safe if idx == better), safe[0][1])
        if len(response) < 10:
            return None
        return {
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ],
            "source": source,
        }

    return None


def convert_example(example: dict[str, Any], source: str) -> dict[str, Any] | None:
    messages = convert_messages(example)
    if messages:
        return {"messages": messages, "source": source}

    preference = convert_preference_example(example, source)
    if preference:
        return preference

    prompt = first_present(example, PROMPT_KEYS)
    response = first_present(example, RESPONSE_KEYS)

    # Common programming benchmark schemas.
    if not prompt and ("question" in example or "starter_code" in example):
        prompt = clean_text(example.get("question")) + "\n\n" + clean_text(example.get("starter_code"))
    if not response and "solutions" in example:
        response = clean_text(example.get("solutions"))
    if not response and "outputs" in example:
        response = clean_text(example.get("outputs"))

    if not prompt or not response or prompt == response:
        return None
    if len(prompt) < 10 or len(response) < 10:
        return None
    return {
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ],
        "source": source,
    }


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: item for item in raw.get("datasets", [])}


def iter_dataset(repo: str, split: str, streaming: bool):
    from datasets import load_dataset

    try:
        return load_dataset(repo, split=split, streaming=streaming)
    except Exception:
        return load_dataset(repo, split="train", streaming=streaming)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a chat-SFT JSONL from selected Hugging Face datasets.")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--datasets", required=True, help="Comma-separated dataset ids from catalog.json")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "merged_code_sft.jsonl")
    parser.add_argument("--split", default="train")
    parser.add_argument("--max-per-dataset", type=int, default=50000)
    parser.add_argument("--streaming", action="store_true", help="Use HF streaming mode; recommended for huge datasets")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    random.seed(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(args.catalog)
    selected = [item.strip() for item in args.datasets.split(",") if item.strip()]
    total = 0
    per_source: dict[str, int] = {}

    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for dataset_id in selected:
            if dataset_id not in catalog:
                raise SystemExit(f"Unknown dataset id: {dataset_id}")
            repo = catalog[dataset_id]["repo"]
            print(f"Loading {dataset_id} ({repo})")
            count = 0
            skipped = 0
            try:
                rows = iter_dataset(repo, args.split, args.streaming)
                for example in rows:
                    converted = convert_example(dict(example), dataset_id)
                    if not converted:
                        skipped += 1
                        continue
                    handle.write(json.dumps(converted, ensure_ascii=False) + "\n")
                    count += 1
                    total += 1
                    if count >= args.max_per_dataset:
                        break
            except Exception as exc:
                print(f"[ERR] {dataset_id}: {exc}")
            per_source[dataset_id] = count
            print(f"[OK] {dataset_id}: wrote={count} skipped={skipped}")

    manifest = {
        "output": str(args.out),
        "total_rows": total,
        "per_source": per_source,
        "selected": selected,
    }
    manifest_path = args.out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {total} rows to {args.out}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
