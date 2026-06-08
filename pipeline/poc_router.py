"""Domain-layered router (follow Adaptive-RAG: lightweight classifier -> source).
security layer -> SecOC pipeline; functional layer -> defect-RAG (Ch-A/B)."""

SECURITY_KEYWORDS = [
    "security", "cyber", "crypto", "authentic", "secoc", "mac ",
    "key management", "encryption", "certificate", "replay",
    "tamper", "unauthorized", "access control", "signature", "bootloader",
]


def route_category(category: str) -> str:
    if not category:
        return "unknown"
    c = category.lower()
    if any(k in c for k in ("security", "cyber", "crypto")):
        return "security"
    return "functional"


def route_layer(category, text: str) -> str:
    """category takes priority; fall back to text keywords when no category."""
    if category:
        return route_category(category)
    t = (text or "").lower()
    return "security" if any(k in t for k in SECURITY_KEYWORDS) else "functional"


def route_dataset(syrs_records):
    """syrs_records: [{syrs_id, category, requirement}] -> {syrs_id: layer}"""
    return {r["syrs_id"]: route_layer(r.get("category"), r.get("requirement", ""))
            for r in syrs_records}
