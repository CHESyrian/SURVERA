"""Tests for company roles, manage permissions, and membership re-invite."""
import pytest
from django.core.exceptions import PermissionDenied

from apps.companies.models import CompanyMembership
from apps.companies.services import (
    add_company_member,
    create_company_with_owner,
    get_active_membership,
    user_can_manage_surveys,
    user_can_manage_team,
    user_is_company_member,
)
from apps.factories import CompanyFactory, CompanyMembershipFactory, UserFactory


@pytest.mark.django_db
class TestMembershipRoleFlags:
    def test_owner_can_manage_surveys_and_team(self, owner_membership):
        assert owner_membership.can_manage_surveys is True
        assert owner_membership.can_manage_team is True
        assert owner_membership.is_owner is True
        assert owner_membership.is_admin_or_owner is True

    def test_moderator_can_manage_surveys_and_team(self, moderator_membership):
        assert moderator_membership.can_manage_surveys is True
        assert moderator_membership.can_manage_team is True
        assert moderator_membership.is_owner is False

    def test_legacy_admin_can_manage_surveys_and_team(self, company, db):
        user = UserFactory()
        m = CompanyMembershipFactory(
            company=company, user=user, role=CompanyMembership.Role.ADMIN, is_active=True
        )
        assert m.can_manage_surveys is True
        assert m.can_manage_team is True
        assert m.is_admin_or_owner is True

    def test_participant_cannot_manage(self, participant_membership):
        assert participant_membership.can_manage_surveys is False
        assert participant_membership.can_manage_team is False
        assert participant_membership.is_owner is False

    def test_viewer_cannot_manage(self, company, db):
        user = UserFactory()
        m = CompanyMembershipFactory(
            company=company, user=user, role=CompanyMembership.Role.VIEWER, is_active=True
        )
        assert m.can_manage_surveys is False
        assert m.can_manage_team is False

    def test_analyst_cannot_manage_surveys(self, company, db):
        user = UserFactory()
        m = CompanyMembershipFactory(
            company=company, user=user, role=CompanyMembership.Role.ANALYST, is_active=True
        )
        assert m.can_manage_surveys is False
        assert m.can_manage_team is False


@pytest.mark.django_db
class TestUserCanManageHelpers:
    def test_owner_can_manage_surveys(self, owner, company, owner_membership):
        assert user_can_manage_surveys(owner, company) is True
        assert user_can_manage_team(owner, company) is True
        assert user_is_company_member(owner, company) is True

    def test_participant_cannot_manage_surveys(self, participant, company, participant_membership):
        assert user_can_manage_surveys(participant, company) is False
        assert user_can_manage_team(participant, company) is False
        assert user_is_company_member(participant, company) is True

    def test_non_member_cannot_manage(self, company, db):
        stranger = UserFactory()
        assert user_can_manage_surveys(stranger, company) is False
        assert user_can_manage_team(stranger, company) is False
        assert user_is_company_member(stranger, company) is False

    def test_inactive_membership_does_not_grant_access(self, company, db):
        user = UserFactory()
        CompanyMembershipFactory(
            company=company,
            user=user,
            role=CompanyMembership.Role.OWNER,
            is_active=False,
        )
        assert user_can_manage_surveys(user, company) is False
        assert get_active_membership(user, company) is None


@pytest.mark.django_db
class TestCreateCompanyWithOwner:
    def test_creates_owner_membership(self, db):
        user = UserFactory(user_type="person")
        company = create_company_with_owner(owner=user, name="Acme Corp")
        assert company.name == "Acme Corp"
        m = CompanyMembership.objects.get(company=company, user=user)
        assert m.role == CompanyMembership.Role.OWNER
        assert m.is_active is True
        user.refresh_from_db()
        assert user.user_type == user.UserType.COMPANY_MEMBER


@pytest.mark.django_db
class TestAddCompanyMemberReInvite:
    def test_add_new_member(self, company, owner, owner_membership, db):
        from apps.notifications.models import Notification

        invitee = UserFactory(email="invitee@example.com")
        m = add_company_member(
            company=company,
            email="invitee@example.com",
            role=CompanyMembership.Role.PARTICIPANT,
            invited_by=owner,
        )
        assert m.is_active is True
        assert m.role == CompanyMembership.Role.PARTICIPANT
        assert m.user_id == invitee.pk
        note = Notification.objects.filter(
            user=invitee, type=Notification.Type.TEAM_INVITE
        ).first()
        assert note is not None
        assert note.read_at is None
        assert note.payload.get("company_id") == company.pk
        assert note.payload.get("reactivated") is False
        assert str(company.pk) in note.link or note.link.endswith(f"/team/")

    def test_cannot_add_duplicate_active_member(self, company, owner, owner_membership, participant, participant_membership):
        with pytest.raises(ValueError, match="already a member"):
            add_company_member(
                company=company,
                email=participant.email,
                role=CompanyMembership.Role.PARTICIPANT,
                invited_by=owner,
            )

    def test_reinvite_reactivates_soft_removed_member(
        self, company, owner, owner_membership, participant, participant_membership
    ):
        # Soft-remove
        participant_membership.is_active = False
        participant_membership.save(update_fields=["is_active"])
        assert get_active_membership(participant, company) is None

        from apps.notifications.models import Notification

        # Re-invite reactivates the same row
        m = add_company_member(
            company=company,
            email=participant.email,
            role=CompanyMembership.Role.MODERATOR,
            invited_by=owner,
        )
        assert m.pk == participant_membership.pk
        assert m.is_active is True
        assert m.role == CompanyMembership.Role.MODERATOR
        assert get_active_membership(participant, company) is not None
        note = Notification.objects.filter(
            user=participant, type=Notification.Type.TEAM_INVITE
        ).order_by("-id").first()
        assert note is not None
        assert note.payload.get("reactivated") is True
        assert note.payload.get("role") == CompanyMembership.Role.MODERATOR

    def test_cannot_assign_owner_via_invite(self, company, owner, owner_membership, db):
        invitee = UserFactory()
        with pytest.raises(ValueError, match="owner"):
            add_company_member(
                company=company,
                email=invitee.email,
                role=CompanyMembership.Role.OWNER,
                invited_by=owner,
            )

    def test_legacy_admin_role_normalized_to_moderator(self, company, owner, owner_membership, db):
        invitee = UserFactory()
        m = add_company_member(
            company=company,
            email=invitee.email,
            role=CompanyMembership.Role.ADMIN,
            invited_by=owner,
        )
        assert m.role == CompanyMembership.Role.MODERATOR

    def test_unknown_email_raises(self, company, owner, owner_membership):
        with pytest.raises(ValueError, match="No user"):
            add_company_member(
                company=company,
                email="nobody@example.com",
                role=CompanyMembership.Role.PARTICIPANT,
                invited_by=owner,
            )


@pytest.mark.django_db
class TestAssignableRoleScope:
    def test_owner_can_assign_moderator_and_participant(self, owner_membership):
        roles = owner_membership.roles_assignable_by_self()
        assert CompanyMembership.Role.MODERATOR in roles
        assert CompanyMembership.Role.PARTICIPANT in roles
        assert CompanyMembership.Role.OWNER not in roles

    def test_moderator_can_only_assign_participant(self, moderator_membership):
        roles = moderator_membership.roles_assignable_by_self()
        assert roles == [CompanyMembership.Role.PARTICIPANT]

    def test_participant_assigns_nothing(self, participant_membership):
        assert participant_membership.roles_assignable_by_self() == []

    def test_moderator_cannot_invite_moderator(
        self, company, owner, owner_membership, moderator, moderator_membership, db
    ):
        invitee = UserFactory()
        with pytest.raises(ValueError, match="cannot assign"):
            add_company_member(
                company=company,
                email=invitee.email,
                role=CompanyMembership.Role.MODERATOR,
                invited_by=moderator,
            )

    def test_moderator_can_invite_participant(
        self, company, moderator, moderator_membership, db
    ):
        invitee = UserFactory()
        m = add_company_member(
            company=company,
            email=invitee.email,
            role=CompanyMembership.Role.PARTICIPANT,
            invited_by=moderator,
        )
        assert m.role == CompanyMembership.Role.PARTICIPANT
