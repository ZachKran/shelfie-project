from django.db import models


class Scan(models.Model):
    """One uploaded shelf photo and the pipeline run over it."""

    image = models.ImageField(upload_to="scans/")
    created_at = models.DateTimeField(auto_now_add=True)

    # Measured per stage so the README numbers come from real runs.
    detect_ms = models.IntegerField(null=True, blank=True)
    vlm_ms = models.IntegerField(null=True, blank=True)
    match_ms = models.IntegerField(null=True, blank=True)
    total_ms = models.IntegerField(null=True, blank=True)

    vlm_input_tokens = models.IntegerField(null=True, blank=True)
    vlm_output_tokens = models.IntegerField(null=True, blank=True)

    # Set when the whole run failed; individual spine failures live on ScanItem.
    error = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Scan {self.pk} ({self.items.count()} spines)"


class ScanItem(models.Model):
    """One detected spine. Every detected spine gets a row, including failures."""

    MATCHED = "matched"
    REVIEW = "review"
    UNMATCHED = "unmatched"
    UNREADABLE = "unreadable"
    SKIPPED = "skipped"
    STATUS_CHOICES = [
        (MATCHED, "Matched"),
        (REVIEW, "Needs review"),
        (UNMATCHED, "No catalog match"),
        (UNREADABLE, "Could not be read"),
        (SKIPPED, "Skipped to stay within the per-scan limit"),
    ]

    scan = models.ForeignKey(Scan, related_name="items", on_delete=models.CASCADE)
    index = models.IntegerField()

    # Detector output, normalised to the original image.
    box = models.JSONField(default=list)
    detector_confidence = models.FloatField(null=True, blank=True)
    crop = models.ImageField(upload_to="crops/", null=True, blank=True)

    # VLM output, as read. Kept raw so the review screen can show what the
    # model actually saw rather than only what it matched to.
    read_title = models.CharField(max_length=500, blank=True, default="")
    read_author = models.CharField(max_length=300, blank=True, default="")
    read_error = models.TextField(blank=True, default="")

    # Matcher output.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    confidence = models.FloatField(default=0.0)
    match_id = models.CharField(max_length=100, blank=True, default="")
    candidates = models.JSONField(default=list)

    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["index"]
        unique_together = [("scan", "index")]

    def __str__(self):
        return f"{self.scan_id}#{self.index} {self.status}"


class LibraryBook(models.Model):
    """A book the user confirmed. This is the only table the library reads."""

    catalog_id = models.CharField(max_length=100, blank=True, default="")
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300, blank=True, default="")
    added_at = models.DateTimeField(auto_now_add=True)

    source_item = models.ForeignKey(
        ScanItem, null=True, blank=True, on_delete=models.SET_NULL
    )
    # True when the user corrected or typed this rather than accepting a match.
    manually_entered = models.BooleanField(default=False)

    class Meta:
        ordering = ["author", "title"]

    def __str__(self):
        return f"{self.title} — {self.author}"
