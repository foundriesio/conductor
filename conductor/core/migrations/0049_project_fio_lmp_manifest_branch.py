# Copyright 2023 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2023-10-23 12:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0048_project_fio_lmp_manifest_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='fio_lmp_manifest_branch',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]
