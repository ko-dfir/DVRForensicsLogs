"""Cooperative cancellation at safe read/record/transaction boundaries."""


class ExtractionCancelled(Exception):
    """Requested stop, distinct from extraction failure or successful completion."""


def check_cancelled(cancelled=None):
    if cancelled and cancelled():
        raise ExtractionCancelled('Extraction cancelled by the user.')
