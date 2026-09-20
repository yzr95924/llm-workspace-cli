"""api_key 展示脱敏（任何 list / show / dry-run 出口必须走这里）"""


def redact_api_key(key: str) -> str:
    """脱敏：len <= 8 → '***'；否则 '前3...末4'（如 sk-...XYZW）。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"
