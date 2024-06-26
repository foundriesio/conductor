# Generated by Django 3.1.7 on 2021-05-18 12:20
#
# SPDX-License-Identifier: BSD-3-Clause

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_lavabackend'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='lava_api_token',
        ),
        migrations.RemoveField(
            model_name='project',
            name='lava_url',
        ),
        migrations.RemoveField(
            model_name='project',
            name='websocket_url',
        ),
        migrations.AddField(
            model_name='project',
            name='lava_backend',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.lavabackend'),
        ),
    ]
