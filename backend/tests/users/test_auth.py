import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


def test_me_unauthenticated_returns_401(api_client):
    response = api_client.get("/api/auth/me/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_me_sets_csrf_cookie(api_client):
    api_client.get("/api/auth/me/")
    assert "csrftoken" in api_client.cookies


def test_login_with_valid_credentials(api_client, regular_user):
    regular_user.set_password("correct horse")
    regular_user.save()
    response = api_client.post(
        "/api/auth/login/",
        {"username": regular_user.username, "password": "correct horse"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["username"] == regular_user.username
    assert response.data["is_admin"] is False


def test_login_with_invalid_credentials(api_client, regular_user):
    response = api_client.post(
        "/api/auth/login/",
        {"username": regular_user.username, "password": "wrong"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_me_reflects_admin_status(admin_client, admin_user):
    response = admin_client.get("/api/auth/me/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_admin"] is True


def test_logout_clears_session(api_client, regular_user):
    regular_user.set_password("correct horse")
    regular_user.save()
    api_client.post(
        "/api/auth/login/",
        {"username": regular_user.username, "password": "correct horse"},
    )
    response = api_client.post("/api/auth/logout/")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    me_response = api_client.get("/api/auth/me/")
    assert me_response.status_code == status.HTTP_401_UNAUTHORIZED
