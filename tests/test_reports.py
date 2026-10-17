import csv
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from scripts.dvr_extractor import export_to_csv, export_to_html


def _database(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE events (timestamp TEXT, event TEXT)")
    connection.executemany(
        "INSERT INTO events VALUES (?, ?)",
        [("2026-01-01 10:00:00", "old <event>"),
         ("2026-09-21 13:00:00", "selected & safe")],
    )
    connection.commit()
    connection.close()


def test_csv_export_applies_active_time_filter(tmp_path):
    database = tmp_path / "events.db"
    output = tmp_path / "report.csv"
    _database(database)
    export_to_csv(
        database, "events", output,
        " WHERE timestamp >= ? AND timestamp < ?",
        ["2026-09-21", "2026-09-22"],
    )
    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows == [["timestamp", "event"], ["2026-09-21 13:00:00", "selected & safe"]]


def test_html_export_is_blue_filtered_escaped_and_embeds_logo(tmp_path):
    database = tmp_path / "events.db"
    output = tmp_path / "report.html"
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"fake-png")
    _database(database)
    export_to_html(
        database, "events", output, " WHERE event LIKE ?", ["%old%"],
        logo_path=logo,
        report_context={"metadata": {"Active filters": "event: old"}},
    )
    document = output.read_text(encoding="utf-8")
    assert "--blue:#155eef" in document
    assert "data:image/png;base64," in document
    assert "old &lt;event&gt;" in document
    assert "selected &amp; safe" not in document


def test_html_report_has_interactive_category_filter_for_exported_rows(tmp_path):
    database = tmp_path / "logs.db"
    output = tmp_path / "report.html"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE tvt_logs (event_category TEXT, message TEXT)")
    connection.executemany("INSERT INTO tvt_logs VALUES (?, ?)", [
        ("USER_ACTION", "Login"),
        ("SYSTEM_ERROR", "Disk error"),
        ("USER_ACTION", "Logout"),
    ])
    connection.commit()
    connection.close()

    export_to_html(
        database, "tvt_logs", output,
        report_context={"page_size": 25, "title": "Case report"},
    )
    document = output.read_text(encoding="utf-8")
    assert "id='report-category'" in document
    assert "<option value='USER_ACTION'>USER_ACTION</option>" in document
    assert "<option value='SYSTEM_ERROR'>SYSTEM_ERROR</option>" in document
    assert document.count("data-category='USER_ACTION'") == 2
    assert "entry[2] === selected" in document
    assert "USER_ACTION: 2" in document
    assert "Page 1 of 1" in document
    assert "Search all pages" in document
    assert "Case report" in document


def test_html_report_can_hide_metadata_but_keeps_filters(tmp_path):
    database = tmp_path / "events.db"
    output = tmp_path / "report.html"
    _database(database)
    export_to_html(database, "events", output,
                   report_context={"show_metadata": False, "title": "Private report"})
    document = output.read_text(encoding="utf-8")
    assert "<section class='meta'>" not in document
    assert "Private report" in document
    assert "id='report-search'" in document
    assert "Search all pages" in document
    assert "id='report-category'" not in document


def test_embedded_report_pagination_script_is_valid_javascript(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node.js is unavailable")
    database = tmp_path / "events.db"
    output = tmp_path / "report.html"
    _database(database)
    export_to_html(database, "events", output)
    document = output.read_text(encoding="utf-8")
    for script in re.findall(r"<script>(.*?)</script>", document, re.S):
        result = subprocess.run(["node", "--check", "-"], input=script,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr


def test_html_export_writes_bounded_linked_pages_and_hides_host_paths(tmp_path):
    database = tmp_path / "logs.db"
    output = tmp_path / "case.html"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE logs (source_database TEXT, category TEXT, message TEXT)")
        connection.executemany("INSERT INTO logs VALUES (?, ?, ?)", [
            (r"C:\\Users\\examiner\\Dahua\\serial123.db", "User", f"Event {number}")
            for number in range(27)
        ])
    pages = export_to_html(database, "logs", output, report_context={"page_size": 10})
    assert [output.name, "case_page_0002.html", "case_page_0003.html", "case_index.js"] == [
        Path(page).name for page in pages]
    first = output.read_text(encoding="utf-8")
    second = (tmp_path / "case_page_0002.html").read_text(encoding="utf-8")
    assert first.count("data-category='User'") == 10
    assert "case_page_0002.html" in first
    assert "case.html" in second
    assert "serial123.db" in first
    assert "examiner" not in first
    assert "Event 26" not in first
    index_script = (tmp_path / "case_index.js").read_text(encoding="utf-8")
    entries = json.loads(index_script.removeprefix("window.REPORT_INDEX=").removesuffix(";\n"))
    assert len(entries) == 27
    assert entries[-1][:3] == [3, 7, "User"]
    assert "Event 26" in entries[-1][3]
    assert "examiner" not in index_script
    assert "window.REPORT_INDEX" in first
    assert "matching records across all pages" in first
    assert "id='result-body'" in first
