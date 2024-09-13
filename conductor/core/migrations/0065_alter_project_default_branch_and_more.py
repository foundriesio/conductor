# Generated by Django 4.2.13 on 2024-08-12 12:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0064_project_is_parent_factory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='default_branch',
            field=models.CharField(default='main', max_length=16),
        ),
        migrations.AlterField(
            model_name='project',
            name='default_container_branch',
            field=models.CharField(default='main', max_length=64),
        ),
        migrations.AlterField(
            model_name='project',
            name='default_meta_branch',
            field=models.CharField(default='main', help_text='Default branch to monitor in meta-subscriber-overrides repository', max_length=64),
        ),
    ]