import os
import re
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from scripts.table_rows import (
    CELL_ALIGNMENT, FULL_TEXT_HINT, MAX_ROW_LINES, SUMMARY_LIMIT, TOOLTIP_LIMIT,
    cell_summary, cell_tooltip, fit_rows, max_row_height,
)

LONG_EXPLANATION = " ".join(
    ["The recorder logged a configuration save; Setting: Location; Values: ['English', 'Ελληνικά']."] * 200)


def make_table(values):
    QApplication.instance() or QApplication([])
    table = QTableWidget(len(values), 1)
    table.setWordWrap(True)
    table.setColumnWidth(0, 500)
    for row, value in enumerate(values):
        item = QTableWidgetItem(value)
        item.setTextAlignment(CELL_ALIGNMENT)
        table.setItem(row, 0, item)
    return table


def test_summary_is_short_single_line_and_marks_truncation():
    assert cell_summary("User logged out.") == "User logged out."
    assert cell_summary("line one\n  line two") == "line one line two"
    summary = cell_summary(LONG_EXPLANATION)
    assert len(summary) <= SUMMARY_LIMIT + 2
    assert summary.endswith(" …")
    assert "\n" not in summary
    assert LONG_EXPLANATION.startswith(summary[:-2].rstrip())


def test_long_text_row_is_capped_and_short_row_is_unchanged():
    table = make_table(["short value", LONG_EXPLANATION])
    table.resizeRowsToContents()
    uncapped_short = table.rowHeight(0)
    assert table.rowHeight(1) > max_row_height(table)  # the original bug
    fit_rows(table)
    assert table.rowHeight(0) == uncapped_short
    assert table.rowHeight(1) == max_row_height(table)
    assert max_row_height(table) == table.fontMetrics().lineSpacing() * MAX_ROW_LINES + 12


def test_tooltip_is_shortened_only_when_long():
    assert cell_tooltip("abc") == "abc"
    tip = cell_tooltip("x" * 5000)
    assert tip.startswith("x" * TOOLTIP_LIMIT)
    assert len(tip) < TOOLTIP_LIMIT + 60
    assert FULL_TEXT_HINT in tip


def test_viewer_rows_show_summary_and_details_get_full_text(tmp_path, monkeypatch):
    import cctv_log_analyzer as ui

    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.recents, "recent", lambda _limit: [])
    database = tmp_path / "Dahua_Analysis.db"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE dahua_logs (id INTEGER, explanation TEXT)")
        conn.execute("INSERT INTO dahua_logs VALUES (1, ?)", (LONG_EXPLANATION,))
        conn.execute("INSERT INTO dahua_logs VALUES (2, 'User logged out.')")
    viewer = ui.CCTVLogAnalyzerWindow()
    shown = {}
    monkeypatch.setattr(viewer, "show_record_values",
                        lambda values, table, label: shown.update(values))
    try:
        viewer.current_db = str(database)
        viewer.current_table = "dahua_logs"
        viewer.setup_table_columns()
        viewer.populate_table()
        column = viewer.columns.index("explanation")
        cell = viewer.table.item(0, column)
        assert cell.text() == cell_summary(LONG_EXPLANATION)
        assert viewer.table.item(1, column).text() == "User logged out."
        limit = max_row_height(viewer.table)
        assert all(viewer.table.rowHeight(row) <= limit for row in range(2))
        assert FULL_TEXT_HINT in cell.toolTip()
        # Unbreakable values are elided instead of painting over the next column.
        assert viewer.table.textElideMode() == ui.Qt.TextElideMode.ElideRight
        viewer.open_record_details(0, column)
        assert shown["explanation"] == LONG_EXPLANATION
    finally:
        viewer.close()
        application.processEvents()


def test_tooltips_have_readable_colours_in_both_themes():
    import cctv_log_analyzer as ui

    def tooltip_colours(theme):
        sheet = ui.application_stylesheet(theme, "Segoe UI", 13)
        block = re.search(r"QToolTip\s*\{([^}]*)\}", sheet).group(1)
        background = re.search(r"background:\s*(#[0-9a-fA-F]{6})", block).group(1)
        colour = re.search(r"(?<!-)color:\s*(#[0-9a-fA-F]{6})", block).group(1)
        return background, colour

    def luminance(hex_colour):
        r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for theme in ("dark", "light"):
        background, colour = tooltip_colours(theme)
        assert abs(luminance(background) - luminance(colour)) > 120, theme
    assert luminance(tooltip_colours("light")[0]) > luminance(tooltip_colours("dark")[0])
