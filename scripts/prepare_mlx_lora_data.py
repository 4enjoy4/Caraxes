from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "training" / "data" / "caraxes_mixed_sft.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "training" / "mlx_lora_data"


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages = item.get("messages")
            if isinstance(messages, list) and len(messages) >= 2:
                rows.append({"messages": messages})
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Caraxes chat JSONL for mlx_lm.lora.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--valid-ratio", type=float, default=0.03)
    parser.add_argument("--test-ratio", type=float, default=0.02)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()

    rows = load_rows(args.input)
    if not rows:
        raise SystemExit(f"No usable rows found in {args.input}")

    rng = random.Random(args.seed)
    rng.shuffle(rows)
    total = len(rows)
    test_count = max(1, int(total * args.test_ratio))
    valid_count = max(1, int(total * args.valid_ratio))
    test_rows = rows[:test_count]
    valid_rows = rows[test_count : test_count + valid_count]
    train_rows = rows[test_count + valid_count :]

    write_jsonl(args.output_dir / "train.jsonl", train_rows)
    write_jsonl(args.output_dir / "valid.jsonl", valid_rows)
    write_jsonl(args.output_dir / "test.jsonl", test_rows)

    print(f"Input rows: {total}")
    print(f"Train rows: {len(train_rows)} -> {args.output_dir / 'train.jsonl'}")
    print(f"Valid rows: {len(valid_rows)} -> {args.output_dir / 'valid.jsonl'}")
    print(f"Test rows: {len(test_rows)} -> {args.output_dir / 'test.jsonl'}")


if __name__ == "__main__":
    main()
