# Generated by Django 4.0.4 on 2022-05-05 09:51

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_account_orig_pk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="account",
            name="orig_pk",
        ),
    ]