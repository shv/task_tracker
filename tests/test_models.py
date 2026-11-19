from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from tasks.models import Comment, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="author")


@pytest.fixture
def assignee(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(username="assignee")


@pytest.fixture
def task(author: User) -> Task:
    return Task.objects.create(title="Prepare release", author=author)


def test_task_defaults_and_assignment_are_persisted(task: Task, assignee: User) -> None:
    task.refresh_from_db()
    assert task.description == ""
    assert task.assignee is None
    assert not task.is_completed

    updated_at = task.created_at + timedelta(minutes=1)
    with patch("django.utils.timezone.now", return_value=updated_at):
        task.assignee = assignee
        task.is_completed = True
        task.save()

    task.refresh_from_db()
    assert task.assignee == assignee
    assert task.is_completed
    assert task.updated_at == updated_at
    assert task.created_at < task.updated_at


def test_author_can_be_assignee(task: Task, author: User) -> None:
    task.assignee = author
    task.full_clean()
    task.save()

    task.refresh_from_db()
    assert task.assignee == author


@pytest.mark.parametrize("title", ["", "x" * 256])
def test_task_title_validation(task: Task, title: str) -> None:
    task.title = title

    with pytest.raises(ValidationError) as error:
        task.full_clean()

    assert "title" in error.value.message_dict


@pytest.mark.parametrize("text", ["", "x" * 10001])
def test_comment_text_validation(task: Task, author: User, text: str) -> None:
    comment = Comment(task=task, author=author, text=text)

    with pytest.raises(ValidationError) as error:
        comment.full_clean()

    assert "text" in error.value.message_dict


def test_database_rejects_empty_task_title(author: User) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.create(title="", author=author)


def test_database_rejects_empty_comment_text(task: Task, author: User) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Comment.objects.create(task=task, author=author, text="")


def test_database_requires_task_author() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.create(title="Prepare release")


def test_deleting_assignee_keeps_task(task: Task, assignee: User) -> None:
    task.assignee = assignee
    task.save()

    assignee.delete()

    task.refresh_from_db()
    assert task.assignee is None


def test_task_author_is_protected_from_deletion(task: Task, author: User) -> None:
    with pytest.raises(ProtectedError):
        author.delete()

    assert Task.objects.filter(pk=task.pk).exists()


def test_comment_author_is_protected_from_deletion(task: Task, assignee: User) -> None:
    task.assignee = assignee
    task.save()
    comment = Comment.objects.create(
        task=task, author=assignee, text="Ready for review"
    )

    with pytest.raises(ProtectedError):
        assignee.delete()

    assert Comment.objects.filter(pk=comment.pk).exists()


def test_deleting_task_deletes_its_comments(task: Task, author: User) -> None:
    comment = Comment.objects.create(task=task, author=author, text="Ready for review")
    comment_id = comment.pk

    task.delete()

    assert not Comment.objects.filter(pk=comment_id).exists()
    assert User.objects.filter(pk=author.pk).exists()


def test_tasks_and_comments_have_stable_ordering(author: User) -> None:
    first_task = Task.objects.create(title="First", author=author)
    second_task = Task.objects.create(title="Second", author=author)
    Task.objects.filter(pk=second_task.pk).update(created_at=first_task.created_at)
    first_comment = Comment.objects.create(task=first_task, author=author, text="First")
    second_comment = Comment.objects.create(
        task=first_task, author=author, text="Second"
    )
    Comment.objects.filter(pk=second_comment.pk).update(
        created_at=first_comment.created_at
    )

    assert list(Task.objects.values_list("pk", flat=True)) == [
        second_task.pk,
        first_task.pk,
    ]
    assert list(
        Comment.objects.filter(task=first_task).values_list("pk", flat=True)
    ) == [
        first_comment.pk,
        second_comment.pk,
    ]
