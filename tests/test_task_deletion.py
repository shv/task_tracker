from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from tasks.models import Comment, Task

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
    return Task.objects.create(title="Delete me", author=author, assignee=assignee)


@pytest.mark.parametrize(
    "state", ["assigned", "unassigned", "self_assigned", "completed"]
)
def test_author_can_delete_task_in_any_state(
    client: Client, task: Task, author: User, state: str
) -> None:
    if state == "unassigned":
        task.assignee = None
    elif state == "self_assigned":
        task.assignee = author
    elif state == "completed":
        task.is_completed = True
    task.save()
    client.force_login(author)
    url = reverse("api:task-detail", args=[task.pk])

    response = client.delete(url)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert response.content == b""
    assert not Task.objects.filter(pk=task.pk).exists()
    assert client.get(url).status_code == HTTPStatus.NOT_FOUND
    assert client.get(reverse("api:task-list")).json()["count"] == 0


def test_deletion_removes_only_task_and_its_comments(
    client: Client, task: Task, author: User, assignee: User, other_user: User
) -> None:
    task_comments = [
        Comment.objects.create(task=task, author=author, text="Author comment"),
        Comment.objects.create(task=task, author=assignee, text="Assignee comment"),
    ]
    remaining_task = Task.objects.create(title="Keep me", author=other_user)
    remaining_comment = Comment.objects.create(
        task=remaining_task, author=other_user, text="Keep this comment"
    )
    client.force_login(author)

    response = client.delete(reverse("api:task-detail", args=[task.pk]))

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not Comment.objects.filter(
        pk__in=[item.pk for item in task_comments]
    ).exists()
    assert Task.objects.get() == remaining_task
    assert Comment.objects.get() == remaining_comment
    assert (
        User.objects.filter(pk__in=[author.pk, assignee.pk, other_user.pk]).count() == 3
    )


@pytest.mark.parametrize("role", ["assignee", "outsider", "staff", "superuser"])
def test_only_author_can_delete_task(
    client: Client, task: Task, assignee: User, other_user: User, role: str
) -> None:
    actor = assignee if role == "assignee" else other_user
    actor.is_staff = role in {"staff", "superuser"}
    actor.is_superuser = role == "superuser"
    actor.save()
    comment = Comment.objects.create(task=task, author=assignee, text="Keep me")
    before = Task.objects.values().get(pk=task.pk)
    client.force_login(actor)

    response = client.delete(reverse("api:task-detail", args=[task.pk]))

    expected_status = (
        HTTPStatus.FORBIDDEN if role == "assignee" else HTTPStatus.NOT_FOUND
    )
    assert response.status_code == expected_status
    assert Task.objects.values().get(pk=task.pk) == before
    assert Comment.objects.filter(pk=comment.pk).exists()


def test_anonymous_user_cannot_delete_task(client: Client, task: Task) -> None:
    response = client.delete(reverse("api:task-detail", args=[task.pk]))

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.filter(pk=task.pk).exists()


def test_inactive_author_cannot_delete_task(
    client: Client, task: Task, author: User
) -> None:
    client.force_login(author)
    author.is_active = False
    author.save()

    response = client.delete(reverse("api:task-detail", args=[task.pk]))

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.filter(pk=task.pk).exists()


def test_repeated_deletion_returns_404(
    client: Client, task: Task, author: User
) -> None:
    client.force_login(author)
    url = reverse("api:task-detail", args=[task.pk])

    assert client.delete(url).status_code == HTTPStatus.NO_CONTENT
    assert client.delete(url).status_code == HTTPStatus.NOT_FOUND


def test_missing_task_returns_404(client: Client, author: User) -> None:
    client.force_login(author)

    response = client.delete(reverse("api:task-detail", args=[99999999]))

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_deletion_requires_csrf_token(task: Task, author: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(author)
    url = reverse("api:task-detail", args=[task.pk])
    comment = Comment.objects.create(
        task=task, author=author, text="Keep until deletion"
    )

    response = client.delete(url)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert Task.objects.filter(pk=task.pk).exists()
    assert Comment.objects.filter(pk=comment.pk).exists()
    token = client.get(reverse("api:csrf")).json()["csrf_token"]

    response = client.delete(url, HTTP_X_CSRFTOKEN=token)

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not Task.objects.filter(pk=task.pk).exists()
    assert not Comment.objects.filter(pk=comment.pk).exists()
