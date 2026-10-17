"""Persistent per-user UI preferences."""

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication

THEMES = ("system", "dark", "light")

DEFAULTS = {
    "theme": "system",
    "font_family": "Segoe UI",
    "font_size": 13,
    "recent_limit": 10,
    "page_size": 100,
    "last_open_dir": "",
    "last_output_dir": "",
    "case_folder": "",
    "report_logo": "",
    "report_title": "CCTV Log Analyzer Report",
    "report_page_size": 100,
    "report_show_metadata": True,
}


def system_theme():
    """'dark' or 'light' from the operating system's app colour scheme."""
    application = QGuiApplication.instance()
    hints = application.styleHints() if application is not None else None
    scheme = getattr(hints, "colorScheme", lambda: None)()
    if scheme == Qt.ColorScheme.Light:
        return "light"
    return "dark"


def resolve_theme(theme):
    """Concrete 'dark' or 'light' theme for a saved preference."""
    if theme in ("dark", "light"):
        return theme
    return system_theme()


class AppSettings:
    def __init__(self):
        self._settings = QSettings("CCTVLogAnalyzer", "CCTVLogAnalyzer")

    def get(self, key):
        default = DEFAULTS.get(key)
        value = self._settings.value(key, default)
        if isinstance(default, bool):
            return value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes")
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return value

    def set(self, key, value):
        self._settings.setValue(key, value)
        self._settings.sync()

    def font(self):
        family = str(self.get("font_family") or DEFAULTS["font_family"])
        size = max(9, min(22, int(self.get("font_size"))))
        return family, size
