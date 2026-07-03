from __future__ import annotations

import os
from pathlib import Path

from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import FastLanguageModel


MODEL_NAME = os.environ.get(
    "CARAXES_TRAIN_MODEL",
    "huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated",
)
DATA_PATH = os.environ.get("CARAXES_SFT_DATA", "training/data/caraxes_mixed_sft.jsonl")
OUTPUT_DIR = os.environ.get("CARAXES_LORA_OUTPUT", "outputs/caraxes-qwythos-lora")
MAX_SEQ_LENGTH = int(os.environ.get("CARAXES_TRAIN_SEQ_LEN", "4096"))


def main() -> None:
    if not Path(DATA_PATH).exists():
        raise SystemExit(f"Training dataset not found: {DATA_PATH}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=int(os.environ.get("CARAXES_LORA_R", "16")),
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=int(os.environ.get("CARAXES_LORA_ALPHA", "32")),
        lora_dropout=float(os.environ.get("CARAXES_LORA_DROPOUT", "0")),
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=int(os.environ.get("CARAXES_TRAIN_SEED", "3407")),
    )

    dataset = load_dataset("json", data_files=DATA_PATH, split="train")

    def format_example(example: dict) -> dict:
        return {
            "text": tokenizer.apply_chat_template(
                example["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        }

    dataset = dataset.map(format_example, remove_columns=dataset.column_names)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        packing=True,
        args=TrainingArguments(
            per_device_train_batch_size=int(os.environ.get("CARAXES_BATCH_SIZE", "1")),
            gradient_accumulation_steps=int(os.environ.get("CARAXES_GRAD_ACCUM", "8")),
            warmup_steps=int(os.environ.get("CARAXES_WARMUP_STEPS", "20")),
            max_steps=int(os.environ.get("CARAXES_MAX_STEPS", "300")),
            learning_rate=float(os.environ.get("CARAXES_LR", "2e-4")),
            fp16=True,
            logging_steps=5,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=int(os.environ.get("CARAXES_TRAIN_SEED", "3407")),
            output_dir=OUTPUT_DIR,
            report_to="none",
            save_strategy="steps",
            save_steps=100,
        ),
    )
    trainer.train()

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    if os.environ.get("CARAXES_SAVE_GGUF", "0").lower() in {"1", "true", "yes"}:
        gguf_dir = OUTPUT_DIR.rstrip("/\\") + "-gguf"
        model.save_pretrained_gguf(gguf_dir, tokenizer, quantization_method="q4_k_m")
        print(f"Saved GGUF to {gguf_dir}")

    print(f"Saved LoRA adapter to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
