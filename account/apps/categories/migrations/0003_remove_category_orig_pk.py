# Generated by Django 4.0.4 on 2022-04-18 08:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("categories", "0002_category_orig_pk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="category",
            name="orig_pk",
        ),
    ]
