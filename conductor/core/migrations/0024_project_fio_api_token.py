# Copyright 2022 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 3.1.7 on 2022-07-28 09:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_project_create_ota_commit'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='fio_api_token',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
    ]
