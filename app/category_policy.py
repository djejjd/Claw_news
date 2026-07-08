from __future__ import annotations

RUNTIME_CATEGORIES = frozenset({"ai", "tool", "game"})

_CATEGORY_ALIASES = {
    "device": "tool",
}

DISPLAY_CATEGORY_MAP = {
    "ai": "AI",
    "tool": "工具",
    "game": "游戏",
}


def normalize_category(category: str) -> str:
    normalized = (category or "").strip().lower()
    if normalized in RUNTIME_CATEGORIES:
        return normalized
    if normalized in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[normalized]
    raise ValueError(f"Unsupported category: {category}")


def is_supported_runtime_category(category: str) -> bool:
    try:
        normalize_category(category)
    except ValueError:
        return False
    return True


def display_category_for_runtime(category: str) -> str:
    normalized = normalize_category(category)
    return DISPLAY_CATEGORY_MAP[normalized]
