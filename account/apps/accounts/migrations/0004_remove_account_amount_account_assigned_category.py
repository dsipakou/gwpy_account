# Generated by Django 4.0.4 on 2022-08-16 16:25

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0005_remove_category_is_income"),
        ("accounts", "0003_remove_account_orig_pk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="account",
            name="amount",
        ),
        migrations.AddField(
            model_name="account",
            name="assigned_category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                to="categories.category",
                to_field="uuid",
            ),
        ),
    ]
