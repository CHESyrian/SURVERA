"""Account views: registration, login, logout, profile, email verification."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    LoginForm,
    NotificationPreferenceForm,
    ProfileForm,
    RegisterForm,
    ResendVerificationForm,
    VerifyEmailForm,
)
from .verification import (
    can_resend_code,
    issue_and_send_code,
    seconds_until_resend_allowed,
    verify_code,
)


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            # First code after register: no prior codes → rate limit does not block.
            code, msg = issue_and_send_code(user)
            if code:
                messages.success(
                    request,
                    _("Account created. Check your email for a 6-digit verification code."),
                )
            else:
                messages.warning(
                    request,
                    _(
                        "Account created, but we could not send the verification email. "
                        "You can resend the code from the verification page."
                    ),
                )
            return redirect("accounts:verify_email")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


class SurveraLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class SurveraLogoutView(LogoutView):
    next_page = reverse_lazy("home")


@login_required
@require_http_methods(["GET", "POST"])
def verify_email(request):
    """Enter the 6-digit code sent to the user's email."""
    if request.user.is_email_verified:
        messages.info(request, _("Your email is already verified."))
        return redirect("home")

    form = VerifyEmailForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ok, msg = verify_code(request.user, form.cleaned_data["code"])
        if ok:
            messages.success(request, msg)
            next_url = request.GET.get("next") or request.POST.get("next") or "home"
            if isinstance(next_url, str) and next_url.startswith("/"):
                return redirect(next_url)
            return redirect("home")
        messages.error(request, msg)

    resend_allowed, resend_wait = can_resend_code(request.user)
    return render(
        request,
        "accounts/verify_email.html",
        {
            "form": form,
            "resend_form": ResendVerificationForm(),
            "email": request.user.email,
            "resend_allowed": resend_allowed,
            "resend_wait": resend_wait,
        },
    )


@login_required
@require_POST
def resend_verification(request):
    if request.user.is_email_verified:
        messages.info(request, _("Your email is already verified."))
        return redirect("home")
    resend_form = ResendVerificationForm(request.POST)
    if not resend_form.is_valid():
        for err in resend_form.errors.get("captcha", []):
            messages.error(request, err)
        if not resend_form.errors.get("captcha"):
            messages.error(request, _("Security check failed. Please try again."))
        return redirect("accounts:verify_email")
    code, msg = issue_and_send_code(request.user)
    if code:
        messages.success(request, msg)
    else:
        # Rate limit or send failure — message already localized.
        wait = seconds_until_resend_allowed(request.user)
        if wait > 0:
            messages.warning(request, msg)
        else:
            messages.error(request, msg)
    return redirect("accounts:verify_email")


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    from apps.notifications.preferences import get_or_create_preferences

    prefs = get_or_create_preferences(request.user)
    prefs_form = NotificationPreferenceForm(instance=prefs)
    form = ProfileForm(instance=request.user)
    active_tab = "dashboard"

    if request.method == "POST":
        which = request.POST.get("form_id", "profile")
        if which == "notifications":
            active_tab = "notifications"
            prefs_form = NotificationPreferenceForm(request.POST, instance=prefs)
            if prefs_form.is_valid():
                prefs_form.save()
                messages.success(request, _("Notification preferences saved."))
                return redirect(f"{request.path}?tab=notifications")
        else:
            active_tab = "info"
            form = ProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                request.user.refresh_from_db()
                try:
                    from apps.rewards.services import award_xp_for_profile_complete

                    award_xp_for_profile_complete(user=request.user)
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception(
                        "XP profile-complete failed user_id=%s", request.user.pk
                    )
                try:
                    from apps.accounts.honor import grant_profile_basic_honor

                    grant_profile_basic_honor(request.user)
                except Exception:
                    import logging

                    logging.getLogger(__name__).exception(
                        "Honor profile-basic failed user_id=%s", request.user.pk
                    )
                messages.success(request, _("Profile updated."))
                return redirect(f"{request.path}?tab=info")
    else:
        tab_q = (request.GET.get("tab") or "").strip().lower()
        if tab_q in {"dashboard", "info", "notifications", "settings", "overview"}:
            active_tab = "dashboard" if tab_q in {"dashboard", "overview"} else tab_q

    progress = None
    points = 0
    badges = []
    badge_catalog = []
    badges_earned_count = 0
    xp_next = 0
    xp_current_floor = 0
    xp_into_level = 0
    xp_span = 1
    progress_pct = 0
    memberships = []

    try:
        from apps.rewards.levels import xp_for_level, xp_for_next_level
        from apps.rewards.services import (
            evaluate_badges,
            get_or_create_progress,
            get_points_balance,
            list_profile_badges,
        )

        progress = get_or_create_progress(request.user)
        points = get_points_balance(request.user)
        # Award any newly unlocked badges when visiting profile
        try:
            evaluate_badges(request.user)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "evaluate_badges failed user_id=%s", request.user.pk
            )
        badge_catalog = list_profile_badges(request.user)
        badges = [item for item in badge_catalog if item["earned"]]
        badges_earned_count = len(badges)
        xp_next = xp_for_next_level(progress.xp_total)
        xp_current_floor = xp_for_level(progress.level)
        xp_into_level = max(0, progress.xp_total - xp_current_floor)
        xp_span = max(1, xp_next - xp_current_floor)
        progress_pct = min(100, int(100 * xp_into_level / xp_span))
    except Exception:
        pass

    try:
        from apps.companies.models import CompanyMembership

        memberships = list(
            CompanyMembership.objects.filter(user=request.user, is_active=True)
            .select_related("company")
            .order_by("company__name")
        )
    except Exception:
        memberships = []

    profile_complete = bool(
        request.user.date_of_birth and (request.user.gender or "").strip()
    )

    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "prefs_form": prefs_form,
            "active_tab": active_tab,
            "progress": progress,
            "points": points,
            "badges": badges,
            "badge_catalog": badge_catalog,
            "badges_earned_count": badges_earned_count,
            "xp_next": xp_next,
            "xp_into_level": xp_into_level,
            "xp_span": xp_span,
            "progress_pct": progress_pct,
            "memberships": memberships,
            "profile_complete": profile_complete,
        },
    )


class SurveraPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")
