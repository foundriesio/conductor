from django.db import migrations, models

def move_arm64_to_aarch64(apps, schema_editor):
    LAVADeviceType = apps.get_model("core", "LAVADeviceType")
    for dev_type in LAVADeviceType.objects.filter(architecture="arm64"):
        dev_type.architecture = "aarch64"
        dev_type.save()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0055_alter_lavadevicetype_architecture'),
    ]

    operations = [
        migrations.RunPython(move_arm64_to_aarch64),
    ]

