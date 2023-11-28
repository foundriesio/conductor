from django.db import migrations, models

def update_device_architecture(apps, schema_editor):
    dev_mapping = {
        "imx8mmevk": "arm64",
        "raspberrypi4-64": "arm64",
        "imx6ullevk": "armhf",
        "stm32mp15-disco": "armhf",
        "am64xx-evm": "arm64",
        "imx8mp-lpddr4-evk": "arm64",
        "imx8mq-evk": "arm64",
        "imx8mm-lpddr4-evk-sec": "arm64",
        "intel-corei7-64": "amd64",
        "qemuarm64-securebot": "arm64",
        "imx8mm-lpddr4-evk-sec": "arm64",
        "imx8mm-lpddr4-evk-sec-se050": "arm64",
        "imx8mm-lpddr4-evk": "arm64",
        "imx6ullevk-sec": "armhf",
        "imx8mm-lpddr4-evk-xeno4": "arm64",
        "imx8mn-lpddr4-evk": "arm64",
        "imx8mn-ddr4-evk": "arm64",
        "imx93-11x11-lpddr4x-evk": "arm64",
        "imx8ulp-lpddr4-evk": "arm64",
        "portenta-x8": "arm64",
    }
    LAVADeviceType = apps.get_model("core", "LAVADeviceType")
    for dev_type in LAVADeviceType.objects.all():
        architecture = dev_mapping.get(dev_type.name)
        if architecture:
            dev_type.architecture = architecture
            dev_type.save()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0053_lavadevicetype_architecture'),
    ]

    operations = [
        migrations.RunPython(update_device_architecture),
    ]

