"""
vpc_colors — deterministic VPC → color mapping.

Pure module: no imports from project, no side effects.
Same vpc_id always maps to the same color, across all sessions.
"""

_PALETTE = [
    "#3498db",  # blue
    "#e67e22",  # orange
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#e74c3c",  # red
    "#f1c40f",  # yellow
    "#2ecc71",  # green
    "#e91e63",  # pink
]


def vpc_color(vpc_id: str) -> str:
    """Return a deterministic hex color for a given vpc_id.

    Maps vpc_id → stable index in an 8-color palette by hashing.
    The same vpc_id always returns the same color; different vpc_ids
    are spread across the palette.
    """
    idx = hash(vpc_id) % len(_PALETTE)
    return _PALETTE[idx]
