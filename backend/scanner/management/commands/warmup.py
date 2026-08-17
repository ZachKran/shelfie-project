"""Download and warm the local detector.

Run once after a clean clone. Without it the first scan pays the weight
download inside the request, and returns zero detections while it does.
"""

from django.core.management.base import BaseCommand

from scanner import detection


class Command(BaseCommand):
    help = "Download and warm up the local spine detector."

    def handle(self, *args, **options):
        self.stdout.write("Loading the detector (this downloads weights on first run)...")
        try:
            path = detection.warm_up()
        except detection.DetectorUnavailable as exc:
            raise SystemExit(f"Detector unavailable: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Detector ready: {path}"))
