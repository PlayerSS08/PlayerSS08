#!/bin/bash
# Double-click (macOS) or run ./"Start Invoice Extractor.command" (Linux)
# to open Invoice Extractor in your browser. First start installs the
# libraries once; later starts open straight away.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    python3 launch.py
elif command -v python >/dev/null 2>&1; then
    python launch.py
else
    echo "Python 3.10 or newer is needed: https://www.python.org/downloads/"
fi
echo
read -r -p "Press Enter to close this window..."
