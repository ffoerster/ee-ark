# Generated by Django 4.0.4 on 2023-07-19 21:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ark", "0004_rename_commitment_ark_rights_ark_format_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="key",
            name="key",
            field=models.CharField(max_length=4096, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="key",
            name="active",
            field=models.BooleanField(default=True),
        ),
    ]
