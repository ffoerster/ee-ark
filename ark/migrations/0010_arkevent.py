from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ark", "0009_ark_tombstone_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArkEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("mint", "mint"),
                            ("update", "update"),
                            ("batch_mint", "batch_mint"),
                            ("batch_update", "batch_update"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "actor_key_hash",
                    models.CharField(blank=True, default="", max_length=4096),
                ),
                (
                    "ip",
                    models.GenericIPAddressField(blank=True, default="", null=True),
                ),
                ("diff_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "ark",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="ark.ark",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="arkevent",
            index=models.Index(fields=["ark", "-created_at"], name="ark_ark_crea_047fb2_idx"),
        ),
    ]
