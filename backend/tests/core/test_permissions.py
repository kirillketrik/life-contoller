import pytest
from model_bakery import baker

from apps.core.permissions import Action, PermissionService, Resource


def test_anonymous_user_has_no_roles():
    assert PermissionService.roles_for(None) == set()


def test_plain_user_is_not_admin(regular_user):
    assert not PermissionService.is_admin(regular_user)
    assert not PermissionService.can(regular_user, Action.CREATE, Resource.METRIC_TYPE)


def test_group_membership_grants_admin_role(admin_user):
    assert PermissionService.is_admin(admin_user)
    assert PermissionService.can(admin_user, Action.CREATE, Resource.METRIC_TYPE)
    assert PermissionService.can(admin_user, Action.DELETE, Resource.FORMULA_DEFINITION)


@pytest.mark.django_db
def test_superuser_is_admin_without_group():
    superuser = baker.make("users.User", is_superuser=True)
    assert PermissionService.is_admin(superuser)
