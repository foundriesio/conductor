# Copyright 2023 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2023-08-22 13:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0044_remove_build_schedule_tests'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='test_static_delta',
            field=models.BooleanField(default=True),
        ),
    ]
