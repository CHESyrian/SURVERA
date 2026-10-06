"""Notification list and read actions."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from .models import Notification
from .services import mark_all_read, mark_read, notify_user, unread_count, user_notifications


@login_required
@require_http_methods(["GET"])
def notification_list(request):
    notes = list(user_notifications(request.user, limit=100))
    return render(
        request,
        "notifications/list.html",
        {
            "notifications": notes,
            "unread": unread_count(request.user),
        },
    )


@login_required
@require_POST
def notification_send_test(request):
    """Staff/superuser helper: create a sample in-app notification for self."""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, _("Only staff can send test notifications."))
        return redirect("notifications:list")

    link = reverse("notifications:list")
    note = notify_user(
        user=request.user,
        type=Notification.Type.SYSTEM,
        title=_("Test notification"),
        body=_("This is a test in-app notification. You can dismiss or mark it read."),
        link=link,
        payload={"test": True},
    )
    if not note:
        # Preferences may suppress SYSTEM in-app; force-create for testing.
        Notification.objects.create(
            user=request.user,
            type=Notification.Type.SYSTEM,
            title=str(_("Test notification")),
            body=str(
                _("This is a test in-app notification. You can dismiss or mark it read.")
            ),
            link=link,
            payload={"test": True, "forced": True},
        )
    messages.success(request, _("Test notification created."))
    return redirect("notifications:list")


@login_required
@require_POST
def notification_mark_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    mark_read(note, request.user)
    if request.htmx:
        return render(
            request,
            "notifications/partials/item.html",
            {"n": note},
        )
    next_url = request.POST.get("next") or note.link or "notifications:list"
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("notifications:list")


@login_required
@require_POST
def notification_mark_all_read(request):
    mark_all_read(request.user)
    if request.htmx:
        return HttpResponse(status=204)
    return redirect("notifications:list")


@login_required
@require_http_methods(["GET"])
def notification_open(request, pk):
    """Mark read and follow link (or list)."""
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    mark_read(note, request.user)
    if note.link:
        return redirect(note.link)
    return redirect("notifications:list")


@login_required
@require_http_methods(["GET"])
def notification_badge(request):
    """HTMX fragment: unread badge for navbar."""
    count = unread_count(request.user)
    return render(
        request,
        "notifications/partials/badge.html",
        {"unread": count},
    )
