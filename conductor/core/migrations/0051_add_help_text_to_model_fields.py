# Copyright 2023 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.0.4 on 2023-11-20 14:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_project_fio_force_kernel_rebuild'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='apply_tag_to_first_build_only',
            field=models.BooleanField(default=False, help_text='When set to true, testing_tag is not applied to the OTA build.'),
        ),
        migrations.AlterField(
            model_name='project',
            name='create_containers_commit',
            field=models.BooleanField(default=False, help_text='If set to true OTA commit will be created in the containers repository'),
        ),
        migrations.AlterField(
            model_name='project',
            name='default_meta_branch',
            field=models.CharField(default='master', help_text='Default branch to monitor in meta-subscriber-overrides repository', max_length=64),
        ),
        migrations.AlterField(
            model_name='project',
            name='el2go_product_id',
            field=models.CharField(blank=True, help_text='12NC number for the SE05x device. This field will be moved to the LAVADevice. For now all devices in the factory have to use the same SE05x chip.', max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='lava_header',
            field=models.CharField(blank=True, help_text='Name of LAVA header created in LAVA profile. Header should be created for the user submitting test jobs', max_length=23, null=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='name',
            field=models.CharField(help_text='The name of the Foundries Factory', max_length=32),
        ),
        migrations.AlterField(
            model_name='project',
            name='privkey',
            field=models.TextField(blank=True, help_text='TUF private key for signing targets', null=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='qa_reports_project_name',
            field=models.CharField(blank=True, help_text='When not empty this name is used as a project name in SQUAD.', max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='secret',
            field=models.CharField(help_text='Secret set in the Foundries Factory usign fioctl. The secret is sent by jobserv callback.', max_length=128),
        ),
        migrations.AlterField(
            model_name='project',
            name='squad_backend',
            field=models.ForeignKey(blank=True, help_text='Name of the SQUAD instance to use for reporing of this project.', null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.squadbackend'),
        ),
        migrations.AlterField(
            model_name='project',
            name='squad_group',
            field=models.CharField(blank=True, help_text='Name of the group in SQUAD instance where this project data is reported. SQUAD project name by default is the same as this project name.', max_length=16, null=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='test_on_merge_only',
            field=models.BooleanField(default=False, help_text='If set to true testing will be triggered only on merges from lmp-manifest.'),
        ),
        migrations.AlterField(
            model_name='project',
            name='testing_tag',
            field=models.CharField(blank=True, help_text='This tag will be applied to the targets in the Foundries Factory on successful build.', max_length=16, null=True),
        ),
    ]
