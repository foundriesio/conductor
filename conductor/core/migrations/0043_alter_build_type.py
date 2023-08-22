from django.db import migrations, models
from conductor.core.models import Build as BuildModel

def update_build_type(apps, schema_editor):
    Build = apps.get_model("core", "Build")
    for build in Build.objects.all():
        if not build.schedule_tests:
            build.build_type = BuildModel.BUILD_TYPE_OTA
            build.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_build_build_type'),
    ]

    operations = [
        migrations.RunPython(update_build_type),
    ]

