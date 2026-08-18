import logging
import time
from pathlib import Path

from django.conf import settings
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import detection, vlm
from .matching import Matcher, load_catalog
from .models import LibraryBook, Scan, ScanItem
from .serializers import (
    LibraryBookSerializer,
    ScanItemSerializer,
    ScanSerializer,
    ScanSummarySerializer,
)

logger = logging.getLogger(__name__)

_matcher: Matcher | None = None


def get_matcher() -> Matcher:
    """Load catalog.csv once per process. 123 rows fits in memory comfortably,
    so it stays out of the database and the matcher stays unit-testable."""
    global _matcher
    if _matcher is None:
        _matcher = Matcher(
            load_catalog(settings.CATALOG_PATH),
            match_threshold=settings.SHELFIE["MATCH_THRESHOLD"],
            review_threshold=settings.SHELFIE["REVIEW_THRESHOLD"],
        )
    return _matcher


def run_pipeline(scan: Scan) -> Scan:
    """detect -> crop -> read -> match. Records timings for the README."""
    started = time.perf_counter()
    image_path = Path(scan.image.path)
    crop_dir = Path(settings.MEDIA_ROOT) / "crops" / str(scan.pk)

    # 1. Detect, locally.
    t0 = time.perf_counter()
    try:
        detections = detection.detect_spines(image_path)
    except detection.DetectorUnavailable as exc:
        scan.error = str(exc)
        scan.total_ms = int((time.perf_counter() - started) * 1000)
        scan.save()
        return scan
    scan.detect_ms = int((time.perf_counter() - t0) * 1000)

    if not detections:
        # Not an error. The app shows a "no books found" state and a retake
        # prompt rather than an empty list.
        scan.total_ms = int((time.perf_counter() - started) * 1000)
        scan.save()
        return scan

    # 2. Crop.
    crop_paths = []
    for det in detections:
        out = crop_dir / f"{det.index:03d}.jpg"
        detection.crop_spine(image_path, det.box, out)
        crop_paths.append(out)

    # 3. Read, hosted. This is the only step that costs money, so it is the
    # only step with a ceiling on it.
    limit = settings.SHELFIE["VLM_MAX_SPINES"]
    to_read, deferred = crop_paths[:limit], crop_paths[limit:]
    if deferred:
        logger.info(
            "scan %s: reading %s of %s spines (VLM_MAX_SPINES=%s)",
            scan.pk, len(to_read), len(crop_paths), limit,
        )
    t0 = time.perf_counter()
    reads, usage = vlm.read_spines(to_read)
    # Spines past the ceiling are still returned to the user, marked skipped,
    # so the cap is visible rather than a silent truncation.
    reads.extend(
        vlm.SpineRead(index=len(to_read) + i, error="skipped: per-scan read limit reached")
        for i in range(len(deferred))
    )
    scan.vlm_ms = int((time.perf_counter() - t0) * 1000)
    scan.vlm_input_tokens = usage["input_tokens"]
    scan.vlm_output_tokens = usage["output_tokens"]

    # 4. Match, locally.
    t0 = time.perf_counter()
    matcher = get_matcher()
    for det, read, crop_path in zip(detections, reads, crop_paths):
        item = ScanItem(
            scan=scan,
            index=det.index,
            box=list(det.box),
            detector_confidence=det.confidence,
            crop=str(crop_path.relative_to(settings.MEDIA_ROOT)),
            read_title=read.title,
            read_author=read.author,
            read_error=read.error,
        )
        if not read.is_readable:
            # Kept in the scan so the user sees the crop and can type it in.
            item.status = (
                ScanItem.SKIPPED if read.error.startswith("skipped:")
                else ScanItem.UNREADABLE
            )
            item.confidence = 0.0
        else:
            result = matcher.match(read.title, read.author)
            item.status = result.status
            item.confidence = result.confidence
            item.match_id = result.match_id or ""
            item.candidates = result.as_dict()["candidates"]
        item.save()
    scan.match_ms = int((time.perf_counter() - t0) * 1000)
    scan.total_ms = int((time.perf_counter() - started) * 1000)
    scan.save()
    return scan


class ScanListCreateView(generics.ListCreateAPIView):
    queryset = Scan.objects.all().prefetch_related("items").order_by("-created_at")
    serializer_class = ScanSerializer

    def get_serializer_class(self):
        # Listing every scan with every item and its candidates would be a very
        # large payload; the list only needs counts.
        if self.request.method == "GET":
            return ScanSummarySerializer
        return ScanSerializer

    def create(self, request, *args, **kwargs):
        if "image" not in request.FILES:
            return Response(
                {"detail": "No image was uploaded."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scan = Scan.objects.create(image=request.FILES["image"])
        try:
            run_pipeline(scan)
        except Exception as exc:  # nothing here should reach the client as a 500
            logger.exception("scan %s failed", scan.pk)
            scan.error = f"{type(exc).__name__}: {exc}"
            scan.save()
        scan.refresh_from_db()
        return Response(
            ScanSerializer(scan, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ScanDetailView(generics.RetrieveAPIView):
    queryset = Scan.objects.all().prefetch_related("items")
    serializer_class = ScanSerializer


@api_view(["POST"])
def resolve_item(request, pk):
    """Confirm, correct, or discard one reviewed spine.

    Every path marks the item resolved, so nothing sits in the review queue
    without the user having made a decision about it.
    """
    try:
        item = ScanItem.objects.get(pk=pk)
    except ScanItem.DoesNotExist:
        return Response({"detail": "No such item."}, status=status.HTTP_404_NOT_FOUND)

    action = request.data.get("action")
    if action not in {"confirm", "correct", "discard"}:
        return Response(
            {"detail": "action must be one of: confirm, correct, discard."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if action == "discard":
        item.resolved = True
        item.save(update_fields=["resolved"])
        return Response({"resolved": True, "book": None})

    matcher = get_matcher()
    if action == "confirm":
        entry = matcher.by_id.get(item.match_id)
        if entry is None:
            return Response(
                {"detail": "This item has no catalog match to confirm."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        title, author, catalog_id, manual = entry.title, entry.author, entry.id, False
    else:
        catalog_id = (request.data.get("catalog_id") or "").strip()
        entry = matcher.by_id.get(catalog_id)
        if entry is not None:
            title, author = entry.title, entry.author
        else:
            title = (request.data.get("title") or "").strip()
            author = (request.data.get("author") or "").strip()
            catalog_id = ""
        if not title:
            return Response(
                {"detail": "A correction needs a catalog_id or a title."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        manual = True

    book, created = LibraryBook.objects.get_or_create(
        catalog_id=catalog_id,
        title=title,
        author=author,
        defaults={"source_item": item, "manually_entered": manual},
    )
    item.resolved = True
    item.save(update_fields=["resolved"])
    return Response(
        {
            "resolved": True,
            "already_in_library": not created,
            "book": LibraryBookSerializer(book).data,
        },
        status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED,
    )


class LibraryListCreateView(generics.ListCreateAPIView):
    queryset = LibraryBook.objects.all()
    serializer_class = LibraryBookSerializer


class LibraryDetailView(generics.RetrieveDestroyAPIView):
    queryset = LibraryBook.objects.all()
    serializer_class = LibraryBookSerializer


@api_view(["GET"])
def catalog_search(request):
    query = request.query_params.get("q", "")
    results = get_matcher().search(query)
    return Response({"results": [c.as_dict() for c in results]})
