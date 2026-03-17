import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_devices_data(apps, schema_editor):
    """Move data from devices.Device to rooms.Device if the old table exists."""
    try:
        OldDevice = apps.get_model('devices', 'Device')
        NewDevice = apps.get_model('rooms', 'Device')
        for d in OldDevice.objects.all():
            NewDevice.objects.update_or_create(
                user_id=d.user_id,
                device_id=d.device_id,
                defaults={
                    'label': d.label,
                    'device_type': d.device_type,
                    'is_default': d.is_default,
                }
            )
    except LookupError:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('rooms', '0006_chatmessage_image_alter_chatmessage_content'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_id', models.CharField(max_length=255)),
                ('label', models.CharField(blank=True, max_length=255)),
                ('device_type', models.CharField(choices=[('camera', 'Camera'), ('microphone', 'Microphone')], max_length=20)),
                ('is_default', models.BooleanField(default=False)),
                ('last_seen', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='devices', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'device_id')},
            },
        ),
        migrations.RunPython(migrate_devices_data, migrations.RunPython.noop),
    ]
