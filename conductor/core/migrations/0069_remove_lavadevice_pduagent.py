# Generated by Django 4.2.13 on 2024-09-24 19:39

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0068_alter_lavajob_job_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='lavadevice',
            name='pduagent',
        ),
    ]
