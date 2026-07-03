# Caraxes Training Plan

Caraxes currently runs a GGUF file locally. GGUF is for inference, not training, so the free training path is:

1. Export high-quality Caraxes chats into JSONL.
2. Fine-tune the non-GGUF model with LoRA/QLoRA on a free notebook GPU.
3. Download the LoRA adapter, or merge/quantize a new GGUF if the notebook has enough time and disk.

The matching non-GGUF model repo is:

```text
huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated
```

## Export Your Data

From the project folder:

```powershell
.\.venv\Scripts\python.exe scripts\export_training_data.py
```

The exporter writes:

```text
training\data\caraxes_sft.jsonl
```

Do not train on broken answers. The exporter skips obvious backend failures by default.

If this only exports a tiny number of examples, that is normal at the beginning. It only contains finished chats from your local Caraxes database. A model does not become a coding specialist from 9 conversations; it needs hundreds to thousands of high-quality examples.

## Build The Hugging Face Coding + Cyber Corpus

To add public Hugging Face data for coding, secure code review, defensive cybersecurity, incident response, and purple-team analysis:

```powershell
.\.venv\Scripts\python.exe scripts\build_hf_training_corpus.py
```

This writes:

```text
training\data\caraxes_mixed_sft.jsonl
training\data\caraxes_mixed_manifest.json
```

Default sources:

- `ise-uiuc/Magicoder-OSS-Instruct-75K` for coding problems and solutions.
- `ise-uiuc/Magicoder-Evol-Instruct-110K` for coding instruction following.
- `Trendyol/Trendyol-Cybersecurity-Instruction-Tuning-Dataset` for defensive cybersecurity instruction tuning.
- `CyberNative/Code_Vulnerability_Security_DPO` transformed into defensive secure-code-review examples.
- `darkknight25/Incident_Response_Playbook_Dataset` for blue-team incident response playbooks.
- `darkknight25/Vulnerable_Programming_Dataset` transformed into vulnerability review examples.
- `Canstralian/Purple-Team-Cybersecurity-Dataset` transformed into purple-team metric analysis examples.
- `AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.1` for cybersecurity causal reasoning and threat analysis.
- `darkknight25/Advanced_SIEM_Dataset` transformed into blue-team SIEM triage examples.
- `stasvinokur/cve-and-cwe-dataset-1999-2025` transformed into CVE/CWE prioritization and detection examples.
- `mitre-attack/attack-stix-data` transformed from official Enterprise ATT&CK STIX techniques into purple-team plans and blue-team detection guidance.

The builder samples data and filters/transforms cyber examples toward authorized defensive use. Red-team knowledge is included through ATT&CK/TTP mapping, adversary behavior, lab validation, detection, and mitigation. It is not designed to train malware, phishing, credential theft, stealth, evasion, or unauthorized intrusion behavior.

Useful controls:

```powershell
# Scan more rows per source for a better random sample.
.\.venv\Scripts\python.exe scripts\build_hf_training_corpus.py --scan-limit 100000

# Build only coding data.
.\.venv\Scripts\python.exe scripts\build_hf_training_corpus.py --source magicoder_oss --source magicoder_evol

# Build only defensive cyber data.
.\.venv\Scripts\python.exe scripts\build_hf_training_corpus.py --source trendyol_cyber_defense --source incident_response_playbooks --source vulnerable_programming_review
```

## Free Cloud Route

Use Colab or Kaggle first. GPU access is free but not guaranteed, so keep runs small and checkpoint often.

Suggested notebook setup:

```python
!pip install -U unsloth trl transformers datasets accelerate bitsandbytes
!git clone https://github.com/YOURNAME/Caraxes.git || true
%cd Caraxes
```

Upload `training/data/caraxes_mixed_sft.jsonl`, then run:

```python
!python training/caraxes_unsloth_qlora.py
```

Useful small-run settings:

```python
%env CARAXES_TRAIN_SEQ_LEN=4096
%env CARAXES_MAX_STEPS=300
%env CARAXES_BATCH_SIZE=1
%env CARAXES_GRAD_ACCUM=8
```

If the free GPU runs out of memory, lower `CARAXES_TRAIN_SEQ_LEN` to `2048`, then reduce `CARAXES_LORA_R` to `8`.

## What To Train

Fine-tune behavior, not giant documents. For 500-page PDFs and multi-million-line logs, Caraxes should use retrieval, chunking, and memory. Good training examples should teach it how to:

- ask for the right slices of a huge file,
- summarize evidence without pretending it saw omitted chunks,
- debug Python, Java, JavaScript, C/C++, assembly, shell, SQL, and config files,
- produce careful code-review findings with file names and concrete fixes,
- explain binary/hex evidence when only metadata and samples are available.

## After Training

Download the output adapter folder, then either:

- load it in a compatible Python inference stack, or
- merge and export a GGUF from the notebook if there is enough free runtime.

Set `CARAXES_SAVE_GGUF=1` before running the training script to try Unsloth GGUF export.
