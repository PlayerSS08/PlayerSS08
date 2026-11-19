"""
One-click launcher: opens Invoice Extractor in your browser.

Double-click "Start Invoice Extractor.bat" (Windows) or
"Start Invoice Extractor.command" (macOS / Linux); both just run this file.

What it does, every time:
1. If the app is already running, it only opens the browser tab.
2. It picks the Python to use: the project's .venv if there is one,
   otherwise the Python that started this script.
3. It checks the required libraries WITHOUT reinstalling anything.
   Only the first time (or if something is missing) it installs them -
   into a private .venv folder - using the bundled offline wheels when present.
4. It starts the app and opens http://localhost:8501 in your browser.
   Keep the window open while you use the app; close it to stop the app.
"""

import hashlib
import importlib.util
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
WHEELS = ROOT / "vendor" / "wheels"
STAMP = VENV / ".requirements-installed"   # remembers which requirements were installed
PORT = 8501
URL = f"http://localhost:{PORT}"

# import name -> pip package (only what the app needs to run; pytest is for development)
REQUIRED = {
    "streamlit": "streamlit", "pymupdf": "pymupdf", "pdfplumber": "pdfplumber",
    "cv2": "opencv-python-headless", "PIL": "Pillow", "numpy": "numpy",
    "dateutil": "python-dateutil", "pandas": "pandas", "openpyxl": "openpyxl",
    "plotly": "plotly", "pytesseract": "pytesseract", "tesserocr": "tesserocr",
}


def say(message: str) -> None:
    print(f"[Invoice Extractor] {message}", flush=True)


# ----------------------------------------------------------------------
# Small helpers (pure where possible, so they can be tested)
# ----------------------------------------------------------------------
def venv_python(venv: Path = VENV) -> Path:
    """Path of the Python inside a virtual environment (Windows or macOS/Linux)."""
    windows = venv / "Scripts" / "python.exe"
    return windows if os.name == "nt" or windows.exists() else venv / "bin" / "python"


def requirements_hash(path: Path = REQUIREMENTS) -> str:
    """Fingerprint of requirements.txt, so a changed list triggers one re-install."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def app_running(url: str = URL, timeout: float = 1.0) -> bool:
    """True if Invoice Extractor (Streamlit) already answers on this port."""
    try:
        with urllib.request.urlopen(f"{url}/_stcore/health", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def missing_in_this_python() -> list:
    """Required packages that the Python running this script cannot find."""
    return [package for module, package in REQUIRED.items()
            if importlib.util.find_spec(module) is None]


def missing_in(python: Path) -> list:
    """Required packages missing from another Python (e.g. the .venv one)."""
    check = ("import importlib.util, json, sys; "
             f"req = {REQUIRED!r}; "
             "print(json.dumps([p for m, p in req.items() if importlib.util.find_spec(m) is None]))")
    try:
        output = subprocess.run([str(python), "-c", check], capture_output=True, text=True,
                                timeout=120, check=True).stdout
        import json
        return json.loads(output.strip().splitlines()[-1])
    except Exception:
        return list(REQUIRED.values())


# ----------------------------------------------------------------------
# Setup (first run only)
# ----------------------------------------------------------------------
def install_into(python: Path) -> bool:
    """pip install the requirements into `python`, offline wheels first. True on success."""
    command = [str(python), "-m", "pip", "install", "--disable-pip-version-check",
               "-r", str(REQUIREMENTS)]
    if WHEELS.exists():
        command += ["--find-links", str(WHEELS)]
    say("Installing the libraries - only needed once, this can take a few minutes...")
    if subprocess.call(command) != 0:
        say("Installation failed. Check your internet connection and try again.")
        return False
    if VENV.exists():
        STAMP.write_text(requirements_hash())
    return True


def choose_python() -> Path:
    """
    The Python to run the app with, installing libraries only when needed:
      * a .venv that is complete and up to date -> use it, no checks repeated
      * no .venv, but this Python already has everything -> use this Python
      * otherwise -> create .venv once and install into it
    """
    if VENV.exists():
        python = venv_python()
        up_to_date = STAMP.exists() and STAMP.read_text().strip() == requirements_hash()
        if up_to_date or not missing_in(python):
            if not up_to_date:
                STAMP.write_text(requirements_hash())
            return python
        return python if install_into(python) else None

    if not missing_in_this_python():
        return Path(sys.executable)

    say("First start: setting up a private Python environment in the .venv folder...")
    if subprocess.call([sys.executable, "-m", "venv", str(VENV)]) != 0:
        say("Could not create the .venv folder.")
        return None
    python = venv_python()
    subprocess.call([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    return python if install_into(python) else None


# ----------------------------------------------------------------------
# Start
# ----------------------------------------------------------------------
def start(python: Path) -> int:
    """Run the app, open the browser when it is ready, and wait until it stops."""
    say("Starting the app...")
    server = subprocess.Popen([str(python), "-m", "streamlit", "run", str(ROOT / "app.py"),
                               "--server.port", str(PORT), "--server.headless", "true"],
                              cwd=str(ROOT))
    for _ in range(120):                       # wait up to 60 s for the server
        if server.poll() is not None:
            say("The app stopped unexpectedly - see the messages above.")
            return server.returncode or 1
        if app_running(timeout=0.5):
            break
        time.sleep(0.5)
    webbrowser.open(URL)
    say(f"Running at {URL}  (keep this window open; close it or press Ctrl+C to stop)")
    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        return 0


def main() -> int:
    if sys.version_info < (3, 10):
        say("Python 3.10 or newer is needed: https://www.python.org/downloads/")
        return 1
    if app_running():
        say(f"Already running - opening {URL}")
        webbrowser.open(URL)
        return 0
    python = choose_python()
    if python is None:
        return 1
    return start(python)


if __name__ == "__main__":
    sys.exit(main())
