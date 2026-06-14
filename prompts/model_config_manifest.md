# Model Configuration Manifest

Models, versions, and endpoints used in the experiments. API keys are read from
environment variables and are never stored in this package.

## Main pipeline (primary run)

| Stage | Role | Model | Provider / endpoint |
|---|---|---|---|
| Stage 2 (Filter) | distill failure triple | `qwen-plus` | Alibaba DashScope (`dashscope.aliyuncs.com/compatible-mode/v1`) |
| Stage 3 (Match) | embedding similarity | `text-embedding-v3` | Alibaba DashScope (snapshot April–May 2026) |
| Stage 4 (Generate) | generate VCs | `qwen-max` | Alibaba DashScope |
| Baseline (RQ1) | no-context generation | `qwen-max` | Alibaba DashScope |
| Abl-LM (RQ3) | binary relevance classifier | `qwen-plus` | Alibaba DashScope |

Generation parameters: `temperature = 0.2`, `max_tokens = 800`.
Matching: top-`K = 5` retrieved triples per SYRS, cosine similarity, no hard
similarity cut-off (relevance is delegated to the Stage-4 abstention sentinel).

## RQ4 cross-LLM sensitivity (7 models)

Generation-rate proxy only (see `stats/reproduce_sensitivity.py`). Log
`model_name` → paper name:

| `model_name` (logs) | Paper name | Provider / endpoint |
|---|---|---|
| `qwen-max` | Qwen-Max | Alibaba DashScope |
| `qwen-plus` | Qwen-Plus | Alibaba DashScope |
| `deepseek-chat` | DeepSeek-v4-Pro | DeepSeek (`api.deepseek.com/v1`) |
| `deepseek-v4-flash` | DeepSeek-v4-Flash | DeepSeek via DashScope |
| `kimi-k2.6` | Kimi-K2.6 | Moonshot via DashScope |
| `glm-5` | GLM-5 | Zhipu via DashScope |
| `qwen3.6-plus` | Qwen3.6-Plus | Alibaba DashScope |

> `deepseek-chat` is the DeepSeek-v4-Pro endpoint (DeepSeek ships no separate
> "chat" model). Only Qwen-Max and Qwen-Plus emit the `NO_NOVEL_VC_FOUND`
> sentinel discriminatively; the other five generate for >93 % of items on both
> channels regardless of relevance.
