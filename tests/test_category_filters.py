import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from cctv_log_analyzer import CCTVLogAnalyzerWindow


@pytest.mark.parametrize("table_name,category_column", [
    ("dahua_logs", "category"),
    ("hikvision_logs", "major_type"),
    ("tvt_logs", "event_category"),
])
def test_category_filter_uses_actual_database_values(tmp_path, table_name, category_column):
    application = QApplication.instance() or QApplication([])
    database = tmp_path / "logs.db"
    connection = sqlite3.connect(database)
    connection.execute(
        f'CREATE TABLE "{table_name}" ("{category_column}" TEXT, message TEXT)')
    connection.executemany(
        f'INSERT INTO "{table_name}" VALUES (?, ?)',
        [("Authentication", "Login"), ("System", "Power on")])
    connection.commit()
    connection.close()

    viewer = CCTVLogAnalyzerWindow()
    try:
        viewer.current_db = str(database)
        viewer.current_table = table_name
        viewer.setup_table_columns()
        assert viewer.category_selector.isEnabled()
        assert [viewer.category_selector.itemText(index)
                for index in range(viewer.category_selector.count())] == [
                    "All categories", "Authentication", "System"]
        viewer.category_selector.setCurrentIndex(1)
        viewer.populate_table()
        where, params = viewer._where_clause()
        assert f'"{category_column}" = ?' in where
        assert params == ["Authentication"]
        assert viewer.total_rows == 1
        assert viewer.table.item(0, 1).text() == "Login"
        assert "Authentication" in viewer._export_context()["metadata"]["Active filters"]
    finally:
        viewer.close()
        application.processEvents()
