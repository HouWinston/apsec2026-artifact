# Prompt Registry

All LLM prompts used by the pipeline, released verbatim. `{...}` fields are
filled at run time. These are the exact templates used in
`pipeline/poc_pipeline.py` (Channel A / GitHub), `pipeline/poc_nhtsa.py`
(Channel B / NHTSA), and `pipeline/poc_baseline.py` (no-context baseline).

> Note: the generation prompts label the role as "ASPICE SYS.5" (software
> qualification test). The target artefact is the SYS.2 system-requirements
> verification criterion; the prompts are reproduced here exactly as run.

---

## Stage 2 — Filter / Distill

### Channel A (GitHub issues) — model: Qwen-Plus

```
You are an automotive embedded systems expert.
Extract the technical essence from this GitHub issue report.

Output ONLY a JSON object with these three fields:
{
  "trigger": "what system state or input caused the issue (protocol service, service ID, conditions)",
  "behavior": "what protocol or system behavior was expected vs observed",
  "fault_mode": "the failure category: e.g. missing response, wrong NRC, timing violation, silent failure, protocol non-compliance"
}

If the issue is not about automotive protocol behavior (e.g., pure Python packaging, docs), output:
{"trigger": null, "behavior": null, "fault_mode": null}

Issue title: {title}
Issue body: {body}
```

### Channel B (NHTSA complaints) — model: Qwen-Plus

```
You are an automotive ECU requirements engineer.
Extract the technical essence from this NHTSA vehicle complaint.

Output ONLY a JSON object:
{
  "trigger": "what operational condition or user action triggered the failure",
  "behavior": "what the system was expected to do vs what actually happened",
  "fault_mode": "failure category: e.g. no-response, false-activation, timing-violation, state-stuck, unexpected-lock, sensor-error"
}

If this complaint is not related to automotive ECU system behavior (e.g., cosmetic, noise, smell), output:
{"trigger": null, "behavior": null, "fault_mode": null}

Component: {component}
Complaint: {summary}
```

---

## Stage 4 — Generate

### Channel A (GitHub issues) — model: Qwen-Max

```
You are an automotive ECU systems testing expert with ASPICE SYS.5 knowledge.

Your task: generate MISSING verification conditions for an automotive ECU system requirement.
"Missing" means test scenarios NOT already covered by the existing golden VCs.

The insight comes from real-world issues in open-source automotive protocol software.
These issues reveal corner cases that spec authors typically overlook.

SYRS (System Requirement):
{syrs_text}

Existing golden VCs (already covered -- DO NOT repeat these):
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

### Channel B (NHTSA complaints) — model: Qwen-Max

```
You are an automotive ECU system test engineer (ASPICE SYS.5).

Generate MISSING verification conditions for an automotive ECU body/control system requirement.
The insight comes from real NHTSA vehicle owner complaints -- these are real-world corner cases
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

---

## No-context baseline (RQ1 comparison) — model: Qwen-Max

```
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
