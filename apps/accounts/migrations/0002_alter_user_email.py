from django.db import migrations, models


def deduplicate_emails(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    # Blank strings → NULL
    User.objects.filter(email='').update(email=None)
    # Duplicate non-null emails → NULL (keep lowest pk)
    seen = set()
    for user in User.objects.exclude(email=None).order_by('pk'):
        key = user.email.lower()
        if key in seen:
            user.email = None
            user.save(update_fields=['email'])
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        # Step 1: drop NOT NULL so RunPython can write NULLs
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        # Step 2: normalise existing data before adding the unique constraint
        migrations.RunPython(deduplicate_emails, migrations.RunPython.noop),
        # Step 3: add UNIQUE (safe now that duplicates/blanks are gone)
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True),
        ),
    ]
