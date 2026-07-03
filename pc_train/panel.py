from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "datasets" / "catalog.json"
MODEL_CATALOG_PATH = ROOT / "models" / "model_catalog.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(cmd: list[str]) -> None:
    print("\n$ " + " ".join(cmd))
    subprocess.run(cmd, check=False)


def print_datasets(selected: set[str]) -> None:
    catalog = load_json(CATALOG_PATH)
    print("\nDatasets")
    print("--------")
    for index, item in enumerate(catalog["datasets"], start=1):
        mark = "*" if item["id"] in selected else " "
        hf = item.get("hf", {})
        stage = item.get("stage", "coding")
        print(
            f"{index:2d}. [{mark}] {item['id']:<24} "
            f"stage={stage:<26} prio={item['priority']} downloads={hf.get('downloads')} likes={hf.get('likes')} "
            f"default={item.get('default')} repo={item['repo']}"
        )


def choose_datasets(default_only: bool = True) -> set[str]:
    catalog = load_json(CATALOG_PATH)
    selected = {item["id"] for item in catalog["datasets"] if item.get("default")} if default_only else set()
    while True:
        print_datasets(selected)
        print("\nType numbers like 1,2,5 to toggle; 'a' all; 'd' defaults; 'c' continue.")
        choice = input("> ").strip().lower()
        if choice == "c":
            return selected
        if choice == "a":
            selected = {item["id"] for item in catalog["datasets"]}
            continue
        if choice == "d":
            selected = {item["id"] for item in catalog["datasets"] if item.get("default")}
            continue
        for part in choice.split(","):
            part = part.strip()
            if not part.isdigit():
                continue
            index = int(part) - 1
            if 0 <= index < len(catalog["datasets"]):
                dataset_id = catalog["datasets"][index]["id"]
                if dataset_id in selected:
                    selected.remove(dataset_id)
                else:
                    selected.add(dataset_id)


def choose_model() -> str:
    catalog = load_json(MODEL_CATALOG_PATH)
    print("\nModels")
    print("------")
    for index, item in enumerate(catalog["models"], start=1):
        print(f"{index}. {item['id']:<24} {item['class']:<24} repo={item['repo']}")
        print(f"   {item['why']}")
    choice = input("Choose model number or paste HF repo [1]: ").strip()
    if not choice:
        return catalog["models"][0]["id"]
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(catalog["models"]):
            return catalog["models"][index]["id"]
    return choice


def main() -> None:
    selected = {item["id"] for item in load_json(CATALOG_PATH)["datasets"] if item.get("default")}
    while True:
        print("\nCaraxes PC Train Panel")
        print("======================")
        print("1. Select datasets")
        print("2. Refresh Hugging Face downloads/likes")
        print("3. Build merged SFT JSONL")
        print("4. Generate Axolotl QLoRA config")
        print("5. Show recommended training commands")
        print("q. Quit")
        choice = input("> ").strip().lower()
        if choice == "q":
            return
        if choice == "1":
            selected = choose_datasets(default_only=False)
        elif choice == "2":
            run([sys.executable, str(ROOT / "scripts" / "refresh_hf_metadata.py")])
        elif choice == "3":
            max_rows = input("Max rows per dataset [50000]: ").strip() or "50000"
            streaming = input("Use streaming mode for huge datasets? [y/N]: ").strip().lower() == "y"
            cmd = [
                sys.executable,
                str(ROOT / "scripts" / "build_sft_dataset.py"),
                "--datasets",
                ",".join(sorted(selected)),
                "--max-per-dataset",
                max_rows,
                "--out",
                str(ROOT / "data" / "merged_code_sft.jsonl"),
            ]
            if streaming:
                cmd.append("--streaming")
            run(cmd)
        elif choice == "4":
            model = choose_model()
            seq = input("Sequence length [8192, try 16384 later]: ").strip() or "8192"
            run([
                sys.executable,
                str(ROOT / "scripts" / "make_axolotl_config.py"),
                "--model",
                model,
                "--sequence-len",
                seq,
                "--dataset",
                str(ROOT / "data" / "merged_code_sft.jsonl"),
                "--out",
                str(ROOT / "configs" / "axolotl_qlora.yaml"),
            ])
        elif choice == "5":
            print("\nInstall:")
            print("  python -m venv .venv-train")
            print("  .venv-train\\Scripts\\activate        # Windows")
            print("  source .venv-train/bin/activate      # Linux")
            print("  pip install -r pc_train/requirements-pc-train.txt")
            print("\nBuild data:")
            print("  python pc_train/panel.py")
            print("\nTrain:")
            print("  accelerate launch -m axolotl.cli.train pc_train/configs/axolotl_qlora.yaml")
            print("\nRecommended order:")
            print("  1) de-abliteration repair + secure coding smoke run")
            print("  2) larger coding reasoning SFT")
            print("  3) optional DPO/ORPO pass with secure-code preference data")
            print("\nMonitor:")
            print("  tensorboard --logdir pc_train/outputs")


if __name__ == "__main__":
    main()
