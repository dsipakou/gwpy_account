# Generated by Django 4.0.4 on 2022-04-17 06:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="orig_pk",
            field=models.IntegerField(default=-1),
            preserve_default=False,
        ),
    ]
