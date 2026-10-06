"""Turnstile helpers — enabled flag and field behaviour."""
from django import forms
from django.test import SimpleTestCase, override_settings

from apps.common.turnstile import TurnstileField, turnstile_enabled, verify_turnstile_token


class TurnstileDisabledTests(SimpleTestCase):
    def test_disabled_by_default_in_spirit(self):
        # With empty keys, even if ENABLED, turnstile_enabled is False
        with override_settings(TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY=""):
            self.assertFalse(turnstile_enabled())

    @override_settings(TURNSTILE_ENABLED=False, TURNSTILE_SITE_KEY="x", TURNSTILE_SECRET_KEY="y")
    def test_disabled_flag(self):
        self.assertFalse(turnstile_enabled())
        self.assertTrue(verify_turnstile_token(""))

    @override_settings(
        TURNSTILE_ENABLED=True,
        TURNSTILE_SITE_KEY="1x00000000000000000000AA",
        TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
    )
    def test_enabled_with_keys(self):
        self.assertTrue(turnstile_enabled())

    @override_settings(TURNSTILE_ENABLED=False)
    def test_field_not_required_when_disabled(self):
        class F(forms.Form):
            captcha = TurnstileField()

        f = F(data={})
        self.assertTrue(f.is_valid())
