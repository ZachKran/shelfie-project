import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Scan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="scans/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("detect_ms", models.IntegerField(blank=True, null=True)),
                ("vlm_ms", models.IntegerField(blank=True, null=True)),
                ("match_ms", models.IntegerField(blank=True, null=True)),
                ("total_ms", models.IntegerField(blank=True, null=True)),
                ("vlm_input_tokens", models.IntegerField(blank=True, null=True)),
                ("vlm_output_tokens", models.IntegerField(blank=True, null=True)),
                ("error", models.TextField(blank=True, default="")),
            ],
        ),
        migrations.CreateModel(
            name="ScanItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("index", models.IntegerField()),
                ("box", models.JSONField(default=list)),
                ("detector_confidence", models.FloatField(blank=True, null=True)),
                ("crop", models.ImageField(blank=True, null=True, upload_to="crops/")),
                ("read_title", models.CharField(blank=True, default="", max_length=500)),
                ("read_author", models.CharField(blank=True, default="", max_length=300)),
                ("read_error", models.TextField(blank=True, default="")),
                ("status", models.CharField(choices=[("matched", "Matched"), ("review", "Needs review"), ("unmatched", "No catalog match"), ("unreadable", "Could not be read")], max_length=20)),
                ("confidence", models.FloatField(default=0.0)),
                ("match_id", models.CharField(blank=True, default="", max_length=100)),
                ("candidates", models.JSONField(default=list)),
                ("resolved", models.BooleanField(default=False)),
                ("scan", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="scanner.scan")),
            ],
            options={"ordering": ["index"], "unique_together": {("scan", "index")}},
        ),
        migrations.CreateModel(
            name="LibraryBook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("catalog_id", models.CharField(blank=True, default="", max_length=100)),
                ("title", models.CharField(max_length=500)),
                ("author", models.CharField(blank=True, default="", max_length=300)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                ("manually_entered", models.BooleanField(default=False)),
                ("source_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="scanner.scanitem")),
            ],
            options={"ordering": ["author", "title"]},
        ),
    ]
