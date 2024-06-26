# Generated by Django 4.0.4 on 2022-10-06 11:38

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0005_rename_transactionamount_transactionmulticurrency"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transactionmulticurrency",
            name="transaction",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="multicurrency",
                to="transactions.transaction",
                to_field="uuid",
            ),
        ),
    ]
