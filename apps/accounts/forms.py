"""Authentication and profile forms for SURVERA."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from apps.common.turnstile import TurnstileField, turnstile_enabled
from apps.notifications.preferences import NotificationPreference

User = get_user_model()

PASSWORD_INPUT_ATTRS = {
    "class": "form-control",
    "autocomplete": "new-password",
}
PASSWORD_CURRENT_ATTRS = {
    "class": "form-control",
    "autocomplete": "current-password",
}


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(
            attrs={"class": "form-control", "autocomplete": "email", "id": "id_email"}
        ),
    )
    username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "autocomplete": "username",
                "id": "id_username",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("email", "username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(
            {
                **PASSWORD_INPUT_ATTRS,
                "id": "id_password1",
                "data-pw-meter": "1",
                "minlength": "8",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                **PASSWORD_INPUT_ATTRS,
                "id": "id_password2",
                "autocomplete": "new-password",
            }
        )
        self.fields["password1"].help_text = _(
            "At least 8 characters. Prefer a mix of letters, numbers, and symbols."
        )
        if turnstile_enabled():
            self.fields["captcha"] = TurnstileField()

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower().strip()
        user.user_type = User.UserType.PERSON
        user.is_email_verified = False
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "autocomplete": "email",
                "id": "id_username",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                **PASSWORD_CURRENT_ATTRS,
                "id": "id_password",
            }
        ),
    )


    def confirm_login_allowed(self, user):
        """Block frozen or permanently closed accounts."""
        super().confirm_login_allowed(user)
        reason = getattr(user, "moderation_block_reason", lambda: None)()
        if reason:
            raise forms.ValidationError(reason, code="account_moderation")


class VerifyEmailForm(forms.Form):
    code = forms.CharField(
        label=_("Verification code"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg text-center letter-spacing",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "autocomplete": "one-time-code",
                "placeholder": "000000",
                "id": "id_code",
                "maxlength": "6",
            }
        ),
    )

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError(_("Enter the 6-digit code from your email."))
        return code


class ResendVerificationForm(forms.Form):
    """Resend code — protected by Turnstile when enabled."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if turnstile_enabled():
            self.fields["captcha"] = TurnstileField()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "language", "date_of_birth", "gender")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "language": forms.Select(attrs={"class": "form-select"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
        }


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = (
            "inapp_survey_published",
            "inapp_points_awarded",
            "inapp_team_invite",
            "inapp_system",
            "email_survey_published",
            "email_points_awarded",
            "email_team_invite",
            "email_system",
            "email_digest",
        )
        widgets = {
            "inapp_survey_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "inapp_points_awarded": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "inapp_team_invite": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "inapp_system": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "email_survey_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "email_points_awarded": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "email_team_invite": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "email_system": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "email_digest": forms.Select(attrs={"class": "form-select form-select-sm"}),
        }
