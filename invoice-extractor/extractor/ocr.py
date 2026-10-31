"""
OCR for photographed bills, image files and scanned PDFs.

Pipeline (each step is a small function so it can be explained and tested):
    grayscale -> upscale if small -> denoise -> deskew -> adaptive threshold
    -> Tesseract with --psm 6 and --psm 4, keep the more confident result

Engines: Tesseract (default, via pytesseract) or EasyOCR (optional, only
if it is installed), selected by config.OCR_ENGINE. If no engine is
available an OCRUnavailableError with a clear message is raised; callers
(text_extraction.get_text) catch it so the app never crashes.
"""

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

import config

TESSERACT_CONFIGS = ("--oem 3 --psm 6", "--oem 3 --psm 4")

INSTALL_HELP = (
    "No OCR engine is available, so images and scanned PDFs cannot be read "
    "(digital PDFs still work). Install Tesseract: Windows - UB Mannheim "
    "installer (https://github.com/UB-Mannheim/tesseract/wiki); Mac - "
    "'brew install tesseract'; Linux - 'sudo apt install tesseract-ocr'. "
    "Or 'pip install easyocr' and set OCR_ENGINE = \"easyocr\" in config.py."
)


class OCRUnavailableError(RuntimeError):
    """Raised when neither Tesseract nor EasyOCR can be used."""


# ======================================================================
# Image preprocessing
# ======================================================================
def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Colour (BGR/BGRA) -> single-channel grayscale."""
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def upscale_if_small(gray: np.ndarray, min_width: int = config.MIN_IMAGE_WIDTH) -> np.ndarray:
    """Enlarge narrow images (OCR works badly on tiny text)."""
    height, width = gray.shape[:2]
    if width >= min_width:
        return gray
    scale = min_width / width
    return cv2.resize(gray, (min_width, int(height * scale)), interpolation=cv2.INTER_CUBIC)


def denoise(gray: np.ndarray) -> np.ndarray:
    """Remove camera / scanner noise while keeping letter edges."""
    return cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)


def estimate_skew_angle(gray: np.ndarray) -> float:
    """
    Angle (degrees) by which the text is rotated.
    Uses cv2.minAreaRect around all dark (text) pixels.
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ys, xs = np.where(binary > 0)
    if len(xs) < 50:
        return 0.0
    points = np.column_stack((xs, ys)).astype(np.float32)
    angle = cv2.minAreaRect(points)[-1]
    # Different OpenCV versions report the angle in [-90, 0) or (0, 90];
    # bring it into (-45, 45] so it means "small tilt left/right".
    while angle > 45:
        angle -= 90
    while angle <= -45:
        angle += 90
    return float(angle)


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    """Rotate around the centre, filling the corners with white."""
    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(gray, matrix, (width, height), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def deskew(gray: np.ndarray) -> np.ndarray:
    """Straighten slightly rotated text (ignores tiny or huge angles)."""
    angle = estimate_skew_angle(gray)
    if 0.5 <= abs(angle) <= 30:
        return rotate(gray, angle)
    return gray


def adaptive_threshold(gray: np.ndarray) -> np.ndarray:
    """Black text on white background, robust to uneven lighting/shadows."""
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY, 31, 15)


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Run all cleaning steps in order and return a binary image."""
    gray = to_grayscale(image)
    gray = upscale_if_small(gray)
    gray = denoise(gray)
    gray = deskew(gray)
    return adaptive_threshold(gray)


def load_image(path) -> np.ndarray:
    """Read JPG/PNG/WEBP into a BGR numpy array, honouring phone EXIF rotation."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ======================================================================
# OCR engines
# ======================================================================
@lru_cache(maxsize=1)
def tesseract_available() -> bool:
    """True if the Tesseract program is installed and callable."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _easyocr_reader():
    """Create the (slow to load) EasyOCR reader once, or None if not installed."""
    try:
        import easyocr
        return easyocr.Reader(["en"], gpu=False, verbose=False)
    except Exception:
        return None


def active_engine() -> str:
    """
    The engine that will actually be used: the configured one if it works,
    otherwise the other one, otherwise "none".
    """
    order = ["easyocr", "tesseract"] if config.OCR_ENGINE == "easyocr" else ["tesseract", "easyocr"]
    for engine in order:
        if engine == "tesseract" and tesseract_available():
            return "tesseract"
        if engine == "easyocr" and _easyocr_reader() is not None:
            return "easyocr"
    return "none"


def ocr_available() -> bool:
    """True if any OCR engine can be used."""
    return active_engine() != "none"


def _tesseract_with_confidence(image: np.ndarray, tess_config: str) -> tuple:
    """Run Tesseract once; return (text with line breaks, mean word confidence)."""
    import pytesseract
    data = pytesseract.image_to_data(image, config=tess_config,
                                     output_type=pytesseract.Output.DICT)
    lines, scores = {}, []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        score = float(data["conf"][i])
        if score >= 0:
            scores.append(score)
    text = "\n".join(" ".join(words) for _key, words in sorted(lines.items()))
    return text, (sum(scores) / len(scores) if scores else 0.0)


def _ocr_tesseract(image: np.ndarray) -> str:
    """Try psm 6 and psm 4; keep the more confident (then longer) result."""
    results = [_tesseract_with_confidence(image, cfg) for cfg in TESSERACT_CONFIGS]
    best_text, _score = max(results, key=lambda r: (round(r[1]), len(r[0])))
    return best_text


def _ocr_easyocr(image: np.ndarray) -> str:
    """EasyOCR fallback: one recognised text line per output line."""
    return "\n".join(_easyocr_reader().readtext(image, detail=0, paragraph=False))


def ocr_image(image: np.ndarray) -> str:
    """Preprocess an image array and OCR it with the active engine."""
    engine = active_engine()
    if engine == "none":
        raise OCRUnavailableError(INSTALL_HELP)
    cleaned = preprocess_image(image)
    if engine == "tesseract":
        return _ocr_tesseract(cleaned)
    return _ocr_easyocr(cleaned)


def ocr_image_file(path) -> str:
    """OCR an image file (JPG, JPEG, PNG, WEBP)."""
    return ocr_image(load_image(path))


def render_pdf_pages(path, dpi: int = config.PDF_RENDER_DPI) -> list:
    """Render every PDF page to a BGR numpy image with pymupdf (no Poppler needed)."""
    import pymupdf
    pages = []
    with pymupdf.open(Path(path)) as document:
        for page in document:
            pix = page.get_pixmap(dpi=dpi)
            array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            code = cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR
            pages.append(cv2.cvtColor(array, code) if pix.n >= 3 else array)
    return pages


def ocr_pdf(path) -> str:
    """OCR a scanned PDF page by page."""
    if not ocr_available():
        raise OCRUnavailableError(INSTALL_HELP)
    return "\n".join(ocr_image(page) for page in render_pdf_pages(path))
