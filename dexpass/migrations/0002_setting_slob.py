
from django.db import migrations, models


def settings_yay(apps, schema_editor):
    DexPassSettings = apps.get_model("dexpass", "DexPassSettings")

    DexPassSettings.objects.get_or_create(
        pass_name="DexPass",
        defaults={
            "enabled": True,
        },
    )


class Migration(migrations.Migration):

    initial = False

    dependencies = [
        ("dexpass", "0001_initial"),
    ]
    
    operations = [
        migrations.RunPython(settings_yay),
    ]
