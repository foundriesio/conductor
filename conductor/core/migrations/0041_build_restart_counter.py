# Copyright 2023 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2023-08-15 12:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0040_build_built_trigger'),
    ]

    operations = [
        migrations.AddField(
            model_name='build',
            name='restart_counter',
            field=models.IntegerField(default=0),
        ),
    ]
