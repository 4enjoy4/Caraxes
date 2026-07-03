from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
REPO_ID = "huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-GGUF"
DEFAULT_FILENAME = "Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-Q4_K.gguf"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the Caraxes GGUF model into the project models folder.")
    parser.add_argument("--filename", default=DEFAULT_FILENAME, help="GGUF filename from the Hugging Face repo.")
    parser.add_argument("--include-mmproj", action="store_true", help="Also download mmproj-model-bf16.gguf if you want to experiment with image-capable llama.cpp setups.")
    args = parser.parse_args()

    target_dir = ROOT / "models" / REPO_ID.split("/")[-1]
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {REPO_ID}/{args.filename}")
    path = hf_hub_download(
        repo_id=REPO_ID,
        filename=args.filename,
        local_dir=target_dir,
    )
    print(f"Saved model to: {path}")

    if args.include_mmproj:
        print("Downloading mmproj-model-bf16.gguf")
        mmproj = hf_hub_download(
            repo_id=REPO_ID,
            filename="mmproj-model-bf16.gguf",
            local_dir=target_dir,
        )
        print(f"Saved mmproj to: {mmproj}")


if __name__ == "__main__":
    main()
