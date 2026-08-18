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

# A box that swallows this many other boxes is a shelf, not a book. The
# detector reliably emits one of these per shelf alongside the real spines,
# and every one that survives costs a wasted API call downstream.
CONTAINS_LIMIT = 2

# Fraction of the smaller box that must sit inside the larger one to count as
# contained. Below 1.0 so a spine poking a few pixels out still counts.
CONTAINMENT_RATIO = 0.80

# Two boxes overlapping more than this are the same spine detected twice.
DUPLICATE_IOU = 0.70

# Never blow a crop up by more than this. Past it there is no more detail to
# recover, only tokens to pay for.
MAX_UPSCALE = 5.0


@dataclass
class Detection:
    index: int
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in original image pixels
    confidence: float


class DetectorUnavailable(RuntimeError):
    """Raised when the weights cannot be loaded at all."""


def get_model():
    """Load once per process, and warm the model before anyone depends on it.

    The warm-up is not an optimisation. On a clean clone the first call also
    downloads the weights, and a prediction issued immediately afterwards
    returns zero detections rather than raising — so the very first scan a
    reviewer runs would report "no books found" on a perfectly good photo. The
    throwaway prediction below absorbs that first call.
    """
    global _model
    if _model is None:
        try:
            import numpy as np
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover
            raise DetectorUnavailable(
                "ultralytics is not installed; run pip install -r requirements.txt"
            ) from exc

        weights = settings.SHELFIE["DETECTOR_WEIGHTS"]
        downloading = not Path(weights).exists()
        if downloading:
            logger.info("detector weights not found locally, downloading: %s", weights)
        model = YOLO(weights)

        if not Path(weights).exists():
            raise DetectorUnavailable(
                f"detector weights {weights} could not be downloaded; "
                "check your network connection and try again"
            )

        model.predict(
            np.zeros((64, 64, 3), dtype="uint8"), device="cpu", verbose=False
        )
        logger.info("detector ready: %s", weights)
        _model = model
    return _model


def warm_up() -> str:
    """Load and warm the detector ahead of the first request. Returns the
    weights path so callers can report it."""
    get_model()
    return str(Path(settings.SHELFIE["DETECTOR_WEIGHTS"]).resolve())


def _intersection(a: tuple, b: tuple) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def _area(box: tuple) -> float:
    return max(box[2] - box[0], 0) * max(box[3] - box[1], 0)


def suppress_overlaps(detections: list[Detection]) -> list[Detection]:
    """Drop shelf-spanning boxes and duplicate detections of one spine.

    Ultralytics already runs non-max suppression, but NMS keeps a box that
    fully contains several smaller ones because the pairwise overlap with any
    single one of them is low. Those are exactly the shelf-wide boxes, so they
    are removed here by counting containment rather than overlap.
    """
    if not detections:
        return []

    kept = list(detections)

    # Shelf-spanning boxes.
    survivors = []
    for candidate in kept:
        contained = 0
        for other in kept:
            if other is candidate:
                continue
            other_area = _area(other.box)
            if other_area <= 0:
                continue
            if _intersection(candidate.box, other.box) / other_area >= CONTAINMENT_RATIO:
                contained += 1
        if contained >= CONTAINS_LIMIT:
            logger.debug("dropping box containing %s others: %s", contained, candidate.box)
            continue
        survivors.append(candidate)

    # Duplicates of the same spine: keep whichever the detector was surer of.
    survivors.sort(key=lambda d: d.confidence, reverse=True)
    deduped: list[Detection] = []
    for candidate in survivors:
        duplicate = False
        for chosen in deduped:
            overlap = _intersection(candidate.box, chosen.box)
            union = _area(candidate.box) + _area(chosen.box) - overlap
            if union > 0 and overlap / union >= DUPLICATE_IOU:
                duplicate = True
                break
        if not duplicate:
            deduped.append(candidate)

    return deduped


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

    before = len(detections)
    detections = suppress_overlaps(detections)
    if before != len(detections):
        logger.info("suppressed %s overlapping boxes", before - len(detections))

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

        # Spine text on North American editions runs top-to-bottom, so a
        # counter-clockwise quarter turn puts it the right way up. Rotating
        # here rather than asking the model to cope with vertical text is the
        # single biggest quality lever in the pipeline: rotated the wrong way,
        # reads came back as anagram-like garbage ("DAVID BALDACCI" was read as
        # "BRIGGSAM"); rotated correctly they are clean.
        if crop.height > crop.width:
            crop = crop.rotate(90, expand=True)

        # Detected spines are thin — often only 40-60px on the short edge,
        # which is not enough pixels for the model to resolve the lettering.
        # Upscaling costs tokens (billed by pixel area) but a crop the model
        # cannot read costs the same and returns nothing.
        target = settings.SHELFIE["CROP_MIN_HEIGHT"]
        if 0 < crop.height < target:
            scale = min(target / crop.height, MAX_UPSCALE)
            crop = crop.resize(
                (max(1, int(crop.width * scale)), max(1, int(crop.height * scale))),
                Image.LANCZOS,
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_path, "JPEG", quality=85)
    return out_path
