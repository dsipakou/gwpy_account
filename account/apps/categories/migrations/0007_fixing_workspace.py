# Generated by Django 4.0.4 on 2023-01-20 14:46

from django.db import migrations


def fix_workspace(apps, schema_editor):
    Workspace = apps.get_model("workspaces", "Workspace")
    Category = apps.get_model("categories", "Category")

    default_workspace = Workspace.objects.first()
    Category.objects.update(workspace=default_workspace)


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0006_category_workspace"),
    ]

    operations = [migrations.RunPython(fix_workspace, migrations.RunPython.noop)]
