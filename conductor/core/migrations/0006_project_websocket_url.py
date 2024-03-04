# Generated by Django 3.1.7 on 2021-04-15 09:59
#
# SPDX-License-Identifier: BSD-3-Clause

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_build_commit_release'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='websocket_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
