from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "training" / "data"
DEFAULT_LOCAL_EXPORT = DATA_DIR / "caraxes_sft.jsonl"
DEFAULT_OUTPUT = DATA_DIR / "caraxes_mixed_sft.jsonl"
DEFAULT_MANIFEST = DATA_DIR / "caraxes_mixed_manifest.json"

SAFE_CYBER_SYSTEM = (
    "You are Caraxes, a coding and cybersecurity assistant. Help with authorized, defensive, educational, "
    "and code-review work only. For red-team topics, focus on threat modeling, controlled lab learning, "
    "vulnerability identification, detection, hardening, and incident response. Refuse malware, credential "
    "theft, phishing, stealth, persistence, evasion, destructive actions, or unauthorized intrusion."
)

HF_SOURCES = {
    "magicoder_oss": {
        "repo": "ise-uiuc/Magicoder-OSS-Instruct-75K",
        "url": "https://huggingface.co/datasets/ise-uiuc/Magicoder-OSS-Instruct-75K/resolve/main/data-oss_instruct-decontaminated.jsonl",
        "license": "mit",
        "kind": "jsonl",
        "default": 600,
    },
    "magicoder_evol": {
        "repo": "ise-uiuc/Magicoder-Evol-Instruct-110K",
        "url": "https://huggingface.co/datasets/ise-uiuc/Magicoder-Evol-Instruct-110K/resolve/main/data-evol_instruct-decontaminated.jsonl",
        "license": "apache-2.0",
        "kind": "jsonl",
        "default": 600,
    },
    "trendyol_cyber_defense": {
        "repo": "Trendyol/Trendyol-Cybersecurity-Instruction-Tuning-Dataset",
        "url": "https://huggingface.co/datasets/Trendyol/Trendyol-Cybersecurity-Instruction-Tuning-Dataset/resolve/main/CyberSec-Dataset_escaped.jsonl",
        "license": "apache-2.0",
        "kind": "jsonl",
        "default": 800,
    },
    "cybernative_secure_code_dpo": {
        "repo": "CyberNative/Code_Vulnerability_Security_DPO",
        "url": "https://huggingface.co/datasets/CyberNative/Code_Vulnerability_Security_DPO/resolve/main/secure_programming_dpo.json",
        "license": "apache-2.0",
        "kind": "jsonl",
        "default": 350,
    },
    "incident_response_playbooks": {
        "repo": "darkknight25/Incident_Response_Playbook_Dataset",
        "url": "https://huggingface.co/datasets/darkknight25/Incident_Response_Playbook_Dataset/resolve/main/incident_response_playbook_dataset.jsonl",
        "license": "mit",
        "kind": "jsonl",
        "default": 175,
    },
    "vulnerable_programming_review": {
        "repo": "darkknight25/Vulnerable_Programming_Dataset",
        "url": "https://huggingface.co/datasets/darkknight25/Vulnerable_Programming_Dataset/resolve/main/vulerable_codes_programming_languages_dataset.jsonl",
        "license": "mit",
        "kind": "json",
        "default": 300,
    },
    "purple_team_metrics": {
        "repo": "Canstralian/Purple-Team-Cybersecurity-Dataset",
        "url": "https://huggingface.co/datasets/Canstralian/Purple-Team-Cybersecurity-Dataset/resolve/main/data/purple_team_dataset.json",
        "license": "mit",
        "kind": "jsonl",
        "default": 150,
    },
    "fenrir_cyber_reasoning": {
        "repo": "AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.1",
        "url": "https://huggingface.co/datasets/AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.1/resolve/main/220426-CyberSec-Dataset_escaped.jsonl",
        "license": "apache-2.0",
        "kind": "jsonl",
        "default": 500,
    },
    "advanced_siem_triage": {
        "repo": "darkknight25/Advanced_SIEM_Dataset",
        "url": "https://huggingface.co/datasets/darkknight25/Advanced_SIEM_Dataset/resolve/main/advanced_siem_dataset.jsonl",
        "license": "mit",
        "kind": "jsonl",
        "default": 500,
    },
    "cve_cwe_triage": {
        "repo": "stasvinokur/cve-and-cwe-dataset-1999-2025",
        "url": "https://huggingface.co/datasets/stasvinokur/cve-and-cwe-dataset-1999-2025/resolve/main/CVE_CWE_2025.csv",
        "license": "cc0-1.0",
        "kind": "csv",
        "default": 500,
    },
    "mitre_attack_enterprise": {
        "repo": "mitre-attack/attack-stix-data",
        "url": "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json",
        "license": "MITRE ATT&CK Terms of Use",
        "kind": "stix_attack",
        "default": 600,
    },
}

DEFENSIVE_TERMS = {
    "analysis",
    "analyze",
    "audit",
    "blue team",
    "contain",
    "defend",
    "defense",
    "detect",
    "detection",
    "forensic",
    "hardening",
    "incident",
    "investigate",
    "mitigate",
    "monitor",
    "patch",
    "prevent",
    "remediate",
    "response",
    "secure",
    "security review",
    "threat model",
    "vulnerability",
}

HIGH_RISK_PHRASES = {
    "build ransomware",
    "create ransomware",
    "write ransomware",
    "phishing kit",
    "credential stealer",
    "steal cookies",
    "steal credentials",
    "reverse shell",
    "disable antivirus",
    "bypass antivirus",
    "evade detection",
    "persistence mechanism",
    "exfiltrate data",
    "data exfiltration script",
    "deploy malware",
    "keylogger",
    "botnet",
}

THINK_RE = re.compile(r"<think>.*?</think>", flags=re.I | re.S)


def strip_thinking(text: str) -> str:
    return THINK_RE.sub("", text or "").strip()


def clean_text(text: Any, limit: int = 80_000) -> str:
    value = strip_thinking("" if text is None else str(text))
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(value) > limit:
        value = value[:limit].rstrip() + "\n[truncated]"
    return value


def has_defensive_context(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in DEFENSIVE_TERMS)


def is_high_risk_without_defense(*parts: str) -> bool:
    text = "\n".join(parts).lower()
    return any(phrase in text for phrase in HIGH_RISK_PHRASES) and not has_defensive_context(text)


def make_example(
    user: str,
    assistant: str,
    source: str,
    system: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    user = clean_text(user, 60_000)
    assistant = clean_text(assistant, 80_000)
    system = clean_text(system or "", 10_000)
    if len(user) < 20 or len(assistant) < 20:
        return None
    if is_high_risk_without_defense(user, assistant):
        return None

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.extend(
        [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    )
    return {"messages": messages, "source": source, "metadata": metadata or {}}


def transform_magicoder_oss(row: dict[str, Any]) -> dict[str, Any] | None:
    problem = row.get("problem")
    solution = row.get("solution")
    lang = row.get("lang") or "code"
    return make_example(
        f"Solve this {lang} programming problem. Explain the approach briefly, then provide the code.\n\n{problem}",
        solution,
        "ise-uiuc/Magicoder-OSS-Instruct-75K",
        metadata={"language": lang},
    )


def transform_magicoder_evol(row: dict[str, Any]) -> dict[str, Any] | None:
    return make_example(
        row.get("instruction", ""),
        row.get("response", ""),
        "ise-uiuc/Magicoder-Evol-Instruct-110K",
    )


def transform_trendyol(row: dict[str, Any]) -> dict[str, Any] | None:
    system = row.get("system") or SAFE_CYBER_SYSTEM
    user = row.get("user") or row.get("instruction") or row.get("prompt")
    assistant = row.get("assistant") or row.get("response") or row.get("output")
    if not has_defensive_context(f"{user}\n{assistant}"):
        return None
    return make_example(
        user,
        assistant,
        "Trendyol/Trendyol-Cybersecurity-Instruction-Tuning-Dataset",
        system=system,
    )


def transform_cybernative(row: dict[str, Any]) -> dict[str, Any] | None:
    lang = row.get("lang") or "code"
    vulnerability = clean_text(row.get("vulnerability", "Security vulnerability"), 500)
    question = clean_text(row.get("question", ""), 20_000)
    chosen = clean_text(row.get("chosen", ""), 30_000)
    if is_high_risk_without_defense(question, chosen, vulnerability):
        return None
    user = (
        f"Perform a defensive secure-code review for this {lang} task.\n\n"
        f"Known vulnerability theme: {vulnerability}\n\n"
        f"Original task:\n{question}\n\n"
        f"Candidate safer implementation from the dataset:\n{chosen}\n\n"
        "Explain the risk, what makes the safer candidate better, and what additional hardening you would apply."
    )
    assistant = (
        f"Security review for {lang}:\n\n"
        f"- Vulnerability theme: {vulnerability}\n"
        "- Treat the candidate implementation as a starting point, not as proof of safety.\n"
        "- Prefer bounded inputs, validation, least privilege, explicit error handling, and tests for abuse cases.\n\n"
        f"Candidate safer implementation:\n{chosen}\n\n"
        "Additional hardening:\n"
        "- Add negative tests that cover malformed, oversized, and unexpected input.\n"
        "- Keep dangerous APIs isolated behind validation or replace them with safer primitives.\n"
        "- Document remaining assumptions and review the implementation in the context of the full application."
    )
    return make_example(
        user,
        assistant,
        "CyberNative/Code_Vulnerability_Security_DPO",
        system=SAFE_CYBER_SYSTEM,
        metadata={"language": lang, "vulnerability": vulnerability},
    )


def transform_ir_playbook(row: dict[str, Any]) -> dict[str, Any] | None:
    incident_type = row.get("incident_type", "Security Incident")
    target_asset = row.get("target_asset", "unknown asset")
    detection_source = row.get("detection_source", "unknown detection source")
    initial_vector = row.get("initial_vector", "unknown")
    user = (
        f"Create a blue-team incident response playbook for a {incident_type} affecting {target_asset}. "
        f"Detection source: {detection_source}. Initial vector: {initial_vector}. "
        "Include MITRE mapping, containment, eradication, recovery, and lessons learned."
    )
    tactics = row.get("tactics_techniques") or []
    steps = row.get("playbook_steps") or []
    lines = [
        f"Incident: {incident_type}",
        f"Severity: {row.get('severity', 'Unknown')}",
        f"Target asset: {target_asset}",
        f"Detection source: {detection_source}",
        f"Initial vector: {initial_vector}",
        "",
        "MITRE ATT&CK mapping:",
    ]
    for item in tactics:
        lines.append(f"- {item.get('tactic', 'Unknown tactic')}: {item.get('technique', 'Unknown technique')}")
    lines.extend(["", "Response phases:"])
    for step in steps:
        tools = ", ".join(step.get("tools") or [])
        lines.append(
            f"- {step.get('phase', 'Phase')}: {step.get('action', 'Action')}"
            + (f" Tools: {tools}." if tools else "")
            + (f" Target time: {step.get('response_time_min')} min." if step.get("response_time_min") else "")
        )
    lines.extend(
        [
            "",
            f"Final status target: {row.get('final_status', 'Resolved or contained')}",
            "Escalate if containment fails, business-critical systems are affected, or regulated data exposure is suspected.",
        ]
    )
    return make_example(
        user,
        "\n".join(lines),
        "darkknight25/Incident_Response_Playbook_Dataset",
        system=SAFE_CYBER_SYSTEM,
        metadata={"incident_type": incident_type, "severity": row.get("severity")},
    )


def transform_vulnerable_programming(row: dict[str, Any]) -> dict[str, Any] | None:
    language = row.get("language", "code")
    vulnerability = row.get("vulnerability", "Security vulnerability")
    description = row.get("description", "")
    code = row.get("code", "")
    references = row.get("references") or []
    user = (
        f"Review this {language} code for security vulnerabilities. Identify the issue, explain impact, "
        "and suggest a safer implementation direction.\n\n"
        f"```{str(language).lower()}\n{code}\n```"
    )
    assistant = (
        f"Finding: {vulnerability}\n\n"
        f"Why it matters: {description}\n\n"
        "Safer direction:\n"
        "- Do not trust external input by default.\n"
        "- Use framework or language primitives that enforce escaping, bounds, parameterization, or validation.\n"
        "- Add regression tests for malicious and malformed inputs.\n"
        "- Review the surrounding authentication, authorization, logging, and error-handling paths.\n"
    )
    if references:
        assistant += "\nReferences:\n" + "\n".join(f"- {ref}" for ref in references[:5])
    return make_example(
        user,
        assistant,
        "darkknight25/Vulnerable_Programming_Dataset",
        system=SAFE_CYBER_SYSTEM,
        metadata={"language": language, "vulnerability": vulnerability},
    )


def transform_purple_metrics(row: dict[str, Any]) -> dict[str, Any] | None:
    detection = row.get("detection_time_seconds")
    response = row.get("response_time_seconds")
    fp_rate = row.get("false_positive_rate")
    missed = row.get("missed_detection_rate")
    if detection is None or response is None:
        return None
    user = (
        "Analyze these purple-team detection metrics and recommend blue-team improvements.\n\n"
        f"Detection time seconds: {detection}\n"
        f"Response time seconds: {response}\n"
        f"False positive rate: {fp_rate}\n"
        f"Missed detection rate: {missed}"
    )
    findings: list[str] = []
    if float(detection) > 180:
        findings.append("Detection is slow; tune telemetry, alert logic, and correlation windows.")
    else:
        findings.append("Detection speed is acceptable; preserve the signal while improving triage quality.")
    if float(response) > 120:
        findings.append("Response is slow; pre-stage containment playbooks and automate low-risk enrichment.")
    else:
        findings.append("Response speed is acceptable; focus on consistency and documentation.")
    if fp_rate is not None and float(fp_rate) > 0.05:
        findings.append("False positives are elevated; add suppression rules only after validating missed-detection impact.")
    if missed is not None and float(missed) > 0.02:
        findings.append("Missed detections are elevated; add coverage tests mapped to MITRE techniques.")
    assistant = "Assessment:\n" + "\n".join(f"- {item}" for item in findings)
    return make_example(
        user,
        assistant,
        "Canstralian/Purple-Team-Cybersecurity-Dataset",
        system=SAFE_CYBER_SYSTEM,
    )


def transform_fenrir(row: dict[str, Any]) -> dict[str, Any] | None:
    user = row.get("user") or row.get("User") or row.get("instruction") or row.get("prompt")
    assistant = row.get("assistant") or row.get("Assistant") or row.get("response") or row.get("output")
    if not user or not assistant:
        return None
    text = f"{user}\n{assistant}"
    if not has_defensive_context(text):
        return None
    return make_example(
        user,
        assistant,
        "AlicanKiraz0/Cybersecurity-Dataset-Fenrir-v2.1",
        system=SAFE_CYBER_SYSTEM,
    )


def transform_advanced_siem(row: dict[str, Any]) -> dict[str, Any] | None:
    event_type = row.get("event_type", "unknown")
    severity = row.get("severity", "unknown")
    source = row.get("source", "unknown")
    raw_log = row.get("raw_log") or row.get("description") or ""
    metadata = row.get("advanced_metadata") or {}
    analytics = row.get("behavioral_analytics") or {}
    user = (
        "Triage this SIEM event as a blue-team analyst. Identify likely meaning, priority, enrichment steps, "
        "containment criteria, and detection improvements.\n\n"
        f"Event type: {event_type}\n"
        f"Severity: {severity}\n"
        f"Source: {source}\n"
        f"User: {row.get('user', 'unknown')}\n"
        f"Action: {row.get('action', 'unknown')}\n"
        f"Object: {row.get('object', 'unknown')}\n"
        f"Parent process: {row.get('parent_process', 'unknown')}\n"
        f"Risk score: {metadata.get('risk_score', 'unknown')}\n"
        f"Confidence: {metadata.get('confidence', 'unknown')}\n"
        f"Baseline deviation: {analytics.get('baseline_deviation', 'unknown')}\n"
        f"Sequence anomaly: {analytics.get('sequence_anomaly', 'unknown')}\n"
        f"Raw log: {raw_log}"
    )
    assistant = (
        f"Initial triage: Treat this as a {severity} {event_type} event from {source}.\n\n"
        "What to check:\n"
        f"- Validate whether `{row.get('user', 'unknown')}` normally performs `{row.get('action', 'unknown')}` against `{row.get('object', 'unknown')}`.\n"
        f"- Correlate parent process `{row.get('parent_process', 'unknown')}` with endpoint, identity, and network telemetry.\n"
        "- Compare risk score, confidence, baseline deviation, and sequence anomaly with nearby events.\n"
        "- Search for same object, user, process lineage, and source host in the last 24 hours.\n\n"
        "Containment criteria:\n"
        "- Isolate the endpoint or disable the account if there is confirmed malicious process lineage, impossible travel, credential abuse, or repeated high-risk activity.\n\n"
        "Detection improvement:\n"
        "- Add suppression only after validating benign baseline behavior.\n"
        "- Add correlation on user + process lineage + object sensitivity + repeated anomaly score."
    )
    return make_example(
        user,
        assistant,
        "darkknight25/Advanced_SIEM_Dataset",
        system=SAFE_CYBER_SYSTEM,
        metadata={"event_type": event_type, "severity": severity},
    )


def transform_cve_cwe(row: dict[str, Any]) -> dict[str, Any] | None:
    cve_id = row.get("CVE-ID") or row.get("cve_id") or row.get("CVE")
    description = row.get("DESCRIPTION") or row.get("description") or ""
    cwe = row.get("CWE-ID") or row.get("cwe") or "unknown"
    severity = row.get("SEVERITY") or row.get("severity") or "unknown"
    cvss = row.get("CVSS-V4") or row.get("CVSS-V3") or row.get("CVSS-V2") or "unknown"
    if not cve_id or not description:
        return None
    user = (
        f"Analyze {cve_id} for vulnerability management and blue-team prioritization.\n\n"
        f"Severity: {severity}\nCVSS: {cvss}\nCWE: {cwe}\nDescription: {description}"
    )
    assistant = (
        f"{cve_id} triage:\n\n"
        f"- Severity: {severity}; CVSS: {cvss}; weakness: {cwe}.\n"
        f"- Summary: {description}\n"
        "- Prioritization: raise priority when the affected asset is internet-facing, business-critical, reachable by untrusted users, or has known exploitation.\n"
        "- Blue-team actions: identify affected inventory, validate exposed services, check vendor advisories, deploy patches or mitigations, and monitor logs for exploitation attempts.\n"
        "- Detection direction: build queries around affected product names, protocol paths, suspicious error patterns, exploit preconditions, and post-exploitation behavior.\n"
        "- Purple-team use: emulate only in an authorized lab and measure whether prevention, detection, containment, and recovery controls fire as expected."
    )
    return make_example(
        user,
        assistant,
        "stasvinokur/cve-and-cwe-dataset-1999-2025",
        system=SAFE_CYBER_SYSTEM,
        metadata={"cve": cve_id, "cwe": cwe, "severity": severity},
    )


def external_id_for_attack_object(row: dict[str, Any]) -> str:
    for ref in row.get("external_references") or []:
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
            return ref["external_id"]
    return row.get("id", "unknown")


def transform_mitre_attack(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("type") != "attack-pattern" or row.get("revoked") or row.get("x_mitre_deprecated"):
        return None
    technique_id = external_id_for_attack_object(row)
    name = row.get("name", "Unknown technique")
    description = clean_text(row.get("description", ""), 12_000)
    detection = clean_text(row.get("x_mitre_detection", ""), 8_000)
    platforms = ", ".join(row.get("x_mitre_platforms") or [])
    phases = ", ".join(
        phase.get("phase_name", "")
        for phase in row.get("kill_chain_phases") or []
        if phase.get("phase_name")
    )
    if not description:
        return None
    user = (
        f"Map this MITRE ATT&CK technique into a purple-team plan and blue-team detection guidance.\n\n"
        f"Technique: {technique_id} {name}\n"
        f"Tactics/phases: {phases or 'unknown'}\n"
        f"Platforms: {platforms or 'unknown'}\n\n"
        f"ATT&CK description:\n{description}"
    )
    assistant = (
        f"Technique: {technique_id} {name}\n\n"
        f"Adversary behavior to understand: {description[:1800]}\n\n"
        f"Tactics/phases: {phases or 'unknown'}\n"
        f"Platforms: {platforms or 'unknown'}\n\n"
        "Blue-team detection guidance:\n"
        + (detection if detection else "- Build detections around the described behavior, command lineage, identity use, file/registry changes, network destinations, and unusual parent-child process relationships.")
        + "\n\nPurple-team validation:\n"
        "- Emulate only in an authorized lab or approved assessment scope.\n"
        "- Define expected telemetry before testing.\n"
        "- Measure prevention, alert fidelity, triage speed, containment readiness, and recovery evidence.\n"
        "- Convert gaps into detection engineering, hardening, and logging backlog items."
    )
    return make_example(
        user,
        assistant,
        "mitre-attack/attack-stix-data",
        system=SAFE_CYBER_SYSTEM,
        metadata={"technique_id": technique_id, "name": name, "platforms": platforms},
    )


TRANSFORMS: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {
    "magicoder_oss": transform_magicoder_oss,
    "magicoder_evol": transform_magicoder_evol,
    "trendyol_cyber_defense": transform_trendyol,
    "cybernative_secure_code_dpo": transform_cybernative,
    "incident_response_playbooks": transform_ir_playbook,
    "vulnerable_programming_review": transform_vulnerable_programming,
    "purple_team_metrics": transform_purple_metrics,
    "fenrir_cyber_reasoning": transform_fenrir,
    "advanced_siem_triage": transform_advanced_siem,
    "cve_cwe_triage": transform_cve_cwe,
    "mitre_attack_enterprise": transform_mitre_attack,
}


def iter_jsonl_url(url: str, scan_limit: int) -> Iterable[dict[str, Any]]:
    seen = 0
    with httpx.stream("GET", url, follow_redirects=True, timeout=120, headers={"User-Agent": "CaraxesTrainingBuilder/1.0"}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if scan_limit and seen >= scan_limit:
                break
            line = line.strip()
            if not line:
                continue
            seen += 1
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_json_url(url: str) -> Iterable[dict[str, Any]]:
    response = httpx.get(url, follow_redirects=True, timeout=120, headers={"User-Agent": "CaraxesTrainingBuilder/1.0"})
    response.raise_for_status()
    text = response.text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Some community datasets contain invalid JSON escapes inside code strings.
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        fixed = re.sub(r"(\n\s*\})(\s*\n\s*\{)", r"\1,\2", fixed)
        data = json.loads(fixed)
    if isinstance(data, list):
        yield from (item for item in data if isinstance(item, dict))
    elif isinstance(data, dict):
        values = data.values()
        for value in values:
            if isinstance(value, dict):
                yield value
            elif isinstance(value, list):
                yield from (item for item in value if isinstance(item, dict))


def iter_csv_url(url: str, scan_limit: int) -> Iterable[dict[str, Any]]:
    response = httpx.get(url, follow_redirects=True, timeout=120, headers={"User-Agent": "CaraxesTrainingBuilder/1.0"})
    response.raise_for_status()
    reader = csv.DictReader(response.text.splitlines())
    for index, row in enumerate(reader, start=1):
        if scan_limit and index > scan_limit:
            break
        yield dict(row)


def iter_stix_attack_url(url: str) -> Iterable[dict[str, Any]]:
    response = httpx.get(url, follow_redirects=True, timeout=180, headers={"User-Agent": "CaraxesTrainingBuilder/1.0"})
    response.raise_for_status()
    data = response.json()
    for item in data.get("objects", []):
        if isinstance(item, dict):
            yield item


def reservoir_sample(items: Iterable[dict[str, Any]], limit: int, rng: random.Random) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    sample: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if len(sample) < limit:
            sample.append(item)
            continue
        replacement = rng.randrange(index)
        if replacement < limit:
            sample[replacement] = item
    return sample


def read_local_examples(path: Path, limit: int, rng: random.Random) -> list[dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []

    def rows() -> Iterable[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("messages"):
                    item.setdefault("source", "local_caraxes_chats")
                    item.setdefault("metadata", {})
                    yield item

    return reservoir_sample(rows(), limit, rng)


def collect_source(source_key: str, max_examples: int, scan_limit: int, rng: random.Random) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = HF_SOURCES[source_key]
    transform = TRANSFORMS[source_key]
    if source["kind"] == "jsonl":
        raw_rows = iter_jsonl_url(source["url"], scan_limit)
    elif source["kind"] == "csv":
        raw_rows = iter_csv_url(source["url"], scan_limit)
    elif source["kind"] == "stix_attack":
        raw_rows = iter_stix_attack_url(source["url"])
    else:
        raw_rows = iter_json_url(source["url"])
    transformed: list[dict[str, Any]] = []
    raw_seen = 0
    valid_seen = 0
    for row in raw_rows:
        raw_seen += 1
        item = transform(row)
        if not item:
            continue
        valid_seen += 1
        if len(transformed) < max_examples:
            transformed.append(item)
            continue
        replacement = rng.randrange(valid_seen)
        if replacement < max_examples:
            transformed[replacement] = item
    stats = {
        "repo": source["repo"],
        "license": source["license"],
        "requested": max_examples,
        "raw_seen": raw_seen,
        "valid_seen": valid_seen,
        "kept": len(transformed),
        "url": source["url"],
    }
    return transformed, stats


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Caraxes coding + defensive cybersecurity SFT corpus from Hugging Face datasets.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--local-export", type=Path, default=DEFAULT_LOCAL_EXPORT)
    parser.add_argument("--local-max", type=int, default=200)
    parser.add_argument("--scan-limit", type=int, default=30_000, help="Max rows to scan per JSONL source; 0 means scan entire source.")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--source", action="append", choices=sorted(HF_SOURCES), help="Limit to one or more source keys.")
    for key, config in HF_SOURCES.items():
        parser.add_argument(f"--max-{key.replace('_', '-')}", type=int, default=int(config["default"]))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    selected_sources = args.source or list(HF_SOURCES)
    all_rows: list[dict[str, Any]] = []
    manifest: dict[str, Any] = {
        "output": str(args.output),
        "seed": args.seed,
        "scan_limit": args.scan_limit,
        "sources": {},
        "notes": [
            "Cybersecurity examples are filtered and transformed toward authorized defensive, code-review, incident-response, and purple-team use.",
            "Review dataset licenses and content before publishing or redistributing a trained model.",
        ],
    }

    local_rows = read_local_examples(args.local_export, args.local_max, rng)
    all_rows.extend(local_rows)
    manifest["sources"]["local_caraxes_chats"] = {
        "path": str(args.local_export),
        "requested": args.local_max,
        "kept": len(local_rows),
    }

    for key in selected_sources:
        max_examples = getattr(args, f"max_{key}")
        rows, stats = collect_source(key, max_examples, args.scan_limit, rng)
        all_rows.extend(rows)
        manifest["sources"][key] = stats
        print(f"{key}: kept {stats['kept']} examples from {stats['repo']}")

    rng.shuffle(all_rows)
    write_jsonl(args.output, all_rows)
    manifest["total_examples"] = len(all_rows)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(all_rows)} examples to {args.output}")
    print(f"Wrote manifest to {args.manifest}")


if __name__ == "__main__":
    main()
