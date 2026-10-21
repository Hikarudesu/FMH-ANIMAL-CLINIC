from django.core.management.base import BaseCommand

from notifications.utils import expire_follow_up_recommendations


class Command(BaseCommand):
    help = 'Expire missed follow-up recommendations and cancel missed return visits.'

    def handle(self, *args, **options):
        expired = expire_follow_up_recommendations()
        self.stdout.write(f'Expired {expired} follow-up recommendation(s).')
