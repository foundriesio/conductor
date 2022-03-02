# Generated by Django 3.1.7 on 2022-02-23 15:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_squad_backend'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='apply_testing_tag_on_callback',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='project',
            name='testing_tag',
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
    ]
