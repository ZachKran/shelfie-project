from rest_framework import serializers

from .models import LibraryBook, Scan, ScanItem


class ScanItemSerializer(serializers.ModelSerializer):
    crop_url = serializers.SerializerMethodField()

    class Meta:
        model = ScanItem
        fields = [
            "id", "index", "box", "detector_confidence", "crop_url",
            "read_title", "read_author", "read_error",
            "status", "confidence", "match_id", "candidates", "resolved",
        ]

    def get_crop_url(self, obj):
        if not obj.crop:
            return None
        request = self.context.get("request")
        url = obj.crop.url
        return request.build_absolute_uri(url) if request else url


class ScanSerializer(serializers.ModelSerializer):
    items = ScanItemSerializer(many=True, read_only=True)
    timings = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Scan
        fields = ["id", "created_at", "error", "timings", "counts", "items"]

    def get_timings(self, obj):
        return {
            "detect_ms": obj.detect_ms,
            "vlm_ms": obj.vlm_ms,
            "match_ms": obj.match_ms,
            "total_ms": obj.total_ms,
            "vlm_input_tokens": obj.vlm_input_tokens,
            "vlm_output_tokens": obj.vlm_output_tokens,
        }

    def get_counts(self, obj):
        counts = {"matched": 0, "review": 0, "unmatched": 0, "unreadable": 0, "skipped": 0}
        for item in obj.items.all():
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts


class LibraryBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibraryBook
        fields = [
            "id", "catalog_id", "title", "author", "added_at",
            "source_item", "manually_entered",
        ]
        read_only_fields = ["added_at"]
