"""Portable, non-host-specific display values for exported evidence."""


def source_database_name(value):
    """Keep the source database filename, including a device serial if present."""
    if value is None:
        return ""
    return str(value).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def display_value(column, value):
    if column.lower() == "source_database":
        return source_database_name(value)
    return "" if value is None else str(value)
