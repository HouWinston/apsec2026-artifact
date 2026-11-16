# Ablation Prompt Templates

The templates below were extracted verbatim on 2026-11-16 from an archived
source snapshot. Source labels identify the original files and constants.
Runtime placeholders and Python `.format` escaping (`{{` and `}}`) are preserved.

The original SYS.5 role wording is retained; the research target is verification
criteria for SYS.2 system requirements. See
[model_config_manifest.md](model_config_manifest.md) for model aliases and
request settings.

## LLM relevance classification

Source label: `poc_ablation.py` / `RELEVANCE_PROMPT`.

Template SHA-256 (UTF-8 string value): `fbd20359c2c72aa8f594656c2a63b9cebe892008c4cea3b4319c4e518832c074`.

```text
You are a requirements engineer for automotive ECU systems.

Determine whether the following issue/complaint is relevant to the given ECU requirement.
"Relevant" means the issue describes a failure mode, edge case, or behavior that could
constitute a missing verification condition for this requirement.

Requirement: {syrs_text}

Issue title: {title}
Issue description: {body}

Answer with ONLY a JSON object: {{"relevant": true}} or {{"relevant": false}}
```

## Ablation generation

Source label: `poc_ablation.py` / `GENERATE_PROMPT`.

Template SHA-256 (UTF-8 string value): `8ad9fc4e7d5dd81264380d48597ae7630e549b4f490bbc06a63fb30664e32cb7`.

```text
You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues/complaints/vulnerabilities in automotive software.
These reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.NEW.1
    Title: <concise test title>
    Method:
      Type: Dynamic
      Technique: <e.g. Boundary Value Analysis, Fault Injection>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. <step>
        3. Verify: <expected outcome>
      Fail: |
        - <failure condition>
    Issue_Source: <issue id that inspired this VC>

Only generate VCs that are genuinely novel (not in golden VCs) and testable at ECU level.
If no useful novel VC can be identified, output: NO_NOVEL_VC_FOUND
```

