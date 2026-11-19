import json
from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="author")


@pytest.fixture
def assignee(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="assignee")


@pytest.fixture
def other_user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="other")


@pytest.fixture
def task(author: User, assignee: User) -> Task:
    return Task.objects.create(
        title="Original title",
        description="Original description",
        author=author,
        assignee=assignee,
    )


@pytest.fixture
def author_client(author: User) -> Client:
    client = Client()
    client.force_login(author)
    return client


@pytest.fixture
def assignee_client(assignee: User) -> Client:
    client = Client()
    client.force_login(assignee)
    return client


def test_author_can_patch_task(author_client: Client, task: Task, author: User) -> None:
    created_at = task.created_at
    updated_at = task.updated_at

    response = author_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {"title": "Renamed", "is_completed": True},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.title == "Renamed"
    assert task.is_completed
    assert task.description == "Original description"
    assert task.author == author
    assert task.created_at == created_at
    assert task.updated_at > updated_at
    assert response.json()["id"] == task.pk
    assert response.json()["title"] == task.title


def test_author_can_put_task(
    author_client: Client, task: Task, other_user: User
) -> None:
    response = author_client.put(
        reverse("api:task-detail", args=[task.pk]),
        {
            "title": "Replaced title",
            "description": "Replaced description",
            "assignee_id": other_user.pk,
            "is_completed": True,
        },
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.title == "Replaced title"
    assert task.description == "Replaced description"
    assert task.assignee == other_user
    assert task.is_completed


def test_put_preserves_omitted_optional_fields(
    author_client: Client, task: Task
) -> None:
    task.is_completed = True
    task.save()
    old_assignee = task.assignee

    response = author_client.put(
        reverse("api:task-detail", args=[task.pk]),
        {"title": "Renamed"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.description == "Original description"
    assert task.assignee == old_assignee
    assert task.is_completed


@pytest.mark.parametrize("target", ["self", "other", "none"])
def test_author_can_reassign_or_unassign_task(
    author_client: Client,
    assignee_client: Client,
    task: Task,
    author: User,
    other_user: User,
    target: str,
) -> None:
    new_assignee = {"self": author, "other": other_user, "none": None}[target]
    url = reverse("api:task-detail", args=[task.pk])

    response = author_client.patch(
        url,
        {"assignee_id": new_assignee.pk if new_assignee else None},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.assignee == new_assignee
    assert assignee_client.get(url).status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("is_completed", [True, False])
def test_assignee_can_complete_and_reopen_task(
    assignee_client: Client, task: Task, is_completed: bool
) -> None:
    task.is_completed = not is_completed
    task.save()

    response = assignee_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {"is_completed": is_completed},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.is_completed is is_completed
    assert task.title == "Original title"
    assert task.description == "Original description"


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "Forbidden"},
        {"description": "Forbidden"},
        {"assignee_id": None},
        {"author_id": 99999999},
        {"is_completed": True, "title": "Forbidden"},
        {"unknown_field": "Forbidden"},
    ],
)
def test_assignee_cannot_change_other_fields(
    assignee_client: Client, task: Task, payload: dict[str, object]
) -> None:
    before = Task.objects.values().get(pk=task.pk)

    response = assignee_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        payload,
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.values().get(pk=task.pk) == before


def test_assignee_cannot_use_put(assignee_client: Client, task: Task) -> None:
    before = Task.objects.values().get(pk=task.pk)

    response = assignee_client.put(
        reverse("api:task-detail", args=[task.pk]),
        {"title": "Original title", "is_completed": True},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.values().get(pk=task.pk) == before


def test_author_rights_take_precedence_when_self_assigned(
    author_client: Client, task: Task, author: User
) -> None:
    task.assignee = author
    task.save()

    response = author_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {"title": "Allowed", "is_completed": True},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.title == "Allowed"
    assert task.is_completed


def test_new_assignee_receives_write_access_and_former_assignee_loses_it(
    author_client: Client, assignee_client: Client, task: Task, other_user: User
) -> None:
    url = reverse("api:task-detail", args=[task.pk])
    response = author_client.patch(
        url, {"assignee_id": other_user.pk}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.OK

    response = assignee_client.patch(
        url, {"is_completed": True}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
    task.refresh_from_db()
    assert not task.is_completed

    new_client = Client()
    new_client.force_login(other_user)
    response = new_client.patch(
        url, {"is_completed": True}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.is_completed


def test_author_cannot_replace_server_owned_fields(
    author_client: Client, task: Task, author: User, other_user: User
) -> None:
    created_at = task.created_at
    task_id = task.pk

    response = author_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {
            "id": 99999999,
            "author_id": other_user.pk,
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
            "is_completed": True,
        },
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.pk == task_id
    assert task.author == author
    assert task.created_at == created_at
    assert task.updated_at.year > 2000
    assert task.is_completed


@pytest.mark.parametrize(
    ("method", "payload", "invalid_field"),
    [
        ("PUT", {}, "title"),
        ("PATCH", {"title": ""}, "title"),
        ("PATCH", {"title": "x" * 256}, "title"),
        ("PATCH", {"description": None}, "description"),
        ("PATCH", {"is_completed": "invalid"}, "is_completed"),
        ("PATCH", {"assignee_id": 99999999}, "assignee_id"),
    ],
)
def test_invalid_update_leaves_task_unchanged(
    author_client: Client,
    task: Task,
    method: str,
    payload: dict[str, object],
    invalid_field: str,
) -> None:
    before = Task.objects.values().get(pk=task.pk)

    response = author_client.generic(
        method,
        reverse("api:task-detail", args=[task.pk]),
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert invalid_field in response.json()
    assert Task.objects.values().get(pk=task.pk) == before


def test_invalid_assignment_does_not_partially_apply_other_changes(
    author_client: Client, task: Task, other_user: User
) -> None:
    other_user.is_active = False
    other_user.save()
    before = Task.objects.values().get(pk=task.pk)

    response = author_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {"title": "Changed", "assignee_id": other_user.pk, "is_completed": True},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "assignee_id" in response.json()
    assert Task.objects.values().get(pk=task.pk) == before


def test_existing_inactive_assignee_does_not_block_other_edits(
    author_client: Client, task: Task, assignee: User
) -> None:
    assignee.is_active = False
    assignee.save()

    response = author_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {"title": "Changed"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.title == "Changed"
    assert task.assignee == assignee


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize("role", ["outsider", "staff", "superuser"])
def test_outsiders_cannot_update_task_even_with_staff_privileges(
    client: Client, task: Task, other_user: User, method: str, role: str
) -> None:
    other_user.is_staff = role in {"staff", "superuser"}
    other_user.is_superuser = role == "superuser"
    other_user.save()
    client.force_login(other_user)
    before = Task.objects.values().get(pk=task.pk)

    response = client.generic(
        method,
        reverse("api:task-detail", args=[task.pk]),
        data=json.dumps({"title": "Forbidden"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert Task.objects.values().get(pk=task.pk) == before


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_anonymous_user_cannot_update_task(
    client: Client, task: Task, method: str
) -> None:
    before = Task.objects.values().get(pk=task.pk)

    response = client.generic(
        method,
        reverse("api:task-detail", args=[task.pk]),
        data=json.dumps({"title": "Forbidden"}),
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.values().get(pk=task.pk) == before


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_updates_require_csrf_token(author: User, task: Task, method: str) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(author)
    url = reverse("api:task-detail", args=[task.pk])
    body = json.dumps({"title": "Updated with CSRF"})
    before = Task.objects.values().get(pk=task.pk)

    response = client.generic(method, url, data=body, content_type="application/json")
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.values().get(pk=task.pk) == before
    token = client.get(reverse("api:csrf")).json()["csrf_token"]

    response = client.generic(
        method, url, data=body, content_type="application/json", HTTP_X_CSRFTOKEN=token
    )

    assert response.status_code == HTTPStatus.OK
    task.refresh_from_db()
    assert task.title == "Updated with CSRF"


def test_non_object_patch_cannot_bypass_assignee_permissions(
    assignee_client: Client, task: Task
) -> None:
    before = Task.objects.values().get(pk=task.pk)

    response = assignee_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        [{"is_completed": True}],
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.values().get(pk=task.pk) == before
