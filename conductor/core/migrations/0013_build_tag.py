# Generated by Django 3.1.7 on 2021-08-03 12:20
#
# SPDX-License-Identifier: BSD-3-Clause

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_project_lava_backend'),
    ]

    operations = [
        migrations.AddField(
            model_name='build',
            name='tag',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
    ]
