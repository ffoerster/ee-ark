from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ark", "0008_alter_shoulder_shoulder_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ark",
            name="replaced_by",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="ark",
            name="state",
            field=models.CharField(
                choices=[("active", "active"), ("tombstoned", "tombstoned")],
                default="active",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="ark",
            name="tombstone_reason",
            field=models.TextField(blank=True, default=""),
        ),
    ]
