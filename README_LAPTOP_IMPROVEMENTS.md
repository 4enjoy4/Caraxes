# Caraxes Laptop Improvement Guide

This is the practical path for improving Caraxes on the current laptop without training the model weights.

The local GGUF stays the same, but the assistant can become much more useful through better retrieval, stricter workflows, memory, web/GitHub context, and task-specific prompting.

## What Improves Without Training

These changes are permanent app/workflow improvements:

- Better file retrieval and chunk selection.
- Better prompts for coding, blue team, purple team, and red-team-aware defensive analysis.
- Better use of web docs and GitHub repositories.
- Better memory notes with `remember: ...`.
- Better evaluation tasks so we know if Caraxes is improving.

These do not permanently change the model weights:

- Chat history.
- Memory notes.
- Uploaded files.
- Web/GitHub context.
- Prompt templates.
- Model temperature/context settings.

Actual model knowledge changes only after LoRA/QLoRA training and deployment.

## Best Laptop Settings

Use the current Q4_K model for daily work. It is the best balance for this laptop.

Keep reasoning disabled:

```powershell
$env:CARAXES_REASONING="off"
$env:CARAXES_REASONING_BUDGET="0"
scripts\start_all.ps1
```

Try a larger context only when analyzing big files:

```powershell
$env:CARAXES_N_CTX="12288"
scripts\start_all.ps1
```

If replies become too slow or the backend crashes, return to:

```powershell
$env:CARAXES_N_CTX="8192"
scripts\start_all.ps1
```

Do not expect CPU training to be useful on this laptop. Use the laptop for retrieval, evaluation, dataset building, and app improvements.

## Coding Workflow

Use `/coder` for real project work.

Prompt shape:

```text
You are working as my senior coding assistant.
Goal:
- Explain the current code path.
- Find bugs and risky assumptions.
- Suggest the smallest safe change.
- If editing, return complete files only when needed.

Focus files:
- <paste relative paths>

Question:
<your task>
```

For reviews:

```text
Review this code for bugs, security issues, and missing tests.
Return:
1. Findings ordered by severity.
2. File/path references.
3. Why each issue matters.
4. Minimal fix direction.
5. Tests I should run.
```

For large repos:

```text
First map the repository structure.
Do not edit yet.
Tell me which files you need next and why.
```

For debugging:

```text
Here is the error and the relevant file.
Find the likely root cause.
Give me the smallest fix first, then a better long-term fix.
```

## Web And GitHub Use

Caraxes can read public URLs and GitHub repositories in read-only mode.

Use prompts like:

```text
Read this GitHub repo and summarize the architecture:
https://github.com/OWNER/REPO

Focus on:
- entry points
- dependencies
- security-sensitive code
- tests
- likely weak spots
```

For documentation:

```text
Search/read the current docs for <library/tool>.
Then explain the exact install and usage steps for this project.
Cite the URLs you used.
```

For comparing code to docs:

```text
Read the official docs for <tool>.
Compare them with the attached config/code.
Tell me what is outdated, risky, or missing.
```

## Blue Team Workflow

Use this for SIEM logs, EDR alerts, firewall logs, auth logs, and incident notes.

Prompt:

```text
Act as a blue-team incident responder.
Analyze the attached logs.

Return:
1. Executive summary.
2. Timeline.
3. Suspicious entities: users, hosts, IPs, processes, files, domains.
4. MITRE ATT&CK mapping.
5. Likely false-positive explanations.
6. Containment steps.
7. Detection improvements.
8. Questions / missing evidence.

Do not pretend you saw omitted chunks.
If more chunks are needed, name the exact chunk numbers or search terms.
```

For huge logs:

```text
First create a map of this log:
- time range
- line count
- event types
- top error/warning patterns
- high-risk keywords
- which chunks need deeper review

Do not make final conclusions yet.
```

Then:

```text
Inspect chunks <n-m> and build the incident timeline.
Use evidence from the chunks only.
```

## Purple Team Workflow

Purple team work needs red-team knowledge, but the output should be defensive and authorized.

Prompt:

```text
Create a purple-team validation plan for MITRE ATT&CK technique <TID/name>.

Return:
1. Technique summary.
2. Adversary behavior at TTP level.
3. Lab-safe emulation idea.
4. Required telemetry.
5. Detection logic ideas.
6. Expected alerts.
7. Hardening controls.
8. Success/failure criteria.
9. Follow-up backlog.

Keep it authorized and defensive.
Do not provide malware, credential theft, stealth, or unauthorized intrusion instructions.
```

For testing detections:

```text
Given this detection rule and these sample logs, evaluate:
- what it catches
- what it misses
- false-positive risk
- MITRE mapping
- safer tuning options
- test cases
```

## Red-Team-Aware Defensive Workflow

Blue and purple work need red-team knowledge. Use it at the level of adversary behavior, not harmful automation.

Good prompt:

```text
Explain this attack path from a defender perspective.
Use TTP-level reasoning:
- prerequisites
- attacker decision points
- observable telemetry
- prevention controls
- detection opportunities
- containment steps

Do not provide exploit code, malware, credential theft, stealth, persistence, or evasion instructions.
```

Good prompt:

```text
Map these suspicious events to an attacker kill chain.
For each step, list evidence, missing evidence, and what the blue team should verify next.
```

Avoid prompts that ask for:

- real-world exploitation steps against a target
- phishing kits
- credential theft
- malware
- stealth/evasion
- persistence mechanisms
- bypassing security tools

## Memory Instructions

Use explicit memory for stable preferences and project facts:

```text
remember: For Caraxes, prefer defensive cybersecurity output: blue-team triage, purple-team validation, secure coding, and authorized lab-only red-team context.
```

```text
remember: When analyzing huge files, first map chunks, then inspect relevant chunks, then synthesize with evidence.
```

```text
remember: For code reviews, lead with severity-ordered findings and concrete file references.
```

Memory survives restart because it is stored in SQLite.

## Local Evaluation Set

Keep a small manual test list. Run it after every improvement.

Coding tests:

```text
Review this Python file for bugs and security issues. Return severity-ordered findings.
```

```text
Explain this JavaScript function and suggest safer input validation.
```

```text
Given this stack trace and file, find the smallest fix.
```

Blue-team tests:

```text
Analyze this auth log and build a timeline of suspicious login behavior.
```

```text
Map these PowerShell events to MITRE ATT&CK and suggest detections.
```

Purple-team tests:

```text
Create an authorized lab validation plan for suspicious encoded PowerShell activity.
```

```text
Evaluate this Sigma-like rule against these sample logs.
```

Large-file tests:

```text
This log is too large for one context. First map it by chunks and tell me which chunks matter.
```

Success criteria:

- It admits what chunks/files it did not see.
- It asks for specific next chunks or files.
- It cites concrete evidence.
- It separates facts from guesses.
- It gives defensive next actions.
- It avoids harmful red-team operational instructions.

## Best Laptop Improvements To Implement Next

These are realistic on the laptop and more useful than CPU training.

Applied in the app now:

- Chat workflow mode selector for coding, code review, secure code, blue team, incident,
  purple team, detection engineering, red-team-aware defense, and large-file analysis.
- Lightweight local sparse-vector retrieval for uploaded file chunks, combined with the
  existing SQLite FTS keyword search.
- File maps for large uploads, including included parts, structural samples, high-signal
  parts, and first/last line previews.
- Coder related-file retrieval: the AI still centers the open file, but it now receives a
  capped set of locally selected workspace files when the prompt suggests they matter.

1. Local vector search
   - Current state: lightweight sparse-vector retrieval is implemented.
   - Future upgrade: replace or supplement it with a small local embedding model.
   - Store embeddings for docs, logs, workspace files, and GitHub repo files.

2. Multi-pass large-file analysis
   - Pass 1: profile chunks.
   - Pass 2: retrieve likely relevant chunks.
   - Pass 3: summarize evidence.
   - Pass 4: final answer with citations.

3. Repo indexing
   - Index opened workspace files.
   - Track symbols, imports, dependencies, tests, and config files.
   - Let `/coder` ask for related files automatically.

4. Detection engineering mode
   - Inputs: logs, rule, alert, MITRE technique.
   - Outputs: detection idea, false positives, test cases, tuning notes.

5. Incident timeline mode
   - Inputs: logs and notes.
   - Outputs: timeline, entities, hypotheses, evidence gaps, containment plan.

6. Secure-code review mode
   - Inputs: code files.
   - Outputs: CWE/OWASP mapping, exploitability at a high level, fix, tests.

7. Evaluation dashboard
   - Store prompts and expected qualities.
   - Re-run after model/app changes.
   - Track whether answers got better.

## Operating Rule

For this laptop: do not chase local CPU training first.

Improve Caraxes by making the model see better evidence, use better workflows, and answer in stricter formats.

That will help coding, blue team, purple team, and red-team-aware defensive work much more than a tiny slow CPU fine-tune.
