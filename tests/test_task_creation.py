from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils.dateparse import parse_datetime

from tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="author")


@pytest.fixture
def assignee(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="assignee")


@pytest.fixture
def authenticated_client(client: Client, user: User) -> Client:
    client.force_login(user)
    return client


def test_create_task_with_defaults(authenticated_client: Client, user: User) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "Prepare release"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.title == "Prepare release"
    assert task.description == ""
    assert task.author == user
    assert task.assignee is None
    assert not task.is_completed
    data = response.json()
    assert data == {
        "id": task.pk,
        "title": task.title,
        "description": "",
        "author_id": user.pk,
        "assignee_id": None,
        "is_completed": False,
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
    }
    assert parse_datetime(data["created_at"]) == task.created_at
    assert parse_datetime(data["updated_at"]) == task.updated_at


def test_create_task_with_assignee_and_completion(
    authenticated_client: Client, user: User, assignee: User
) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"),
        {
            "title": "  Подготовить релиз  ",
            "description": "Publish the new version",
            "assignee_id": assignee.pk,
            "is_completed": True,
        },
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.title == "Подготовить релиз"
    assert task.description == "Publish the new version"
    assert task.author == user
    assert task.assignee == assignee
    assert task.is_completed
    assert response.json()["assignee_id"] == assignee.pk


def test_create_task_assigned_to_self(authenticated_client: Client, user: User) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "My task", "assignee_id": user.pk},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.author == task.assignee == user


def test_create_task_with_explicitly_empty_assignee(
    authenticated_client: Client,
) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "Unassigned", "assignee_id": None},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    assert Task.objects.get().assignee is None


def test_server_owned_fields_cannot_be_overridden(
    authenticated_client: Client, user: User, assignee: User
) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"),
        {
            "title": "New task",
            "id": 999999,
            "author_id": assignee.pk,
            "author": assignee.pk,
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        },
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.author == user
    assert task.pk != 999999
    assert response.json()["author_id"] == user.pk
    assert task.created_at.year > 2000
    assert task.updated_at.year > 2000


@pytest.mark.parametrize(
    ("payload", "invalid_field"),
    [
        ({}, "title"),
        ({"title": ""}, "title"),
        ({"title": "   "}, "title"),
        ({"title": None}, "title"),
        ({"title": "x" * 256}, "title"),
        ({"title": "Task", "description": None}, "description"),
        ({"title": "Task", "is_completed": "unknown"}, "is_completed"),
        ({"title": "Task", "is_completed": None}, "is_completed"),
    ],
)
def test_invalid_task_data_does_not_create_task(
    authenticated_client: Client, payload: dict[str, object], invalid_field: str
) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"), payload, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert invalid_field in response.json()
    assert not Task.objects.exists()


@pytest.mark.parametrize("assignee_id", [0, -1, 99999999, "invalid", True, 1.5, {}])
def test_invalid_assignee_does_not_create_task(
    authenticated_client: Client, assignee_id: object
) -> None:
    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "New task", "assignee_id": assignee_id},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "assignee_id" in response.json()
    assert not Task.objects.exists()


def test_inactive_assignee_cannot_be_assigned(
    authenticated_client: Client, assignee: User
) -> None:
    assignee.is_active = False
    assignee.save()

    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "New task", "assignee_id": assignee.pk},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "assignee_id" in response.json()
    assert not Task.objects.exists()


def test_anonymous_user_cannot_create_task(client: Client) -> None:
    response = client.post(
        reverse("api:task-list"),
        {"title": "New task"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert not Task.objects.exists()


def test_inactive_user_cannot_create_task(
    authenticated_client: Client, user: User
) -> None:
    user.is_active = False
    user.save()

    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "New task"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert not Task.objects.exists()


def test_session_login_followed_by_task_creation(user: User) -> None:
    password = "test-password"
    user.set_password(password)
    user.save()
    client = Client(enforce_csrf_checks=True)
    token = client.get(reverse("api:csrf")).json()["csrf_token"]
    response = client.post(
        reverse("api:login"),
        {"username": user.username, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == HTTPStatus.OK
    token = client.get(reverse("api:csrf")).json()["csrf_token"]

    response = client.post(
        reverse("api:task-list"),
        {"title": "Task created through a real session"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.author == user
    assert response.json()["id"] == task.pk
