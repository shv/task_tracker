from http import HTTPStatus

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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
    return Task.objects.create(title="Task", author=author, assignee=assignee)


@pytest.fixture
def author_client(author: User) -> Client:
    client = Client()
    client.force_login(author)
    return client


@pytest.mark.parametrize(
    "role", ["author", "assignee", "outsider", "staff", "superuser"]
)
def test_comments_access_follows_parent_task_visibility(
    client: Client,
    task: Task,
    author: User,
    assignee: User,
    other_user: User,
    role: str,
) -> None:
    actor = {"author": author, "assignee": assignee}.get(role, other_user)
    actor.is_staff = role in {"staff", "superuser"}
    actor.is_superuser = role == "superuser"
    actor.save()
    existing = Comment.objects.create(task=task, author=author, text="Existing")
    client.force_login(actor)
    url = reverse("api:comment-list", args=[task.pk])

    list_response = client.get(url)
    create_response = client.post(
        url, {"text": "New comment"}, content_type="application/json"
    )

    if role in {"author", "assignee"}:
        assert list_response.status_code == HTTPStatus.OK
        assert list_response.json()["count"] == 1
        assert list_response.json()["results"][0]["id"] == existing.pk
        assert create_response.status_code == HTTPStatus.CREATED
        created = Comment.objects.get(pk=create_response.json()["id"])
        assert created.task == task
        assert created.author == actor
        assert created.text == "New comment"
        assert create_response.json() == {
            "id": created.pk,
            "task_id": task.pk,
            "author_id": actor.pk,
            "text": created.text,
            "created_at": create_response.json()["created_at"],
        }
        assert (
            parse_datetime(create_response.json()["created_at"]) == created.created_at
        )
    else:
        assert list_response.status_code == HTTPStatus.NOT_FOUND
        assert create_response.status_code == HTTPStatus.NOT_FOUND
        assert Comment.objects.count() == 1


def test_empty_comments_list_is_distinct_from_missing_task(
    author_client: Client, task: Task
) -> None:
    response = author_client.get(reverse("api:comment-list", args=[task.pk]))

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }


def test_comment_author_and_task_cannot_be_overridden(
    author_client: Client, task: Task, author: User, other_user: User
) -> None:
    foreign_task = Task.objects.create(title="Other task", author=other_user)

    response = author_client.post(
        reverse("api:comment-list", args=[task.pk]),
        {
            "text": "  Привет, команда  ",
            "id": 99999999,
            "task_id": foreign_task.pk,
            "task": foreign_task.pk,
            "author_id": other_user.pk,
            "author": other_user.pk,
            "created_at": "2000-01-01T00:00:00Z",
        },
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    comment = Comment.objects.get()
    assert comment.task == task
    assert comment.author == author
    assert comment.text == "Привет, команда"
    assert comment.pk != 99999999
    assert comment.created_at.year > 2000


@pytest.mark.parametrize("text", ["", "   ", None, "x" * 10001, [], {}])
def test_invalid_text_does_not_create_comment(
    author_client: Client, task: Task, text: object
) -> None:
    response = author_client.post(
        reverse("api:comment-list", args=[task.pk]),
        {"text": text},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "text" in response.json()
    assert not Comment.objects.exists()


def test_text_is_required(author_client: Client, task: Task) -> None:
    response = author_client.post(
        reverse("api:comment-list", args=[task.pk]), {}, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "text" in response.json()
    assert not Comment.objects.exists()


def test_comment_accepts_maximum_text_length(author_client: Client, task: Task) -> None:
    text = "x" * 10000

    response = author_client.post(
        reverse("api:comment-list", args=[task.pk]),
        {"text": text},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED
    assert Comment.objects.get().text == text


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_missing_parent_returns_404_before_comment_validation(
    author_client: Client, method: str
) -> None:
    response = author_client.generic(
        method,
        reverse("api:comment-list", args=[99999999]),
        data="{}",
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert not Comment.objects.exists()


@pytest.mark.parametrize("remove_assignee", [False, True])
def test_former_assignee_loses_access_but_comments_remain(
    author_client: Client,
    task: Task,
    assignee: User,
    other_user: User,
    remove_assignee: bool,
) -> None:
    old_comment = Comment.objects.create(task=task, author=assignee, text="Old comment")
    former_client = Client()
    former_client.force_login(assignee)
    url = reverse("api:comment-list", args=[task.pk])
    assert former_client.get(url).status_code == HTTPStatus.OK

    response = author_client.patch(
        reverse("api:task-detail", args=[task.pk]),
        {"assignee_id": None if remove_assignee else other_user.pk},
        content_type="application/json",
    )
    assert response.status_code == HTTPStatus.OK

    assert former_client.get(url).status_code == HTTPStatus.NOT_FOUND
    response = former_client.post(url, {}, content_type="application/json")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert Comment.objects.get() == old_comment
    assert author_client.get(url).json()["count"] == 1
    if not remove_assignee:
        new_client = Client()
        new_client.force_login(other_user)
        assert new_client.get(url).status_code == HTTPStatus.OK
        response = new_client.post(
            url, {"text": "New assignee comment"}, content_type="application/json"
        )
        assert response.status_code == HTTPStatus.CREATED
        assert Comment.objects.get(pk=response.json()["id"]).author == other_user


def test_completed_task_can_be_commented(author_client: Client, task: Task) -> None:
    task.is_completed = True
    task.save()

    response = author_client.post(
        reverse("api:comment-list", args=[task.pk]),
        {"text": "Follow-up"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CREATED


def test_comments_pagination_is_scoped_and_chronological(
    author_client: Client, task: Task, author: User
) -> None:
    comments = Comment.objects.bulk_create(
        [
            Comment(task=task, author=author, text=f"Comment {number}")
            for number in range(21)
        ]
    )
    other_task = Task.objects.create(title="Another visible task", author=author)
    Comment.objects.bulk_create(
        [
            Comment(task=other_task, author=author, text=f"Other {number}")
            for number in range(25)
        ]
    )
    Comment.objects.filter(task=task).update(created_at=timezone.now())
    url = reverse("api:comment-list", args=[task.pk])

    first_page = author_client.get(url).json()
    second_page = author_client.get(url, {"page": 2}).json()

    assert first_page["count"] == second_page["count"] == 21
    assert [item["id"] for item in first_page["results"]] == [
        item.pk for item in comments[:20]
    ]
    assert [item["id"] for item in second_page["results"]] == [comments[20].pk]
    assert first_page["previous"] is None
    assert first_page["next"] == f"http://testserver{url}?page=2"
    assert second_page["previous"] == f"http://testserver{url}"
    assert second_page["next"] is None
    assert author_client.get(url, {"page": 3}).status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_anonymous_user_cannot_access_comments(
    client: Client, task: Task, method: str
) -> None:
    response = client.generic(
        method,
        reverse("api:comment-list", args=[task.pk]),
        data='{"text":"Forbidden"}',
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert not Comment.objects.exists()


def test_inactive_user_cannot_access_comments(
    author_client: Client, task: Task, author: User
) -> None:
    author.is_active = False
    author.save()
    url = reverse("api:comment-list", args=[task.pk])

    assert author_client.get(url).status_code == HTTPStatus.UNAUTHORIZED
    response = author_client.post(
        url, {"text": "Forbidden"}, content_type="application/json"
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert not Comment.objects.exists()


def test_comment_creation_requires_csrf_but_reading_does_not(
    task: Task, author: User
) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(author)
    url = reverse("api:comment-list", args=[task.pk])
    assert client.get(url).status_code == HTTPStatus.OK

    response = client.post(
        url, {"text": "New comment"}, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert not Comment.objects.exists()
    token = client.get(reverse("api:csrf")).json()["csrf_token"]
    response = client.post(
        url,
        {"text": "New comment"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == HTTPStatus.CREATED
    assert Comment.objects.get().author == author


def test_comments_list_does_not_add_queries_per_comment(
    author_client: Client, task: Task, assignee: User
) -> None:
    Comment.objects.create(task=task, author=assignee, text="First")
    url = reverse("api:comment-list", args=[task.pk])
    with CaptureQueriesContext(connection) as one_comment_queries:
        first_response = author_client.get(url)
    Comment.objects.bulk_create(
        [Comment(task=task, author=assignee, text=f"Comment {i}") for i in range(19)]
    )
    with CaptureQueriesContext(connection) as many_comments_queries:
        page_response = author_client.get(url)

    assert first_response.status_code == page_response.status_code == HTTPStatus.OK
    assert len(page_response.json()["results"]) == 20
    assert len(many_comments_queries) == len(one_comment_queries)


def test_browsable_api_only_displays_comments_of_requested_task(
    author_client: Client, task: Task, author: User
) -> None:
    Comment.objects.create(task=task, author=author, text="Visible comment text")
    other_task = Task.objects.create(title="Other task", author=author)
    Comment.objects.create(task=other_task, author=author, text="Foreign comment text")

    response = author_client.get(
        reverse("api:comment-list", args=[task.pk]), HTTP_ACCEPT="text/html"
    )

    assert response.status_code == HTTPStatus.OK
    assert "Visible comment text" in response.content.decode()
    assert "Foreign comment text" not in response.content.decode()
