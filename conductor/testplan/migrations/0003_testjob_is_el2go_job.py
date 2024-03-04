# Copyright 2022 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2022-09-28 10:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('testplan', '0002_alter_testjob_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='testjob',
            name='is_el2go_job',
            field=models.BooleanField(default=False),
        ),
    ]
