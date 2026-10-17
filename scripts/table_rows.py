"""Compact cells, bounded row heights and tooltips for result tables.

Table cells show a short one-line summary of long values; the complete text is
shown in the record details window, which reads the original stored values.
"""

import re

from PySide6.QtCore import Qt

MAX_ROW_LINES = 3
SUMMARY_LIMIT = 150
TOOLTIP_LIMIT = 500
CELL_ALIGNMENT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
FULL_TEXT_HINT = "(Double-click the row for the full text.)"


def cell_summary(text, limit=SUMMARY_LIMIT):
    """Single-line cell text, shortened at a word boundary for long values."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.") + " …"


def max_row_height(table, lines=MAX_ROW_LINES):
    """Pixel height of `lines` wrapped text lines plus cell padding."""
    return table.fontMetrics().lineSpacing() * lines + 12


def fit_rows(table, lines=MAX_ROW_LINES):
    """Size rows to their content, but never taller than `lines` text lines."""
    table.resizeRowsToContents()
    limit = max_row_height(table, lines)
    for row in range(table.rowCount()):
        if table.rowHeight(row) > limit:
            table.setRowHeight(row, limit)


def cell_tooltip(text, limit=TOOLTIP_LIMIT):
    """Tooltip text, shortened for very long values."""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…\n\n" + FULL_TEXT_HINT
