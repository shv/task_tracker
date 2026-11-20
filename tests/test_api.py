from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory

from tasks.models import Task


@pytest.mark.django_db
def test_session_requests_require_csrf_token(django_user_model: type[User]) -> None:
    client = Client(enforce_csrf_checks=True)
    user = django_user_model.objects.create_user(username="user")
    client.force_login(user)

    response = client.post(
        "/api/v1/tasks/", data={"title": "New task"}, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "CSRF" in response.json()["detail"]
    assert not Task.objects.exists()

    request = RequestFactory().get("/")
    token = get_token(request)
    client.cookies["csrftoken"] = request.META["CSRF_COOKIE"]

    response = client.post(
        "/api/v1/tasks/",
        data={"title": "New task"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert Task.objects.get().author == user
