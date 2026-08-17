"""Local spine detection.

Runs on CPU, needs no network after the one-off weight download, and costs
nothing per image. Everything here is deliberately cheap so that the only paid
call in the pipeline is reading text off a crop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

_model = None

# COCO class 73 is "book". These weights were trained largely on books lying
# flat rather than spines on a shelf, so recall on a dense shelf is imperfect;
# the aspect-ratio filter below drops the shelf-sized boxes it sometimes emits.
BOOK_CLASS_ID = 73

# A spine is taller than it is wide. Anything wider than this is a shelf or a
# stack, not a single book.
MAX_ASPECT_RATIO = 1.2


@dataclass
class Detection:
    index: int
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in original image pixels
    confidence: float


class DetectorUnavailable(RuntimeError):
    """Raised when the weights cannot be loaded at all."""


def get_model():
    """Load once per process. The first call downloads the weights."""
    global _model
    if _model is None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover
            raise DetectorUnavailable(
                "ultralytics is not installed; run pip install -r requirements.txt"
            ) from exc
        weights = settings.SHELFIE["DETECTOR_WEIGHTS"]
        logger.info("loading detector weights: %s", weights)
        _model = YOLO(weights)
    return _model


def detect_spines(image_path: str | Path) -> list[Detection]:
    """Return one Detection per book spine found. May legitimately be empty."""
    model = get_model()
    results = model.predict(
        str(image_path),
        imgsz=settings.SHELFIE["DETECTOR_IMGSZ"],
        conf=settings.SHELFIE["DETECTOR_CONFIDENCE"],
        device="cpu",
        verbose=False,
    )
    if not results:
        return []

    detections: list[Detection] = []
    for box in results[0].boxes:
        if int(box.cls) != BOOK_CLASS_ID:
            continue
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        width, height = max(x2 - x1, 1), max(y2 - y1, 1)
        if width / height > MAX_ASPECT_RATIO:
            continue
        detections.append(
            Detection(index=0, box=(x1, y1, x2, y2), confidence=float(box.conf))
        )

    # Left to right, so the order on screen matches the order on the shelf.
    detections.sort(key=lambda d: d.box[0])
    for i, detection in enumerate(detections):
        detection.index = i
    return detections


def crop_spine(image_path: str | Path, box: tuple[int, int, int, int], out_path: Path,
               pad: int = 4) -> Path:
    """Crop one spine, with a little padding so edge glyphs are not clipped."""
    from PIL import Image

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        x1, y1, x2, y2 = box
        x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
        x2, y2 = min(img.width, x2 + pad), min(img.height, y2 + pad)
        crop = img.crop((x1, y1, x2, y2))

        # Spine text runs bottom-to-top on most books. Rotating here rather
        # than asking the model to cope with vertical text measurably improves
        # the read and costs nothing.
        if crop.height > crop.width:
            crop = crop.rotate(-90, expand=True)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_path, "JPEG", quality=85)
    return out_path
