from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.rooms.models import Room


class Command(BaseCommand):
    help = 'Deactivate rooms that have been empty for 15+ minutes'

    def handle(self, *args, **options):
        threshold = timezone.now() - timedelta(minutes=15)
        count = Room.objects.filter(
            is_active=True,
            last_empty_at__isnull=False,
            last_empty_at__lte=threshold,
        ).update(is_active=False)
        self.stdout.write(f'Deactivated {count} stale room(s).')
