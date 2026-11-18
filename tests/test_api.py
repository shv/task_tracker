from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory

PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/tasks/"),
    ("POST", "/api/v1/tasks/"),
    ("GET", "/api/v1/tasks/1/"),
    ("PUT", "/api/v1/tasks/1/"),
    ("PATCH", "/api/v1/tasks/1/"),
    ("DELETE", "/api/v1/tasks/1/"),
    ("GET", "/api/v1/tasks/1/comments/"),
    ("POST", "/api/v1/tasks/1/comments/"),
    ("GET", "/api/v1/users/"),
    ("POST", "/api/v1/auth/logout/"),
    ("GET", "/api/v1/auth/me/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "url"), PROTECTED_ENDPOINTS)
@pytest.mark.parametrize("authenticated", [False, True])
def test_protected_stubs_require_authentication(
    client: Client,
    django_user_model: type[User],
    method: str,
    url: str,
    authenticated: bool,
) -> None:
    if authenticated:
        user = django_user_model.objects.create_user(username="user")
        client.force_login(user)

    response = client.generic(method, url, data="{}", content_type="application/json")

    expected_status = (
        HTTPStatus.NOT_IMPLEMENTED if authenticated else HTTPStatus.FORBIDDEN
    )
    assert response.status_code == expected_status
    assert response.headers["Content-Type"] == "application/json"
    assert set(response.json()) == {"detail"}
    if authenticated:
        assert response.json()["detail"] == "This endpoint is not implemented yet."


@pytest.mark.parametrize(
    ("method", "url"),
    [("GET", "/api/v1/auth/csrf/"), ("POST", "/api/v1/auth/login/")],
)
def test_public_auth_stubs_are_accessible_without_login(
    client: Client, method: str, url: str
) -> None:
    response = client.generic(method, url, data="{}", content_type="application/json")

    assert response.status_code == HTTPStatus.NOT_IMPLEMENTED
    assert response.json() == {"detail": "This endpoint is not implemented yet."}


@pytest.mark.django_db
def test_session_requests_require_csrf_token(django_user_model: type[User]) -> None:
    client = Client(enforce_csrf_checks=True)
    user = django_user_model.objects.create_user(username="user")
    client.force_login(user)

    response = client.post("/api/v1/tasks/", data={}, content_type="application/json")

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "CSRF" in response.json()["detail"]

    request = RequestFactory().get("/")
    token = get_token(request)
    client.cookies["csrftoken"] = request.META["CSRF_COOKIE"]

    response = client.post(
        "/api/v1/tasks/",
        data={},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == HTTPStatus.NOT_IMPLEMENTED
