# Generated by Django 4.0.4 on 2022-08-16 16:27

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0004_remove_account_amount_account_assigned_category"),
    ]

    operations = [
        migrations.RenameField(
            model_name="account",
            old_name="source",
            new_name="title",
        ),
        migrations.AlterUniqueTogether(
            name="account",
            unique_together={("user", "title")},
        ),
    ]