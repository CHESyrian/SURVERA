"""
Cloudflare Turnstile integration for SURVERA forms.

When TURNSTILE_ENABLED is False or keys are missing, validation is skipped
(local/dev/tests). Production should set site key + secret in the environment.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django import forms
from django.conf import settings
from django.forms.widgets import Widget
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# Cloudflare always-pass test keys (docs): safe for local/CI when enabled with dummies
TEST_SITE_KEY = "1x00000000000000000000AA"
TEST_SECRET_KEY = "1x0000000000000000000000000000000AA"


def turnstile_enabled() -> bool:
    """True when Turnstile should be enforced on forms."""
    if not getattr(settings, "TURNSTILE_ENABLED", False):
        return False
    site = (getattr(settings, "TURNSTILE_SITE_KEY", "") or "").strip()
    secret = (getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    return bool(site and secret)


def turnstile_site_key() -> str:
    return (getattr(settings, "TURNSTILE_SITE_KEY", "") or "").strip()


def verify_turnstile_token(token: str, remoteip: str | None = None) -> bool:
    """
    Verify a Turnstile response token with Cloudflare.

    Returns True on success. On network/config errors logs and returns False
    when enforcement is on.
    """
    if not turnstile_enabled():
        return True
    token = (token or "").strip()
    if not token:
        return False

    secret = (getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    data = {
        "secret": secret,
        "response": token,
    }
    if remoteip:
        data["remoteip"] = remoteip

    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        SITEVERIFY_URL,
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    timeout = float(getattr(settings, "TURNSTILE_TIMEOUT", 5))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Turnstile siteverify failed: %s", exc)
        return False

    ok = bool(payload.get("success"))
    if not ok:
        logger.info("Turnstile rejected token: %s", payload.get("error-codes"))
    return ok


class TurnstileWidget(Widget):
    template_name = None  # rendered via render()

    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.site_key = turnstile_site_key()

    def render(self, name, value, attrs=None, renderer=None):
        if not turnstile_enabled():
            return ""
        # Implicit render: Cloudflare injects a widget into this div.
        # Script is loaded once from the template (or here as a safeguard).
        site_key = self.site_key
        return (
            f'<div class="cf-turnstile mb-3" data-sitekey="{site_key}" '
            f'data-theme="auto"></div>\n'
            f'<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" '
            f'async defer></script>'
        )

    def value_from_datadict(self, data, files, name):
        # Cloudflare posts this field name regardless of Django field name.
        return data.get("cf-turnstile-response") or data.get(name)


class TurnstileField(forms.CharField):
    """
    Form field that validates Cloudflare Turnstile.

    Invisible when TURNSTILE_ENABLED is False (not required, always valid).
    """

    widget = TurnstileWidget
    default_error_messages = {
        "required": _("Please confirm you are human."),
        "invalid": _("Security check failed. Please try again."),
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", turnstile_enabled())
        kwargs.setdefault("label", "")
        super().__init__(*args, **kwargs)
        if not turnstile_enabled():
            self.required = False

    def clean(self, value):
        if not turnstile_enabled():
            return ""
        value = super().clean(value)
        # remote IP is optional; forms don't always have request — view may re-check
        if not verify_turnstile_token(value or ""):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        return value


def maybe_add_turnstile(form: forms.BaseForm, field_name: str = "captcha") -> None:
    """Attach a TurnstileField to a form instance when enforcement is on."""
    if turnstile_enabled():
        form.fields[field_name] = TurnstileField()
    elif field_name in form.fields:
        del form.fields[field_name]
