# Generated by Django 4.2.13 on 2024-09-24 19:41

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0069_remove_lavadevice_pduagent'),
    ]

    operations = [
        migrations.DeleteModel(
            name='PDUAgent',
        ),
    ]
