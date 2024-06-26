# Copyright 2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2024-01-11 17:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0056_migrate_arm64_aarch64'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lavadevicetype',
            name='architecture',
            field=models.CharField(choices=[('armhf', 'armhf'), ('aarch64', 'aarch64'), ('amd64', 'amd64')], default='aarch64', max_length=8),
        ),
    ]
