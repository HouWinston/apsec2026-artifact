# Model Configuration Manifest

This manifest separates settings found in a local archived source snapshot
inspected on 2026-11-16 from metadata in the archived sensitivity records.
Source defaults do not prove the values used in every historical execution.
The public release contains templates and text-free numerical records, not the
underlying implementation, runtime inputs, full execution logs, or API credentials.

## Source-snapshot defaults

| Operation | Request model alias | Temperature | Maximum completion tokens | Additional setting |
|---|---|---:|---:|---|
| Stage 2 distillation, GitHub and NHTSA | `qwen-plus` | 0 | 200 | User-message prompt; `response_format = {"type": "json_object"}` |
| Stage 3 matching | `text-embedding-v3` | N/A | N/A | Cosine similarity, top K = 5 |
| Stage 4 generation, GitHub and NHTSA | `qwen-max` | 0.2 | 800 | Abstention sentinel `NO_NOVEL_VC_FOUND` |
| No-context baseline | `qwen-max` | 0.2 | 600 | Same abstention sentinel |
| Ablation relevance classifier | `qwen-plus` | 0 | 20 | `response_format = {"type": "json_object"}` |
| Ablation generation | `qwen-max` | 0.2 | 800 | Same abstention sentinel |
| Domain-2 generation | `qwen-max` | 0.2 | 800 | Same abstention sentinel |
| RQ4 sensitivity generation | Configured per model | 0.2 | 800 | Channel-specific templates |

These values were read from the source definitions and call sites identified in
the prompt registry and ablation supplement. Main matching selects the top five
evidence items without a hard similarity cutoff. The generation prompt permits
abstention; this is not an independently validated relevance decision.

The source uses the default DashScope OpenAI-compatible endpoint
`https://dashscope.aliyuncs.com/compatible-mode/v1` for the main pipeline,
baseline, ablations, and Domain-2. Environment configuration can override that
endpoint. API keys are read from environment variables; no key values are
included in this manifest or the prompt files.

## Archived RQ4 sensitivity metadata

The following seven request identifiers occur in the archived sensitivity
records used for the reported numerical results. All these records specify
temperature 0.2 and `max_tokens_req` 800. The table describes recorded request
metadata; it is not a recommendation to use these aliases today.

| Recorded request identifier | Recorded provider | Recorded API endpoint |
|---|---|---|
| `qwen-max` | `alibaba-qwen` | DashScope compatible-mode endpoint above |
| `qwen-plus` | `alibaba-qwen` | DashScope compatible-mode endpoint above |
| `qwen3.6-plus` | `alibaba-qwen` | DashScope compatible-mode endpoint above |
| `deepseek-chat` | `deepseek` | `https://api.deepseek.com/v1` |
| `deepseek-v4-flash` | `deepseek-via-dashscope` | DashScope compatible-mode endpoint above |
| `kimi-k2.6` | `moonshot-via-dashscope` | DashScope compatible-mode endpoint above |
| `glm-5` | `zhipu-via-dashscope` | DashScope compatible-mode endpoint above |

There is a source/history discrepancy: in the inspected sensitivity source,
the `deepseek-chat` registry entry defaults to DashScope with provider
`deepseek-via-dashscope`, whereas the archived records for that request identifier
specify the direct DeepSeek endpoint and provider shown above. The archive and
the source snapshot must not be treated as identical configurations.

The request identifiers are API aliases, not immutable model snapshots. The
archived metadata does not identify the resolved backend model versions, and
the templates alone cannot establish the exact historical backend or substituted
prompt for any call.

RQ4 measures a generation-rate proxy based on the abstention sentinel and error
handling. A non-abstaining response is not a human-validated useful or novel VC;
these rates do not establish semantic quality or equivalent abstention behavior
across models. No new model calls or empirical experiments were performed to
prepare this documentation.

## Prompt scope

[prompt_registry.md](prompt_registry.md) contains the main pipeline, baseline,
sensitivity, and Domain-2 prompt literals.
[ablation_prompts.md](ablation_prompts.md) contains both ablation prompt literals.
The original SYS.5 role wording is preserved; the research target remains SYS.2
system-requirements verification criteria. Runtime substituted values are withheld.
