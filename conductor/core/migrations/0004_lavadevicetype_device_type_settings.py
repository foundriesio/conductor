# Generated by Django 3.1.7 on 2021-03-31 09:29

import conductor.core.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_pduagent_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='lavadevicetype',
            name='device_type_settings',
            field=models.TextField(blank=True, null=True, validators=[conductor.core.models.yaml_validator]),
        ),
    ]