"""Account-related signals."""
import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(pre_save, sender=User)
def superuser_email_auto_verified(sender, instance, **kwargs):
    """Superusers never need email verification — mark verified on create/promote."""
    if getattr(instance, "is_superuser", False):
        instance.is_email_verified = True


@receiver(post_save, sender=User)
def attach_superuser_to_platform_company(sender, instance, **kwargs):
    """When a user is (or becomes) superuser, add them as SURVERA company admin."""
    if not instance.is_superuser or not instance.is_active:
        return
    try:
        from apps.companies.services import ensure_superuser_on_platform

        ensure_superuser_on_platform(instance)
    except Exception:
        logger.exception(
            "Failed to attach superuser %s to platform company",
            getattr(instance, "pk", None),
        )


@receiver(post_save, sender=User)
def grant_registration_honor_on_create(sender, instance, created, **kwargs):
    """+10 honor once for every new account."""
    if not created:
        return
    try:
        from apps.accounts.honor import grant_registration_honor

        grant_registration_honor(instance)
    except Exception:
        logger.exception(
            "Failed to grant registration honor user_id=%s",
            getattr(instance, "pk", None),
        )
