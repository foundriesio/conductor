# Generated by Django 4.0.4 on 2024-03-28 13:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0060_alter_build_build_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='fioctl_client_id',
            field=models.CharField(blank=True, help_text='Client ID for fioctl. Can be obtained from https://app.foundries.io/settings/credentials/', max_length=48, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='fioctl_client_secret',
            field=models.CharField(blank=True, help_text='Client secret for fioctl. Can be obtained from https://app.foundries.io/settings/credentials/', max_length=48, null=True),
        ),
    ]
