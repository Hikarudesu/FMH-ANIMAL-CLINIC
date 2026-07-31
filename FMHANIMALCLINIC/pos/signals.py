from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Sale
from .services import create_or_release_soa_for_sale


@receiver(post_save, sender=Sale)
def create_soa_on_sale_completion(sender, instance, **kwargs):
    """Generate/release SOA when a registered-customer sale is completed."""
    if instance.status == Sale.Status.COMPLETED and instance.customer:
        create_or_release_soa_for_sale(instance)
