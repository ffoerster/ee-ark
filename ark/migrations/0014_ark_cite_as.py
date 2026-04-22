from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ark", "0013_alter_ark_related_arks"),
    ]

    operations = [
        migrations.AddField(
            model_name="ark",
            name="cite_as",
            field=models.TextField(blank=True, default=""),
        ),
    ]
