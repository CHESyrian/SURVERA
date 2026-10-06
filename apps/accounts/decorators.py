"""Auth-related view decorators for SURVERA."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.translation import gettext as _


def user_email_verified(user) -> bool:
    """True if user is authenticated and email-verified (or superuser)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(getattr(user, "is_email_verified", False))


def email_verified_required(view_func):
    """
    Require an authenticated user whose email is verified.

    Superusers are always treated as verified.
    Unverified users are redirected to the verification page.
    """

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if user_email_verified(request.user):
            return view_func(request, *args, **kwargs)
        messages.warning(
            request,
            _("Please verify your email to continue. We sent you a code."),
        )
        return redirect("accounts:verify_email")

    return _wrapped
