from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rooms', '0009_chatmessage_updated_at_deleted_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='roomchatmessage',
            name='updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='roomchatmessage',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
