# Copyright 2022 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

# Generated by Django 4.1 on 2022-08-26 13:28

from django.db import migrations, models
import django.db.models.deletion
import sortedm2m.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='AutoLogin',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('login_prompt', models.CharField(max_length=32)),
                ('password_prompt', models.CharField(max_length=32)),
                ('username', models.CharField(max_length=32)),
                ('password', models.CharField(max_length=32)),
                ('login_commands', models.TextField(blank=True, null=True)),
                ('name', models.CharField(max_length=32)),
            ],
        ),
        migrations.CreateModel(
            name='DeployPostprocess',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.CharField(max_length=128)),
                ('name', models.CharField(max_length=128)),
                ('steps', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='DownloadImage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='image', max_length=32)),
                ('url', models.CharField(max_length=256)),
                ('compression', models.CharField(blank=True, max_length=8, null=True)),
                ('headers', models.TextField(blank=True, null=True)),
                ('image_arg', models.CharField(blank=True, max_length=256, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='InteractiveCommand',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('command', models.CharField(max_length=256)),
                ('name', models.CharField(max_length=32)),
                ('wait_for_prompt', models.BooleanField(default=False)),
                ('success_messages', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='LAVAAction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('namespace', models.CharField(blank=True, max_length=64, null=True)),
                ('connection_namespace', models.CharField(blank=True, max_length=64, null=True)),
                ('action_type', models.CharField(choices=[('deploy', 'deploy'), ('boot', 'boot'), ('command', 'command'), ('test', 'test')], max_length=16)),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_%(app_label)s.%(class)s_set+', to='contenttypes.contenttype')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='TestJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('priority', models.IntegerField(default=50)),
                ('visibility', models.CharField(choices=[('public', 'public'), ('group', 'group'), ('private', 'private')], default='public', max_length=8)),
                ('is_ota_job', models.BooleanField(default=False)),
                ('actions', sortedm2m.fields.SortedManyToManyField(help_text=None, to='testplan.lavaaction')),
            ],
        ),
        migrations.CreateModel(
            name='TestJobContext',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('context', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='TestJobMetadata',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('metadata', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Timeout',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
                ('timeout_units', models.CharField(choices=[('minutes', 'minutes'), ('seconds', 'seconds')], max_length=16)),
                ('timeout_value', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='CommandAction',
            fields=[
                ('lavaaction_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='testplan.lavaaction')),
                ('name', models.CharField(max_length=32)),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('testplan.lavaaction',),
        ),
        migrations.CreateModel(
            name='TestPlan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
                ('lava_device_type', models.CharField(max_length=32)),
                ('testjobs', sortedm2m.fields.SortedManyToManyField(help_text=None, to='testplan.testjob')),
            ],
        ),
        migrations.AddField(
            model_name='testjob',
            name='context',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='testplan.testjobcontext'),
        ),
        migrations.AddField(
            model_name='testjob',
            name='metadata',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='testplan.testjobmetadata'),
        ),
        migrations.AddField(
            model_name='testjob',
            name='timeouts',
            field=models.ManyToManyField(to='testplan.timeout'),
        ),
        migrations.CreateModel(
            name='TestDefinition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('testtype', models.CharField(choices=[('git', 'git'), ('interactive', 'interactive')], default='git', max_length=16)),
                ('name', models.CharField(max_length=128)),
                ('device_type', models.CharField(blank=True, max_length=32, null=True)),
                ('path', models.CharField(blank=True, max_length=256, null=True)),
                ('repository', models.CharField(blank=True, max_length=256, null=True)),
                ('parameters', models.TextField(blank=True)),
                ('prompts', models.TextField(default='[]')),
                ('interactive_commands', sortedm2m.fields.SortedManyToManyField(blank=True, help_text=None, to='testplan.interactivecommand')),
            ],
        ),
        migrations.AddField(
            model_name='lavaaction',
            name='timeout',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='testplan.timeout'),
        ),
        migrations.CreateModel(
            name='TestAction',
            fields=[
                ('lavaaction_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='testplan.lavaaction')),
                ('name', models.CharField(max_length=32)),
                ('definitions', sortedm2m.fields.SortedManyToManyField(help_text=None, to='testplan.testdefinition')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('testplan.lavaaction',),
        ),
        migrations.CreateModel(
            name='Deployment',
            fields=[
                ('lavaaction_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='testplan.lavaaction')),
                ('deploy_to', models.CharField(choices=[('download', 'download'), ('downloads', 'downloads'), ('tmpfs', 'tmpfs'), ('flasher', 'flasher')], max_length=16)),
                ('name', models.CharField(blank=True, max_length=32, null=True)),
                ('images', models.ManyToManyField(to='testplan.downloadimage')),
                ('postprocess', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='testplan.deploypostprocess')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('testplan.lavaaction',),
        ),
        migrations.CreateModel(
            name='Boot',
            fields=[
                ('lavaaction_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='testplan.lavaaction')),
                ('prompts', models.TextField()),
                ('method', models.CharField(choices=[('minimal', 'minimal')], max_length=32)),
                ('transfer_overlay', models.BooleanField(default=True)),
                ('transfer_overlay_download', models.CharField(blank=True, max_length=512, null=True)),
                ('transfer_overlay_unpack', models.CharField(blank=True, max_length=512, null=True)),
                ('name', models.CharField(blank=True, max_length=32, null=True)),
                ('auto_login', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='testplan.autologin')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('testplan.lavaaction',),
        ),
    ]
