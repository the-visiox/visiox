CLASS_COLOR_PALETTE = (
    '#22c55e',
    '#38bdf8',
    '#3b82f6',
    '#6366f1',
    '#8b5cf6',
    '#a855f7',
    '#d946ef',
    '#ec4899',
    '#f43f5e',
    '#ef4444',
    '#f97316',
    '#f59e0b',
    '#eab308',
    '#84cc16',
    '#14b8a6',
    '#64748b',
)


def class_color_for_index(index: int) -> str:
    return CLASS_COLOR_PALETTE[index % len(CLASS_COLOR_PALETTE)]
