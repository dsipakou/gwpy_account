# Generated by Django 4.2.5 on 2024-01-18 16:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0020_alter_budget_budget_date"),
    ]

    operations = [
        migrations.AlterField(
            model_name="budget",
            name="description",
            field=models.TextField(blank=True, null=True),
        ),
    ]
