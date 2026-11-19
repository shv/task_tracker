from http import HTTPStatus

import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db
PASSWORD = " password with spaces "


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="alice", password=PASSWORD)


@pytest.fixture
def csrf_client() -> Client:
    client = Client(enforce_csrf_checks=True)
    response = client.get(reverse("api:csrf"))
    assert response.status_code == HTTPStatus.OK
    client.defaults["HTTP_X_CSRFTOKEN"] = response.json()["csrf_token"]
    return client


@pytest.fixture
def logged_in_client(csrf_client: Client, user: User) -> Client:
    response = csrf_client.post(
        reverse("api:login"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    response = csrf_client.get(reverse("api:csrf"))
    csrf_client.defaults["HTTP_X_CSRFTOKEN"] = response.json()["csrf_token"]
    return csrf_client


def test_csrf_endpoint_sets_cookie_and_prevents_caching(client: Client) -> None:
    response = client.get(reverse("api:csrf"))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["csrf_token"]
    assert settings.CSRF_COOKIE_NAME in response.cookies
    assert "Cookie" in response.headers["Vary"]
    assert "no-store" in response.headers["Cache-Control"]


def test_login_sets_session_and_current_user(csrf_client: Client, user: User) -> None:
    old_csrf_cookie = csrf_client.cookies[settings.CSRF_COOKIE_NAME].value

    response = csrf_client.post(
        reverse("api:login"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )

    expected_user = {"id": user.pk, "username": user.username}
    assert response.status_code == HTTPStatus.OK
    assert response.json() == expected_user
    assert csrf_client.session[SESSION_KEY] == str(user.pk)
    assert response.cookies[settings.SESSION_COOKIE_NAME]["httponly"]
    assert csrf_client.cookies[settings.CSRF_COOKIE_NAME].value != old_csrf_cookie
    response = csrf_client.get(reverse("api:current-user"))
    assert response.status_code == HTTPStatus.OK
    assert response.json() == expected_user
    assert "no-store" in response.headers["Cache-Control"]


@pytest.mark.parametrize(
    ("username", "password", "is_active"),
    [
        ("alice", "wrong-password", True),
        ("unknown-user", PASSWORD, True),
        ("alice", PASSWORD, False),
    ],
)
def test_login_rejects_invalid_credentials_without_disclosing_account_status(
    csrf_client: Client,
    user: User,
    username: str,
    password: str,
    is_active: bool,
) -> None:
    user.is_active = is_active
    user.save()

    response = csrf_client.post(
        reverse("api:login"),
        {"username": username, "password": password},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {"detail": "Invalid username or password."}
    assert SESSION_KEY not in csrf_client.session


@pytest.mark.parametrize(
    ("payload", "invalid_field"),
    [
        ({"password": PASSWORD}, "username"),
        ({"username": "alice"}, "password"),
        ({"username": "alice", "password": ""}, "password"),
        ({"username": "a" * 151, "password": PASSWORD}, "username"),
    ],
)
def test_login_validates_request_fields(
    csrf_client: Client, payload: dict[str, str], invalid_field: str
) -> None:
    response = csrf_client.post(
        reverse("api:login"), payload, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert invalid_field in response.json()
    assert SESSION_KEY not in csrf_client.session


@pytest.mark.parametrize("with_cookie", [False, True])
def test_anonymous_login_requires_csrf_header(user: User, with_cookie: bool) -> None:
    client = Client(enforce_csrf_checks=True)
    if with_cookie:
        client.get(reverse("api:csrf"))

    response = client.post(
        reverse("api:login"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "CSRF" in response.json()["detail"]
    assert SESSION_KEY not in client.session


@pytest.mark.parametrize(
    "headers",
    [
        {"X-CSRFToken": "a" * 64},
        {"Origin": "https://untrusted.example"},
    ],
)
def test_login_rejects_invalid_csrf_or_untrusted_origin(
    csrf_client: Client, user: User, headers: dict[str, str]
) -> None:
    response = csrf_client.post(
        reverse("api:login"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "CSRF" in response.json()["detail"]
    assert SESSION_KEY not in csrf_client.session


def test_login_rotates_anonymous_session_key(csrf_client: Client, user: User) -> None:
    session = csrf_client.session
    session["draft"] = "anonymous data"
    session.save()
    old_session_key = session.session_key

    response = csrf_client.post(
        reverse("api:login"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert csrf_client.session.session_key != old_session_key
    assert csrf_client.session["draft"] == "anonymous data"
    assert not Session.objects.filter(session_key=old_session_key).exists()


def test_logout_invalidates_session_and_prevents_replay(
    logged_in_client: Client,
) -> None:
    session_key = logged_in_client.cookies[settings.SESSION_COOKIE_NAME].value

    response = logged_in_client.generic("POST", reverse("api:logout"))

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""
    assert not Session.objects.filter(session_key=session_key).exists()
    assert (
        logged_in_client.get(reverse("api:current-user")).status_code
        == HTTPStatus.FORBIDDEN
    )
    other_client = Client()
    other_client.cookies[settings.SESSION_COOKIE_NAME] = session_key
    assert (
        other_client.get(reverse("api:current-user")).status_code
        == HTTPStatus.FORBIDDEN
    )


def test_logout_requires_csrf_token(logged_in_client: Client) -> None:
    response = logged_in_client.generic(
        "POST", reverse("api:logout"), HTTP_X_CSRFTOKEN=""
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "CSRF" in response.json()["detail"]
    assert (
        logged_in_client.get(reverse("api:current-user")).status_code == HTTPStatus.OK
    )


def test_pre_login_csrf_token_cannot_be_used_after_login(
    csrf_client: Client, user: User
) -> None:
    response = csrf_client.post(
        reverse("api:login"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    response = csrf_client.generic("POST", reverse("api:logout"))

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert csrf_client.get(reverse("api:current-user")).status_code == HTTPStatus.OK


def test_logout_is_not_available_via_get(logged_in_client: Client) -> None:
    response = logged_in_client.get(reverse("api:logout"))

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert (
        logged_in_client.get(reverse("api:current-user")).status_code == HTTPStatus.OK
    )


@pytest.mark.parametrize(
    ("method", "view_name"),
    [("GET", "api:current-user"), ("POST", "api:logout")],
)
def test_protected_auth_views_require_login(
    client: Client, method: str, view_name: str
) -> None:
    response = client.generic(method, reverse(view_name))

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize("change", ["deactivate", "change_password"])
def test_account_changes_revoke_session(
    logged_in_client: Client, user: User, change: str
) -> None:
    if change == "deactivate":
        user.is_active = False
    else:
        user.set_password("new-password")
    user.save()

    response = logged_in_client.get(reverse("api:current-user"))

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_browsable_api_login_works_for_non_staff_user(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    response = client.get(reverse("rest_framework:login"))
    assert response.status_code == HTTPStatus.OK
    assert not user.is_staff

    response = client.post(
        reverse("rest_framework:login"),
        {
            "username": user.username,
            "password": PASSWORD,
            "csrfmiddlewaretoken": client.cookies[settings.CSRF_COOKIE_NAME].value,
            "next": reverse("api:current-user"),
        },
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == reverse("api:current-user")
    assert client.session[SESSION_KEY] == str(user.pk)
    assert client.get(reverse("api:current-user")).json() == {
        "id": user.pk,
        "username": user.username,
    }
