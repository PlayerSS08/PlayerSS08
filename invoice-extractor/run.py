"""
Start the app: python run.py
(the same as `streamlit run app.py`, but works even if the `streamlit`
command is not on PATH, which is common on Windows).
"""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    app = Path(__file__).resolve().parent / "app.py"
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), *sys.argv[1:]]))
