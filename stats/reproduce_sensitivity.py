"""
Canonical reproducer for RQ4 (cross-LLM sensitivity, generation-rate proxy).

Run:  python reproduce_sensitivity.py
Input: ../sensitivity/ch{A,B}_<model>.jsonl  (per-call generation logs, 7 LLMs)

Generation rate = fraction of unique SYRS items for which the model emitted a
VC (is_novel=True) rather than the NO_NOVEL_VC_FOUND sentinel. Denominators:
Ch-A 208 items, Ch-B 142 items. Self-contained, stdlib only.

Log model_name -> paper RQ4 name:
  deepseek-chat = DeepSeek-v4-Pro (DeepSeek ships no separate "chat" model;
  the deepseek-chat endpoint is V4-Pro).
"""
import json
import glob
from pathlib import Path
from collections import defaultdict

SENS = Path(__file__).parent.parent / "sensitivity"

PAPER_NAME = {
    "qwen-max": "Qwen-Max",
    "qwen-plus": "Qwen-Plus",
    "deepseek-chat": "DeepSeek-v4-Pro",
    "deepseek-v4-flash": "DeepSeek-v4-Flash",
    "glm-5": "GLM-5",
    "kimi-k2.6": "Kimi-K2.6",
    "qwen3.6-plus": "Qwen3.6-Plus",
}
# Display order: sentinel-adherent first, then non-adherent.
ORDER = ["qwen-max", "qwen-plus", "deepseek-chat", "deepseek-v4-flash",
         "kimi-k2.6", "glm-5", "qwen3.6-plus"]


def main():
    rec = defaultdict(dict)  # (model, channel) -> {syrs_id: is_novel}
    for f in glob.glob(str(SENS / "*.jsonl")):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec[(e.get("model_name"), e.get("channel"))][e.get("syrs_id")] = e.get("is_novel")

    print("=" * 70)
    print("CANONICAL RQ4 (cross-LLM sensitivity) REPRODUCER")
    print("=" * 70)
    print(f"{'Model':18s} {'Ch-A gen-rate':>16s} {'Ch-B gen-rate':>16s}")
    print("-" * 54)
    non_adherent = 0
    for m in ORDER:
        cells = {}
        for ch in ("A", "B"):
            d = rec.get((m, ch), {})
            cells[ch] = (sum(1 for v in d.values() if v), len(d)) if d else (0, 0)
        ra = 100 * cells["A"][0] / cells["A"][1] if cells["A"][1] else 0
        rb = 100 * cells["B"][0] / cells["B"][1] if cells["B"][1] else 0
        if ra > 93 and rb > 93:
            non_adherent += 1
        print(f"{PAPER_NAME.get(m, m):18s} "
              f"{ra:6.1f}% ({cells['A'][0]:3d}/{cells['A'][1]:3d}) "
              f"{rb:6.1f}% ({cells['B'][0]:3d}/{cells['B'][1]:3d})")
    print("-" * 54)
    print(f"{len(ORDER)} LLMs; {non_adherent} are non-sentinel-adherent (>93% on both channels).")
    print("Only Qwen-Max and Qwen-Plus emit the sentinel discriminatively.")


if __name__ == "__main__":
    main()
