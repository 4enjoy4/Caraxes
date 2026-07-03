from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "datasets" / "catalog.json"


def hf_dataset_info(repo: str) -> dict:
    url = "https://huggingface.co/api/datasets/" + urllib.parse.quote(repo, safe="/")
    request = urllib.request.Request(url, headers={"User-Agent": "CaraxesPcTrain/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh downloads/likes/gated metadata for pc_train dataset catalog.")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    fetched_at = datetime.now(timezone.utc).isoformat()
    for item in catalog.get("datasets", []):
        repo = item["repo"]
        try:
            info = hf_dataset_info(repo)
        except Exception as exc:
            item.setdefault("hf", {})["refresh_error"] = str(exc)
            print(f"[ERR] {repo}: {exc}")
            continue
        item["hf"] = {
            **item.get("hf", {}),
            "downloads": info.get("downloads"),
            "likes": info.get("likes"),
            "gated": info.get("gated"),
            "private": info.get("private"),
            "tags": (info.get("tags") or [])[:25],
            "last_modified": info.get("lastModified"),
            "fetched_at": fetched_at,
        }
        print(f"[OK] {repo}: downloads={item['hf'].get('downloads')} likes={item['hf'].get('likes')}")

    catalog["generated_at"] = fetched_at
    args.catalog.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {args.catalog}")


if __name__ == "__main__":
    main()
