from datetime import timedelta
from http import HTTPStatus

import jwt
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from tasks.models import Comment, Task

pytestmark = pytest.mark.django_db
PASSWORD = " password with spaces "


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="jwt-user", password=PASSWORD)


@pytest.fixture
def pair(user: User) -> dict[str, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        reverse("api:token-pair"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK
    data: dict[str, str] = response.json()
    return data


@pytest.fixture
def bearer_client(pair: dict[str, str]) -> Client:
    return Client(
        enforce_csrf_checks=True, HTTP_AUTHORIZATION=f"Bearer {pair['access']}"
    )


def test_token_pair_does_not_set_session_or_csrf_cookies(user: User) -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        reverse("api:token-pair"),
        {"username": user.username, "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert set(response.json()) == {"access", "refresh"}
    assert "sessionid" not in response.cookies
    assert "csrftoken" not in response.cookies
    assert "no-store" in response.headers["Cache-Control"]
    access = AccessToken(response.json()["access"])
    refresh = RefreshToken(response.json()["refresh"])
    assert str(access["user_id"]) == str(refresh["user_id"]) == str(user.pk)
    assert int(access["exp"]) - int(access["iat"]) == 300
    assert int(refresh["exp"]) - int(refresh["iat"]) == 86400


@pytest.mark.parametrize(
    ("username", "password", "active"),
    [
        ("jwt-user", "wrong", True),
        ("unknown", PASSWORD, True),
        ("jwt-user", PASSWORD, False),
    ],
)
def test_bad_credentials_and_inactive_account_are_rejected(
    client: Client, user: User, username: str, password: str, active: bool
) -> None:
    user.is_active = active
    user.save()

    response = client.post(
        reverse("api:token-pair"),
        {"username": username, "password": password},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_missing_credentials_return_400(client: Client) -> None:
    response = client.post(
        reverse("api:token-pair"), {}, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert set(response.json()) == {"username", "password"}


def test_jwt_allows_task_and_comment_workflow_without_csrf(
    bearer_client: Client, user: User
) -> None:
    me = bearer_client.get(reverse("api:current-user"))
    assert me.status_code == HTTPStatus.OK
    assert me.json() == {"id": user.pk, "username": user.username}
    assert bearer_client.get(reverse("api:user-list")).status_code == HTTPStatus.OK

    response = bearer_client.post(
        reverse("api:task-list"), {"title": "JWT task"}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.author == user
    detail_url = reverse("api:task-detail", args=[task.pk])
    assert bearer_client.get(detail_url).status_code == HTTPStatus.OK
    response = bearer_client.patch(
        detail_url, {"is_completed": True}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.OK

    comments_url = reverse("api:comment-list", args=[task.pk])
    response = bearer_client.post(
        comments_url, {"text": "JWT comment"}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.CREATED
    assert Comment.objects.get().author == user
    assert bearer_client.get(comments_url).json()["count"] == 1
    response = bearer_client.delete(detail_url)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not Task.objects.exists()
    assert not Comment.objects.exists()


def test_jwt_preserves_task_permissions(
    bearer_client: Client, user: User, django_user_model: type[User]
) -> None:
    author = django_user_model.objects.create_user(username="other")
    task = Task.objects.create(title="Assigned", author=author, assignee=user)
    url = reverse("api:task-detail", args=[task.pk])

    assert bearer_client.get(url).status_code == HTTPStatus.OK
    assert (
        bearer_client.patch(
            url, {"is_completed": True}, content_type="application/json"
        ).status_code
        == HTTPStatus.OK
    )
    assert (
        bearer_client.patch(
            url, {"title": "Forbidden"}, content_type="application/json"
        ).status_code
        == HTTPStatus.FORBIDDEN
    )
    assert bearer_client.delete(url).status_code == HTTPStatus.FORBIDDEN
    task.assignee = None
    task.save()
    assert bearer_client.get(url).status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("kind", ["expired", "wrong_signature", "refresh", "malformed"])
def test_invalid_bearer_tokens_are_rejected(user: User, kind: str) -> None:
    token = AccessToken.for_user(user)
    if kind == "expired":
        token.set_exp(lifetime=timedelta(seconds=-1))
        encoded = str(token)
    elif kind == "wrong_signature":
        encoded = jwt.encode(
            token.payload,
            "a-different-signing-key-with-at-least-32-bytes",
            algorithm="HS256",
        )
    elif kind == "refresh":
        encoded = str(RefreshToken.for_user(user))
    else:
        encoded = "not-a-jwt"
    client = Client(HTTP_AUTHORIZATION=f"Bearer {encoded}")

    response = client.get(reverse("api:current-user"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_invalid_jwt_does_not_fall_back_to_authenticated_session(user: User) -> None:
    client = Client(HTTP_AUTHORIZATION="Bearer invalid")
    client.force_login(user)

    response = client.get(reverse("api:current-user"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_refresh_rotates_token_and_rejects_replay(
    client: Client, pair: dict[str, str]
) -> None:
    url = reverse("api:token-refresh")
    response = client.post(
        url, {"refresh": pair["refresh"]}, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.OK
    new_pair = response.json()
    assert set(new_pair) == {"access", "refresh"}
    assert new_pair["refresh"] != pair["refresh"]
    assert "no-store" in response.headers["Cache-Control"]
    assert (
        client.post(
            url, {"refresh": pair["refresh"]}, content_type="application/json"
        ).status_code
        == HTTPStatus.UNAUTHORIZED
    )
    access_client = Client(HTTP_AUTHORIZATION=f"Bearer {new_pair['access']}")
    assert access_client.get(reverse("api:current-user")).status_code == HTTPStatus.OK


def test_blacklist_revokes_refresh_but_access_expires_normally(
    client: Client, pair: dict[str, str]
) -> None:
    response = client.post(
        reverse("api:token-blacklist"),
        {"refresh": pair["refresh"]},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {}
    assert "no-store" in response.headers["Cache-Control"]
    response = client.post(
        reverse("api:token-refresh"),
        {"refresh": pair["refresh"]},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    access_client = Client(HTTP_AUTHORIZATION=f"Bearer {pair['access']}")
    assert access_client.get(reverse("api:current-user")).status_code == HTTPStatus.OK


@pytest.mark.parametrize("view_name", ["api:token-refresh", "api:token-blacklist"])
@pytest.mark.parametrize("token_kind", ["missing", "malformed", "expired", "access"])
def test_refresh_endpoints_reject_invalid_tokens(
    client: Client, user: User, view_name: str, token_kind: str
) -> None:
    if token_kind == "missing":
        payload = {}
    elif token_kind == "malformed":
        payload = {"refresh": "invalid"}
    elif token_kind == "access":
        payload = {"refresh": str(AccessToken.for_user(user))}
    else:
        token = RefreshToken.for_user(user)
        token.set_exp(lifetime=timedelta(seconds=-1))
        payload = {"refresh": str(token)}

    response = client.post(reverse(view_name), payload, content_type="application/json")

    expected = (
        HTTPStatus.BAD_REQUEST if token_kind == "missing" else HTTPStatus.UNAUTHORIZED
    )
    assert response.status_code == expected


@pytest.mark.parametrize("account_change", ["deactivate", "delete"])
def test_account_changes_block_access_and_refresh(
    client: Client,
    bearer_client: Client,
    pair: dict[str, str],
    user: User,
    account_change: str,
) -> None:
    if account_change == "deactivate":
        user.is_active = False
        user.save()
    else:
        user.delete()

    assert (
        bearer_client.get(reverse("api:current-user")).status_code
        == HTTPStatus.UNAUTHORIZED
    )
    response = client.post(
        reverse("api:token-refresh"),
        {"refresh": pair["refresh"]},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
