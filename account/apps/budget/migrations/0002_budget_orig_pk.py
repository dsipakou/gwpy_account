# Generated by Django 4.0.4 on 2022-04-26 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="orig_pk",
            field=models.IntegerField(null=True),
        ),
    ]
