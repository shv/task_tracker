from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from tasks.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="viewer")


@pytest.fixture
def authenticated_client(client: Client, user: User) -> Client:
    client.force_login(user)
    return client


def test_active_users_are_visible_with_only_public_fields(
    authenticated_client: Client, user: User, django_user_model: type[User]
) -> None:
    alice = django_user_model.objects.create_user(
        username="alice", email="private@example.test", first_name="Private first name"
    )
    staff = django_user_model.objects.create_user(
        username="staff", is_staff=True, is_superuser=True
    )
    django_user_model.objects.create_user(username="hidden", is_active=False)
    django_user_model.objects.create_user(
        username="hidden-admin", is_active=False, is_staff=True, is_superuser=True
    )

    response = authenticated_client.get(reverse("api:user-list"))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "count": 3,
        "next": None,
        "previous": None,
        "results": [
            {"id": alice.pk, "username": "alice"},
            {"id": staff.pk, "username": "staff"},
            {"id": user.pk, "username": "viewer"},
        ],
    }
    assert "private@example.test" not in response.content.decode()
    assert "Private first name" not in response.content.decode()


def test_user_pagination_counts_only_active_accounts(
    authenticated_client: Client, user: User, django_user_model: type[User]
) -> None:
    active_users = [
        django_user_model.objects.create_user(username=f"user-{number:03}")
        for number in range(25)
    ]
    for number in range(25):
        django_user_model.objects.create_user(
            username=f"hidden-{number:03}", is_active=False
        )
    url = reverse("api:user-list")

    first_page = authenticated_client.get(url).json()
    second_page = authenticated_client.get(url, {"page": 2}).json()

    assert first_page["count"] == second_page["count"] == 26
    assert [item["id"] for item in first_page["results"]] == [
        account.pk for account in active_users[:20]
    ]
    assert [item["id"] for item in second_page["results"]] == [
        *[account.pk for account in active_users[20:]],
        user.pk,
    ]
    assert first_page["next"] == f"http://testserver{url}?page=2"
    assert first_page["previous"] is None
    assert second_page["previous"] == f"http://testserver{url}"
    assert second_page["next"] is None
    assert (
        authenticated_client.get(url, {"page": 3}).status_code == HTTPStatus.NOT_FOUND
    )


@pytest.mark.parametrize("page", ["0", "-1", "invalid", "2"])
def test_invalid_page_returns_404(authenticated_client: Client, page: str) -> None:
    response = authenticated_client.get(reverse("api:user-list"), {"page": page})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_anonymous_user_cannot_list_accounts(client: Client) -> None:
    response = client.get(reverse("api:user-list"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_inactive_user_cannot_list_accounts(
    authenticated_client: Client, user: User
) -> None:
    user.is_active = False
    user.save()

    response = authenticated_client.get(reverse("api:user-list"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_listing_users_does_not_require_csrf(user: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.get(reverse("api:user-list"))

    assert response.status_code == HTTPStatus.OK


def test_user_selected_from_directory_can_be_assigned(
    authenticated_client: Client, user: User, django_user_model: type[User]
) -> None:
    assignee = django_user_model.objects.create_user(username="assignee")
    directory = authenticated_client.get(reverse("api:user-list")).json()
    selected = next(item for item in directory["results"] if item["id"] == assignee.pk)

    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "Assigned from directory", "assignee_id": selected["id"]},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    task = Task.objects.get()
    assert task.author == user
    assert task.assignee == assignee


def test_deactivated_account_disappears_and_cannot_be_assigned(
    authenticated_client: Client, django_user_model: type[User]
) -> None:
    assignee = django_user_model.objects.create_user(username="assignee")
    url = reverse("api:user-list")
    assert authenticated_client.get(url).json()["count"] == 2

    assignee.is_active = False
    assignee.save()

    directory = authenticated_client.get(url).json()
    assert directory["count"] == 1
    assert assignee.pk not in [item["id"] for item in directory["results"]]
    response = authenticated_client.post(
        reverse("api:task-list"),
        {"title": "Invalid assignment", "assignee_id": assignee.pk},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not Task.objects.exists()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_directory_does_not_allow_writing_accounts(
    authenticated_client: Client, user: User, method: str
) -> None:
    count = User.objects.count()

    response = authenticated_client.generic(
        method,
        reverse("api:user-list"),
        data='{"username":"injected"}',
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert User.objects.count() == count
    user.refresh_from_db()
    assert user.username == "viewer"


def test_directory_does_not_add_queries_per_user(
    authenticated_client: Client, django_user_model: type[User]
) -> None:
    url = reverse("api:user-list")
    with CaptureQueriesContext(connection) as one_user_queries:
        first_response = authenticated_client.get(url)
    for number in range(19):
        django_user_model.objects.create_user(username=f"user-{number:03}")
    with CaptureQueriesContext(connection) as many_users_queries:
        page_response = authenticated_client.get(url)

    assert first_response.status_code == page_response.status_code == HTTPStatus.OK
    assert len(page_response.json()["results"]) == 20
    assert len(many_users_queries) == len(one_user_queries)


def test_browsable_api_does_not_display_inactive_users_or_private_fields(
    authenticated_client: Client, django_user_model: type[User]
) -> None:
    django_user_model.objects.create_user(
        username="visible-account", email="private@example.test"
    )
    django_user_model.objects.create_user(username="hidden-account", is_active=False)

    response = authenticated_client.get(
        reverse("api:user-list"), HTTP_ACCEPT="text/html"
    )

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()
    assert "visible-account" in content
    assert "hidden-account" not in content
    assert "private@example.test" not in content
