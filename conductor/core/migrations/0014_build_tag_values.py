from django.db import migrations

def fill_in_build_tag(apps, schema_editor):
    Build = apps.get_model('core', 'Build')
    for build in Build.objects.all():
        build.tag = "master"
        build.save()

def revert_tag_fill_in(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_build_tag'),
    ]

    operations = [
        migrations.RunPython(fill_in_build_tag, revert_tag_fill_in),
    ]
