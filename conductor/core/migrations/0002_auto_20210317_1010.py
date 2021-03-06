# Copyright 2021 Foundries.io
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Generated by Django 3.1.7 on 2021-03-17 10:10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PDUAgent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('state', models.CharField(choices=[('Online', 'Online'), ('Offline', 'Offline')], default='Offline', max_length=16)),
                ('last_ping', models.DateTimeField(blank=True, null=True)),
                ('version', models.CharField(max_length=32)),
                ('token', models.CharField(max_length=64)),
            ],
        ),
        migrations.AddField(
            model_name='lavadevice',
            name='controlled_by',
            field=models.CharField(choices=[('LAVA', 'Lava'), ('PDU', 'PDU')], default='LAVA', max_length=16),
        ),
        migrations.AddField(
            model_name='lavadevice',
            name='pduagent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.pduagent'),
        ),
    ]
