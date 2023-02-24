# Generated by Django 4.0.4 on 2022-10-18 07:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('testplan', '0005_testjobtag_testjob_tags'),
    ]

    operations = [
        migrations.AlterField(
            model_name='testaction',
            name='name',
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name='testjob',
            name='tags',
            field=models.ManyToManyField(blank=True, to='testplan.testjobtag'),
        ),
    ]