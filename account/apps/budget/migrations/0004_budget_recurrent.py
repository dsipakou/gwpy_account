# Generated by Django 4.0.4 on 2022-06-27 15:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0003_remove_budget_orig_pk"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="recurrent",
            field=models.CharField(
                blank=True,
                choices=[("weekly", "Weekly"), ("monthly", "Monthly")],
                max_length=20,
                null=True,
            ),
        ),
    ]
