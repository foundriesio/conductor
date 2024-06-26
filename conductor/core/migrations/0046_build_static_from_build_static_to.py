# Copyright 2023 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2023-08-23 13:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0045_project_test_static_delta'),
    ]

    operations = [
        migrations.AddField(
            model_name='build',
            name='static_from',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='staticfrom', to='core.build'),
        ),
        migrations.AddField(
            model_name='build',
            name='static_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='staticto', to='core.build'),
        ),
    ]
