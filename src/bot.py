"""Backward-compatible placeholder for the old bot module."""


def run_bot() -> None:
    """Inform callers that the GUI entry point is now main.py."""
    print("Use `python main.py` to start the desktop application.")
