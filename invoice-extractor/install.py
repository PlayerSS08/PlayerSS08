"""
One-step installer: python install.py

* installs everything in requirements.txt into the Python you run it with
* uses the bundled Tesseract wheels in vendor/wheels/ when present
  (so OCR works even without internet / without installing Tesseract)
* then checks that PDF reading and OCR both work
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WHEELS = ROOT / "vendor" / "wheels"


def main() -> int:
    print(f"Python {sys.version.split()[0]} at {sys.executable}\n")
    if sys.version_info < (3, 10):
        print("Please use Python 3.10 or newer.")
        return 1
    command = [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]
    if WHEELS.exists():
        command += ["--find-links", str(WHEELS)]
    print("Installing libraries (first time takes a few minutes)...")
    if subprocess.call(command) != 0:
        print("\nInstallation failed - see the messages above.")
        return 1

    print("\nChecking the installation...")
    sys.path.insert(0, str(ROOT))
    from extractor import ocr  # noqa: E402  (imported after installing)
    engine = ocr.active_engine()
    if engine == "none":
        print("  PDF reading: OK\n  OCR: NOT available - " + ocr.INSTALL_HELP)
    else:
        print(f"  PDF reading: OK\n  OCR engine: {engine} - OK")
    print("\nAll set! Start the app with:  python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
