# Generated by Django 4.0.4 on 2023-07-18 09:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_clone_meta_repositories'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='fio_meds_domain',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]