# Generated by Django 4.2.13 on 2024-08-09 14:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0063_project_forked_from'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='is_parent_factory',
            field=models.BooleanField(default=False),
        ),
    ]
