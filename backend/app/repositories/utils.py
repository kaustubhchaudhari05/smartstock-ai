def escape_like(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so user search text is matched literally (use escape='\\')."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
