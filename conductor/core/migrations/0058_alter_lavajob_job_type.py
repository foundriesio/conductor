# Copyright 2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2024-01-24 12:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0057_alter_lavadevicetype_architecture'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lavajob',
            name='job_type',
            field=models.CharField(choices=[('LAVA', 'Lava'), ('OTA', 'OTA'), ('EL2GO', 'EL2GO'), ('ASM', 'Assemble')], default='LAVA', max_length=16),
        ),
    ]
