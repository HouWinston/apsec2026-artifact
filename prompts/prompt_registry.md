# Prompt Registry

These are the exact Python string values extracted by AST inspection from a
local archived source snapshot on 2026-11-16. This documents the inspected
snapshot; it does not establish the exact prompt sent in every historical run.
Source filenames and constant names below are provenance labels, not files
distributed with this public package.

The text inside each code fence is preserved without rewriting, including
punctuation, trailing newlines, the original SYS.5 role wording, and Python
`.format` escaping (`{{` and `}}` represent literal braces after formatting).
The research target is verification criteria for SYS.2 system requirements.
Runtime requirement text, golden VCs, evidence context, identifiers, and generated
outputs substituted into the placeholders are not distributed here.

These templates are methodological material, not an executable pipeline or proof
of semantic correctness. Model aliases and parameters are documented separately
in [model_config_manifest.md](model_config_manifest.md).

## Stage 2 - Channel A (GitHub)

Source label: `poc_pipeline.py` / `DISTILL_PROMPT`.

Template SHA-256 (UTF-8 string value): `fbbe2f8700630b86af2e64d8973f5a9553bdc832b57008d1871635c5a1e43483`.

```text
You are an automotive embedded systems expert.
Extract the technical essence from this GitHub issue report.

Output ONLY a JSON object with these three fields:
{{
  "trigger": "what system state or input caused the issue (protocol service, service ID, conditions)",
  "behavior": "what protocol or system behavior was expected vs observed",
  "fault_mode": "the failure category: e.g. missing response, wrong NRC, timing violation, silent failure, protocol non-compliance"
}}

If the issue is not about automotive protocol behavior (e.g., pure Python packaging, docs), output:
{{"trigger": null, "behavior": null, "fault_mode": null}}

Issue title: {title}
Issue body: {body}
```

## Stage 2 - Channel B (NHTSA)

Source label: `poc_nhtsa.py` / `NHTSA_DISTILL_PROMPT`.

Template SHA-256 (UTF-8 string value): `5c0cf695b35cbd3c6453b715efe87a4450acabc07547698d83d9013692feb8e4`.

```text
You are an automotive ECU requirements engineer.
Extract the technical essence from this NHTSA vehicle complaint.

Output ONLY a JSON object:
{{
  "trigger": "what operational condition or user action triggered the failure",
  "behavior": "what the system was expected to do vs what actually happened",
  "fault_mode": "failure category: e.g. no-response, false-activation, timing-violation, state-stuck, unexpected-lock, sensor-error"
}}

If this complaint is not related to automotive ECU system behavior (e.g., cosmetic, noise, smell), output:
{{"trigger": null, "behavior": null, "fault_mode": null}}

Component: {component}
Complaint: {summary}
```

## Stage 4 - Channel A (GitHub)

Source label: `poc_pipeline.py` / `GENERATE_PROMPT`.

Template SHA-256 (UTF-8 string value): `018392a511becdd6513f89720636dd7629d9989c6a2bb32a1f3cfc600650b689`.

```text
You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues in open-source automotive protocol software.
These issues reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive protocol software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in this YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.NEW.1
    Title: <concise test title>
    Method:
      Type: Dynamic  # or Static
      Technique: <e.g. Boundary Value Analysis, Equivalence Partitioning, Fault Injection>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. <step>
        3. Verify: <expected outcome>
      Fail: |
        - <condition that constitutes failure>
    Issue_Source: <repo#issue_id that inspired this VC>

Only generate VCs that are:
1. Genuinely testing the SYRS requirement (not testing the protocol library)
2. Not redundant with existing golden VCs
3. Inspired by a real failure pattern from the issues above
4. Testable at ECU system integration test level

If no genuinely useful missing VC can be identified from these issues, output:
NO_NOVEL_VC_FOUND
```

## Stage 4 - Channel B (NHTSA)

Source label: `poc_nhtsa.py` / `NHTSA_GENERATE_PROMPT`.

Template SHA-256 (UTF-8 string value): `31d2a25cdb1c836f67c7721c62e2b96fc25c5bd9ae6bda5eb863520c65d20a4f`.

```text
You are an automotive ECU system test engineer (ASPICE SYS.5).

Generate MISSING verification conditions for an automotive ECU body/control system requirement.
The insight comes from real NHTSA vehicle owner complaints — these are real-world corner cases
that specification authors typically miss.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (DO NOT repeat):
{golden_vcs}

Related NHTSA complaints (real-world failure corner cases):
{complaints_context}

Generate 1-2 additional VCs in YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.NHTSA.1
    Title: <test title>
    Method:
      Type: Dynamic
      Technique: <e.g. Fault Injection, Boundary Value Analysis, State Transition>
    Pass_Fail_Criteria:
      Pass: |
        1. <setup>
        2. <action>
        3. Verify: <expected ECU response>
      Fail: |
        - <failure condition>
    Source_Complaint: ODI#{odi} ({make} {model})

Only generate VCs that are:
1. Testable at ECU system integration level
2. Not redundant with existing golden VCs
3. Directly motivated by the real failure pattern in the complaint

If no useful missing VC is identifiable, output: NO_NOVEL_VC_FOUND
```

## No-context baseline

Source label: `poc_baseline.py` / `BASELINE_PROMPT`.

Template SHA-256 (UTF-8 string value): `be1c4907a0c8077e3cc13dd99dfca53e49c88e62d4cbb89c400a5bca643f37fc`.

```text
You are an automotive ECU systems testing expert (ASPICE SYS.5).

Generate ADDITIONAL Verification Conditions for this automotive ECU requirement.
"Additional" means test scenarios beyond the most obvious happy-path test.

SYRS (System Requirement):
{syrs_text}

Existing VCs already written (DO NOT repeat):
{golden_vcs}

Generate 1-2 additional VCs in YAML format that test corner cases, boundary values,
or error handling scenarios a test engineer might overlook:

- VC_Item:
    VC_ID: {vc_id_prefix}.BASELINE.1
    Title: <title>
    Method:
      Type: Dynamic
      Technique: <technique>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. Verify: <expected>
      Fail: |
        - <failure condition>

If no meaningful additional VC is identifiable beyond the golden VCs, output:
NO_NOVEL_VC_FOUND
```

## RQ4 sensitivity - Channel A

Source label: `poc_sensitivity.py` / `PROMPT_A`.

Template SHA-256 (UTF-8 string value): `b5474a3fdb44b7275e28f813f58362c86f67a5d9a59d7e85ac9ddd0cf55a7414`.

```text
You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues in open-source automotive protocol software.
These issues reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive protocol software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in this YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.SEN.1
    Title: <concise test title>
    Method:
      Type: Dynamic  # or Static
      Technique: <e.g. Boundary Value Analysis, Equivalence Partitioning, Fault Injection>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. <step>
        3. Verify: <expected outcome>
      Fail: |
        - <condition that constitutes failure>
    Issue_Source: <repo#issue_id that inspired this VC>

Only generate VCs that are:
1. Genuinely testing the SYRS requirement (not testing the protocol library)
2. Not redundant with existing golden VCs
3. Inspired by a real failure pattern from the issues above
4. Testable at ECU system integration test level

If no genuinely useful missing VC can be identified from these issues, output:
NO_NOVEL_VC_FOUND
```

## RQ4 sensitivity - Channel B

Source label: `poc_sensitivity.py` / `PROMPT_B`.

Template SHA-256 (UTF-8 string value): `31d2a25cdb1c836f67c7721c62e2b96fc25c5bd9ae6bda5eb863520c65d20a4f`.

```text
You are an automotive ECU system test engineer (ASPICE SYS.5).

Generate MISSING verification conditions for an automotive ECU body/control system requirement.
The insight comes from real NHTSA vehicle owner complaints — these are real-world corner cases
that specification authors typically miss.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (DO NOT repeat):
{golden_vcs}

Related NHTSA complaints (real-world failure corner cases):
{complaints_context}

Generate 1-2 additional VCs in YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.NHTSA.1
    Title: <test title>
    Method:
      Type: Dynamic
      Technique: <e.g. Fault Injection, Boundary Value Analysis, State Transition>
    Pass_Fail_Criteria:
      Pass: |
        1. <setup>
        2. <action>
        3. Verify: <expected ECU response>
      Fail: |
        - <failure condition>
    Source_Complaint: ODI#{odi} ({make} {model})

Only generate VCs that are:
1. Testable at ECU system integration level
2. Not redundant with existing golden VCs
3. Directly motivated by the real failure pattern in the complaint

If no useful missing VC is identifiable, output: NO_NOVEL_VC_FOUND
```

## Domain-2 generation

Source label: `poc_domain2_run.py` / `GENERATE_PROMPT`.

Template SHA-256 (UTF-8 string value): `9414b54666b50940acf179e674ee8ae4bfaa2c8d17e507e5cc0020bd9365a5ae`.

```text
You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues in open-source automotive protocol software (UDS/ISO-TP/CAN).
These issues reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered — DO NOT repeat these):
{golden_vcs}

Related issues from automotive protocol software (potential missing corner cases):
{issues_context}

Generate 1-2 additional VCs in this YAML format:
- VC_Item:
    VC_ID: {vc_id_prefix}.D2.1
    Title: <concise test title>
    Method:
      Type: Dynamic  # or Static
      Technique: <e.g. Boundary Value Analysis, Equivalence Partitioning, Fault Injection>
    Pass_Fail_Criteria:
      Pass: |
        1. <step>
        2. <step>
        3. Verify: <expected outcome>
      Fail: |
        - <condition that constitutes failure>
    Issue_Source: <repo#issue_id that inspired this VC>

Only generate VCs that are:
1. Genuinely testing the SYRS requirement (not testing the protocol library itself)
2. Not redundant with existing golden VCs
3. Inspired by a real failure pattern from the issues above
4. Testable at ECU system integration test level (not unit test)

If no genuinely useful missing VC can be identified from these issues, output:
NO_NOVEL_VC_FOUND
```

