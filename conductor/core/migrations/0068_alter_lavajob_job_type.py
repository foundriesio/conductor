# Generated by Django 4.2.13 on 2024-09-24 13:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0067_alter_project_disabled'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lavajob',
            name='job_type',
            field=models.CharField(choices=[('LAVA', 'Lava'), ('EL2GO', 'EL2GO'), ('ASM', 'Assemble')], default='LAVA', max_length=16),
        ),
    ]