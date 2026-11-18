from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


def test_anonymous_user_is_redirected_to_login(client: Client) -> None:
    response = client.get(reverse("admin:index"))

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == "/admin/login/?next=/admin/"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("is_staff", "expected_status"),
    [(False, HTTPStatus.FOUND), (True, HTTPStatus.OK)],
)
def test_admin_access_requires_staff_status(
    client: Client,
    django_user_model: type[User],
    is_staff: bool,
    expected_status: HTTPStatus,
) -> None:
    user = django_user_model.objects.create_user(username="user", is_staff=is_staff)
    client.force_login(user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == expected_status
    if not is_staff:
        assert response.headers["Location"] == "/admin/login/?next=/admin/"


@pytest.mark.django_db
@pytest.mark.parametrize("password_is_valid", [True, False])
def test_admin_login_authenticates_only_valid_credentials(
    client: Client,
    django_user_model: type[User],
    password_is_valid: bool,
) -> None:
    user = django_user_model.objects.create_user(
        username="staff", password="test-password", is_staff=True
    )

    response = client.post(
        reverse("admin:login"),
        {
            "username": user.username,
            "password": "test-password" if password_is_valid else "wrong-password",
            "next": reverse("admin:index"),
        },
    )

    if password_is_valid:
        assert response.status_code == HTTPStatus.FOUND
        assert response.headers["Location"] == reverse("admin:index")
        assert client.session["_auth_user_id"] == str(user.pk)
    else:
        assert response.status_code == HTTPStatus.OK
        assert "_auth_user_id" not in client.session
