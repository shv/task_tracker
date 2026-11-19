from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="viewer")


@pytest.fixture
def other_user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="other")


@pytest.fixture
def authenticated_client(client: Client, user: User) -> Client:
    client.force_login(user)
    return client


@pytest.mark.parametrize(
    "role", ["author", "assignee", "outsider", "staff", "superuser"]
)
def test_task_visibility_depends_only_on_authorship_or_assignment(
    client: Client, user: User, other_user: User, role: str
) -> None:
    if role in {"staff", "superuser"}:
        user.is_staff = True
        user.is_superuser = role == "superuser"
        user.save()
    task = Task.objects.create(
        title="Private task",
        author=user if role == "author" else other_user,
        assignee=user if role == "assignee" else None,
    )
    client.force_login(user)

    list_response = client.get(reverse("api:task-list"))
    detail_response = client.get(reverse("api:task-detail", args=[task.pk]))

    assert list_response.status_code == HTTPStatus.OK
    if role in {"author", "assignee"}:
        assert list_response.json()["count"] == 1
        assert [item["id"] for item in list_response.json()["results"]] == [task.pk]
        assert detail_response.status_code == HTTPStatus.OK
        assert detail_response.json()["id"] == task.pk
        assert detail_response.json()["title"] == task.title
    else:
        assert list_response.json()["count"] == 0
        assert list_response.json()["results"] == []
        assert detail_response.status_code == HTTPStatus.NOT_FOUND


def test_list_contains_both_authored_and_assigned_tasks_without_duplicates(
    authenticated_client: Client, user: User, other_user: User
) -> None:
    authored = Task.objects.create(title="Authored", author=user)
    assigned = Task.objects.create(title="Assigned", author=other_user, assignee=user)
    self_assigned = Task.objects.create(
        title="Self assigned", author=user, assignee=user
    )
    Task.objects.create(title="Hidden", author=other_user)

    response = authenticated_client.get(reverse("api:task-list"))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["count"] == 3
    assert [item["id"] for item in response.json()["results"]] == [
        self_assigned.pk,
        assigned.pk,
        authored.pk,
    ]


def test_empty_list_has_pagination_envelope(authenticated_client: Client) -> None:
    response = authenticated_client.get(reverse("api:task-list"))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }


def test_pagination_counts_only_visible_tasks_and_preserves_stable_order(
    authenticated_client: Client, user: User, other_user: User
) -> None:
    visible_tasks = Task.objects.bulk_create(
        [Task(title=f"Visible {number}", author=user) for number in range(21)]
    )
    Task.objects.bulk_create(
        [Task(title=f"Hidden {number}", author=other_user) for number in range(25)]
    )
    Task.objects.filter(author=user).update(created_at=timezone.now())
    expected_ids = [task.pk for task in reversed(visible_tasks)]
    url = reverse("api:task-list")

    first_page = authenticated_client.get(url).json()
    second_page = authenticated_client.get(url, {"page": 2}).json()

    assert first_page["count"] == second_page["count"] == 21
    assert len(first_page["results"]) == 20
    assert [item["id"] for item in first_page["results"]] == expected_ids[:20]
    assert first_page["previous"] is None
    assert first_page["next"] == f"http://testserver{url}?page=2"
    assert [item["id"] for item in second_page["results"]] == expected_ids[20:]
    assert second_page["next"] is None
    assert second_page["previous"] == f"http://testserver{url}"
    response = authenticated_client.get(url, {"page": 3})
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("page", ["0", "-1", "invalid", "1.5", "2"])
def test_invalid_or_missing_page_returns_404(
    authenticated_client: Client, user: User, page: str
) -> None:
    Task.objects.create(title="Only task", author=user)

    response = authenticated_client.get(reverse("api:task-list"), {"page": page})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_foreign_task_and_nonexistent_task_have_same_response(
    authenticated_client: Client, other_user: User
) -> None:
    task = Task.objects.create(title="Hidden", author=other_user)

    foreign_response = authenticated_client.get(
        reverse("api:task-detail", args=[task.pk])
    )
    missing_response = authenticated_client.get(
        reverse("api:task-detail", args=[99999999])
    )

    assert foreign_response.status_code == HTTPStatus.NOT_FOUND
    assert missing_response.status_code == HTTPStatus.NOT_FOUND
    assert foreign_response.json() == missing_response.json()


@pytest.mark.parametrize("remove_assignee", [False, True])
def test_former_assignee_loses_access_immediately(
    authenticated_client: Client, user: User, other_user: User, remove_assignee: bool
) -> None:
    task = Task.objects.create(title="Assigned", author=other_user, assignee=user)
    detail_url = reverse("api:task-detail", args=[task.pk])
    assert authenticated_client.get(detail_url).status_code == HTTPStatus.OK

    task.assignee = None if remove_assignee else other_user
    task.save()

    assert authenticated_client.get(detail_url).status_code == HTTPStatus.NOT_FOUND
    assert authenticated_client.get(reverse("api:task-list")).json()["count"] == 0
    author_client = Client()
    author_client.force_login(other_user)
    assert author_client.get(detail_url).status_code == HTTPStatus.OK


def test_query_parameters_cannot_expand_visibility(
    authenticated_client: Client, other_user: User
) -> None:
    Task.objects.create(title="Hidden", author=other_user)

    response = authenticated_client.get(
        reverse("api:task-list"),
        {"author_id": other_user.pk, "assignee_id": other_user.pk},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["count"] == 0
    assert response.json()["results"] == []


@pytest.mark.parametrize("detail", [False, True])
def test_anonymous_user_cannot_read_tasks(
    client: Client, user: User, detail: bool
) -> None:
    task = Task.objects.create(title="Hidden", author=user)
    url = (
        reverse("api:task-detail", args=[task.pk])
        if detail
        else reverse("api:task-list")
    )

    response = client.get(url)

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_inactive_user_cannot_read_tasks(
    authenticated_client: Client, user: User
) -> None:
    task = Task.objects.create(title="Hidden", author=user)
    user.is_active = False
    user.save()

    for url in [reverse("api:task-list"), reverse("api:task-detail", args=[task.pk])]:
        assert authenticated_client.get(url).status_code == HTTPStatus.FORBIDDEN


def test_reading_tasks_does_not_require_csrf_token(user: User) -> None:
    task = Task.objects.create(title="Readable", author=user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    assert client.get(reverse("api:task-list")).status_code == HTTPStatus.OK
    assert (
        client.get(reverse("api:task-detail", args=[task.pk])).status_code
        == HTTPStatus.OK
    )


def test_task_list_does_not_add_queries_per_task(
    authenticated_client: Client, user: User, other_user: User
) -> None:
    Task.objects.create(title="First", author=user, assignee=other_user)
    with CaptureQueriesContext(connection) as one_task_queries:
        first_response = authenticated_client.get(reverse("api:task-list"))
    Task.objects.bulk_create(
        [
            Task(title=f"Task {number}", author=user, assignee=other_user)
            for number in range(19)
        ]
    )
    with CaptureQueriesContext(connection) as many_tasks_queries:
        page_response = authenticated_client.get(reverse("api:task-list"))

    assert first_response.status_code == page_response.status_code == HTTPStatus.OK
    assert len(page_response.json()["results"]) == 20
    assert len(many_tasks_queries) == len(one_task_queries)


def test_browsable_api_displays_only_visible_tasks(
    authenticated_client: Client, user: User, other_user: User
) -> None:
    Task.objects.create(title="Visible task title", author=user)
    Task.objects.create(title="Private task title", author=other_user)

    response = authenticated_client.get(
        reverse("api:task-list"), HTTP_ACCEPT="text/html"
    )

    assert response.status_code == HTTPStatus.OK
    assert "Visible task title" in response.content.decode()
    assert "Private task title" not in response.content.decode()
