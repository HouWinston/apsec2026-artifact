# Model Configuration Manifest

This document summarizes model aliases and request settings from the source
snapshot inspected on 2026-11-16 and archived RQ4 sensitivity records.
Source defaults and recorded request metadata are listed separately.

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

Main matching selects the top five evidence items by cosine similarity without
a hard cutoff. Generation permits abstention using `NO_NOVEL_VC_FOUND`.

The source uses the default DashScope OpenAI-compatible endpoint
`https://dashscope.aliyuncs.com/compatible-mode/v1` for the main pipeline,
baseline, ablations, and Domain-2. Environment configuration can override that
endpoint. Credentials are supplied through environment variables.

## Archived RQ4 sensitivity metadata

Archived RQ4 records contain the seven request identifiers below, all with
temperature 0.2 and `max_tokens_req` 800.

| Recorded request identifier | Recorded provider | Recorded API endpoint |
|---|---|---|
| `qwen-max` | `alibaba-qwen` | DashScope compatible-mode endpoint above |
| `qwen-plus` | `alibaba-qwen` | DashScope compatible-mode endpoint above |
| `qwen3.6-plus` | `alibaba-qwen` | DashScope compatible-mode endpoint above |
| `deepseek-chat` | `deepseek` | `https://api.deepseek.com/v1` |
| `deepseek-v4-flash` | `deepseek-via-dashscope` | DashScope compatible-mode endpoint above |
| `kimi-k2.6` | `moonshot-via-dashscope` | DashScope compatible-mode endpoint above |
| `glm-5` | `zhipu-via-dashscope` | DashScope compatible-mode endpoint above |

For `deepseek-chat`, the inspected source defaults to DashScope with provider
`deepseek-via-dashscope`; the archived records specify the direct DeepSeek
endpoint and provider `deepseek` shown above.

Model names are API aliases; the archived metadata does not identify resolved
backend versions.
RQ4 generation rates use the logged generation/abstention indicator, which is
separate from expert-rated VC quality.

## Prompt scope

[prompt_registry.md](prompt_registry.md) contains the main pipeline, baseline,
sensitivity, and Domain-2 prompt literals.
[ablation_prompts.md](ablation_prompts.md) contains both ablation prompt literals.
