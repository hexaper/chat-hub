from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rooms', '0008_roomchatmessage_delete_device'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatmessage',
            name='updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chatmessage',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
