# Generated by Django 4.0.4 on 2023-11-08 11:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0049_project_fio_lmp_manifest_branch'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='fio_force_kernel_rebuild',
            field=models.BooleanField(default=False),
        ),
    ]