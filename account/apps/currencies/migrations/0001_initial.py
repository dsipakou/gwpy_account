# Generated by Django 4.0.4 on 2022-04-15 15:37

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Currency",
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
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("code", models.CharField(max_length=5, unique=True)),
                ("sign", models.CharField(max_length=2)),
                ("verbal_name", models.CharField(max_length=30)),
                ("comments", models.CharField(blank=True, max_length=255)),
                ("is_base", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]