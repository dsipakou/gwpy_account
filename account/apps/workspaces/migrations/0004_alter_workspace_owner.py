# Generated by Django 4.2 on 2023-08-02 14:10

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("workspaces", "0003_workspace_created_at_workspace_modified_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workspace",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspace_owner",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]