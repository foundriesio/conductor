# Generated by Django 4.0.4 on 2024-06-13 09:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('testplan', '0010_alter_boot_prompts'),
    ]

    operations = [
        migrations.CreateModel(
            name='TestMonitor',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('start', models.CharField(max_length=256)),
                ('end', models.CharField(max_length=256)),
                ('pattern', models.CharField(default='_unused_', max_length=256)),
            ],
        ),
        migrations.AlterField(
            model_name='testdefinition',
            name='testtype',
            field=models.CharField(choices=[('git', 'git'), ('interactive', 'interactive'), ('monitor', 'monitor')], default='git', max_length=16),
        ),
        migrations.AddField(
            model_name='testdefinition',
            name='test_monitor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='testplan.testmonitor'),
        ),
    ]
