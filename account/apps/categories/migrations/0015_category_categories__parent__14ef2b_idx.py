# Generated by Django 4.2.11 on 2025-03-11 18:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0014_update_positions"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="category",
            index=models.Index(
                fields=["parent", "position"], name="categories__parent__14ef2b_idx"
            ),
        ),
    ]
