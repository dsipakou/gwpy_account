# Generated by Django 4.0.4 on 2022-06-21 07:26

from django.db import migrations


def set_base_currency(apps, schema_editor):
    Rate = apps.get_model("rates", "Rate")
    Currency = apps.get_model("currencies", "Currency")
    if len(Rate.objects.all()) > 0:
        rates = Rate.objects.filter(base_currency=None).select_for_update()
        rates.update(base_currency=Currency.objects.get(is_base=True))


class Migration(migrations.Migration):

    dependencies = [
        ("rates", "0002_rate_base_currency"),
    ]

    operations = [migrations.RunPython(set_base_currency, migrations.RunPython.noop)]
