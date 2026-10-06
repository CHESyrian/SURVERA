"""Company team management and create-company."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.decorators import email_verified_required

from .models import Company, CompanyMembership
from .services import (
    add_company_member,
    change_member_role,
    create_company_with_owner,
    roles_assignable_by,
    user_can_manage_team,
)


@login_required
def company_list(request):
    memberships = (
        CompanyMembership.objects.filter(user=request.user, is_active=True)
        .select_related("company")
        .order_by("company__name")
    )
    return render(request, "companies/list.html", {"memberships": memberships})


@email_verified_required
@require_http_methods(["GET", "POST"])
def company_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, _("Company name is required."))
        else:
            company = create_company_with_owner(
                owner=request.user,
                name=name,
                promote_user_type=False,
            )
            messages.success(
                request,
                _("Company “%(name)s” created. You are the owner.") % {"name": company.name},
            )
            return redirect("companies:team", pk=company.pk)
    return render(request, "companies/create.html")


@login_required
def company_team(request, pk):
    company = get_object_or_404(Company, pk=pk, is_deleted=False)
    membership = CompanyMembership.objects.filter(
        company=company, user=request.user, is_active=True
    ).first()
    if not membership:
        raise PermissionDenied

    members = (
        CompanyMembership.objects.filter(company=company, is_active=True)
        .select_related("user")
        .order_by("role", "user__email")
    )
    assignable = roles_assignable_by(request.user, company)
    return render(
        request,
        "companies/team.html",
        {
            "company": company,
            "members": members,
            "can_manage": membership.can_manage_team,
            "my_membership": membership,
            "assignable_roles": assignable,
        },
    )


@login_required
@require_POST
def company_member_add(request, pk):
    company = get_object_or_404(Company, pk=pk, is_deleted=False)
    if not user_can_manage_team(request.user, company):
        raise PermissionDenied
    email = (request.POST.get("email") or "").strip()
    role = request.POST.get("role") or CompanyMembership.Role.PARTICIPANT
    try:
        add_company_member(company=company, email=email, role=role, invited_by=request.user)
        messages.success(request, _("Member added."))
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("companies:team", pk=company.pk)


@login_required
@require_POST
def company_member_role(request, pk, membership_id):
    company = get_object_or_404(Company, pk=pk, is_deleted=False)
    if not user_can_manage_team(request.user, company):
        raise PermissionDenied
    membership = get_object_or_404(CompanyMembership, pk=membership_id, company=company)
    role = request.POST.get("role") or membership.role
    try:
        change_member_role(
            company=company,
            membership=membership,
            new_role=role,
            changed_by=request.user,
        )
        messages.success(request, _("Role updated."))
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("companies:team", pk=company.pk)


@login_required
@require_POST
def company_member_remove(request, pk, membership_id):
    company = get_object_or_404(Company, pk=pk, is_deleted=False)
    if not user_can_manage_team(request.user, company):
        raise PermissionDenied
    membership = get_object_or_404(CompanyMembership, pk=membership_id, company=company)
    if membership.role == CompanyMembership.Role.OWNER:
        messages.error(request, _("Cannot remove the owner."))
        return redirect("companies:team", pk=company.pk)
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])
    messages.success(request, _("Member removed."))
    return redirect("companies:team", pk=company.pk)
