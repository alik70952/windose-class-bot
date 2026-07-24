"""Application bootstrap module."""

from src.ui.main_window import MainWindow


def run_app() -> None:
    """Start the Persian desktop user interface."""
    app = MainWindow()
    app.mainloop()
