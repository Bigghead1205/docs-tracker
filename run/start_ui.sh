#!/bin/sh
# Launch the Streamlit app for Unix-like systems
SCRIPT_DIR="$(dirname "$0")"
python -m streamlit run "$SCRIPT_DIR/../src/docs_tracker/ui_app.py"