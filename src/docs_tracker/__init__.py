"""Package initializer for Docs Tracker.

This package exposes the Streamlit entry point via ``main`` so that
``python -m docs_tracker`` can launch the UI directly.
"""

from .ui_app import main  # noqa: F401


__all__ = ["main"]