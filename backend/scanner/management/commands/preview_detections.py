"""Draw the detector's boxes onto a photo so they can be checked by eye.

A spine count alone does not tell you whether the boxes are individual books
or one blob over a whole shelf. This is the fastest way to find out.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from scanner import detection


class Command(BaseCommand):
    help = "Save a copy of a photo with numbered detection boxes drawn on it."

    def add_arguments(self, parser):
        parser.add_argument("image", help="Path to a shelf photo.")
        parser.add_argument(
            "-o", "--out", default=None,
            help="Output path (default: <image>.detections.jpg).",
        )

    def handle(self, *args, **options):
        from PIL import Image, ImageDraw

        source = Path(options["image"])
        if not source.exists():
            raise SystemExit(f"No such file: {source}")

        detections = detection.detect_spines(source)
        self.stdout.write(f"{len(detections)} spines detected")
        if not detections:
            self.stdout.write(self.style.WARNING(
                "Nothing detected. Check the photo, or lower DETECTOR_CONFIDENCE."
            ))
            return

        with Image.open(source) as img:
            canvas = img.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        for det in detections:
            x1, y1, x2, y2 = det.box
            draw.rectangle([x1, y1, x2, y2], outline=(255, 60, 60), width=3)
            label = str(det.index)
            draw.rectangle([x1, y1, x1 + 8 * len(label) + 6, y1 + 16], fill=(255, 60, 60))
            draw.text((x1 + 4, y1 + 3), label, fill=(255, 255, 255))

        out = Path(options["out"]) if options["out"] else source.with_suffix(".detections.jpg")
        canvas.save(out, "JPEG", quality=88)
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))

        confidences = sorted(d.confidence for d in detections)
        mid = confidences[len(confidences) // 2]
        self.stdout.write(
            f"detector confidence: min {confidences[0]:.2f} / "
            f"median {mid:.2f} / max {confidences[-1]:.2f}"
        )
