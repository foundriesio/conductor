# Generated by Django 4.0.4 on 2023-07-19 10:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_project_fio_meds_domain'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='lava_header',
            field=models.CharField(blank=True, max_length=23, null=True),
        ),
    ]