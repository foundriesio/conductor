# Generated by Django 4.2.13 on 2024-07-03 09:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('testplan', '0011_testmonitor_alter_testdefinition_testtype_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='testjob',
            name='visibility',
            field=models.CharField(choices=[('public', 'public'), ('group', 'group'), ('personal', 'personal')], default='public', max_length=8),
        ),
    ]