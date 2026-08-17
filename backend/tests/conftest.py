"""Fixtures reusable across the whole test suite.

Package-specific fixtures (e.g. metric types/entries) live in that package's
own `conftest.py` instead — keep fixtures as close as possible to the tests
that need them; only put something here once two or more test packages want it.
"""

import pytest
from django.contrib.auth.models import Group
from model_bakery import baker
from rest_framework.test import APIClient

from apps.core.permissions import ADMIN_ROLE


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_group(db):
    group, _ = Group.objects.get_or_create(name=ADMIN_ROLE)
    return group


@pytest.fixture
def regular_user(db):
    return baker.make("users.User")


@pytest.fixture
def admin_user(admin_group):
    """Deliberately overrides pytest-django's built-in `admin_user` fixture
    (which creates a superuser): ours is a member of the `admin` role group,
    matching how `PermissionService` actually grants admin access.
    """
    user = baker.make("users.User")
    user.groups.add(admin_group)
    return user


@pytest.fixture
def authenticated_client(api_client, regular_user):
    api_client.force_authenticate(regular_user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """Deliberately overrides pytest-django's built-in `admin_client` fixture
    for the same reason as `admin_user` above."""
    api_client.force_authenticate(admin_user)
    return api_client
