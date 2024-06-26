# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 3.1.7 on 2021-08-10 09:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_build_tag_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='build',
            name='build_reason',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name='build',
            name='schedule_tests',
            field=models.BooleanField(default=True),
        ),
    ]
