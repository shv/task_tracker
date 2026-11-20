from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from threading import Barrier, Event, local
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import connections, transaction
from django.test import Client
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from api.serializers import CommentSerializer, TaskSerializer
from tasks.models import Comment, Task

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_completion_does_not_restore_former_assignee(
    django_user_model: type[User],
) -> None:
    author = django_user_model.objects.create_user(username="author")
    assignee = django_user_model.objects.create_user(username="assignee")
    replacement = django_user_model.objects.create_user(username="replacement")
    task = Task.objects.create(title="Original", author=author, assignee=assignee)
    assignee_loaded = Event()
    author_loaded = Event()
    resume_assignee = Event()
    original_update = TaskSerializer.update

    def controlled_update(
        serializer: TaskSerializer, instance: Task, validated_data: dict[str, object]
    ) -> Task:
        if serializer.context["request"].user.pk == assignee.pk:
            assignee_loaded.set()
            assert resume_assignee.wait(10)
        else:
            author_loaded.set()
        return original_update(serializer, instance, validated_data)

    def update(token: str, payload: dict[str, object]) -> int:
        try:
            client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
            return client.patch(
                reverse("api:task-detail", args=[task.pk]),
                payload,
                content_type="application/json",
            ).status_code
        finally:
            connections.close_all()

    with patch.object(
        TaskSerializer, "update", autospec=True, side_effect=controlled_update
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            completing = executor.submit(
                update, str(AccessToken.for_user(assignee)), {"is_completed": True}
            )
            try:
                assert assignee_loaded.wait(10)
                reassigning = executor.submit(
                    update,
                    str(AccessToken.for_user(author)),
                    {"assignee_id": replacement.pk, "title": "Author's latest edit"},
                )
                author_loaded.wait(1)
            finally:
                resume_assignee.set()
            assert completing.result(timeout=10) == HTTPStatus.OK
            assert reassigning.result(timeout=10) == HTTPStatus.OK

    task.refresh_from_db()
    assert task.assignee == replacement
    assert task.title == "Author's latest edit"
    assert task.is_completed


@pytest.mark.parametrize("operation", ["completion", "comment"])
def test_reassignment_revokes_access_for_a_waiting_write(
    django_user_model: type[User], operation: str
) -> None:
    author = django_user_model.objects.create_user(username="author")
    assignee = django_user_model.objects.create_user(username="assignee")
    task = Task.objects.create(title="Task", author=author, assignee=assignee)
    token = str(AccessToken.for_user(assignee))
    write_started = Event()
    original_update = TaskSerializer.update
    original_create = CommentSerializer.create

    def update(
        serializer: TaskSerializer, instance: Task, validated_data: dict[str, object]
    ) -> Task:
        write_started.set()
        return original_update(serializer, instance, validated_data)

    def create(
        serializer: CommentSerializer, validated_data: dict[str, object]
    ) -> Comment:
        write_started.set()
        return original_create(serializer, validated_data)

    def send() -> int:
        try:
            client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
            if operation == "completion":
                return client.patch(
                    reverse("api:task-detail", args=[task.pk]),
                    {"is_completed": True},
                    content_type="application/json",
                ).status_code
            return client.post(
                reverse("api:comment-list", args=[task.pk]),
                {"text": "Comment from the former assignee"},
                content_type="application/json",
            ).status_code
        finally:
            connections.close_all()

    with (
        patch.object(TaskSerializer, "update", autospec=True, side_effect=update),
        patch.object(CommentSerializer, "create", autospec=True, side_effect=create),
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        with transaction.atomic():
            Task.objects.filter(pk=task.pk).update(assignee=None)
            response = executor.submit(send)
            write_started.wait(1)
        assert response.result(timeout=10) == HTTPStatus.NOT_FOUND

    task.refresh_from_db()
    assert task.assignee is None
    assert not task.is_completed
    assert not Comment.objects.filter(task=task).exists()


def test_refresh_rotation_accepts_only_one_concurrent_request(
    django_user_model: type[User],
) -> None:
    user = django_user_model.objects.create_user(username="user")
    refresh = str(RefreshToken.for_user(user))
    validated = Barrier(2)
    thread_state = local()
    original_check = RefreshToken.check_blacklist

    def controlled_check(token: RefreshToken) -> None:
        original_check(token)
        if not getattr(thread_state, "validated", False):
            thread_state.validated = True
            validated.wait(timeout=10)

    def renew() -> int:
        try:
            return (
                Client()
                .post(
                    reverse("api:token-refresh"),
                    {"refresh": refresh},
                    content_type="application/json",
                )
                .status_code
            )
        finally:
            connections.close_all()

    with patch.object(RefreshToken, "check_blacklist", controlled_check):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(renew)
            second = executor.submit(renew)
            statuses = sorted([first.result(timeout=15), second.result(timeout=15)])

    assert statuses == [HTTPStatus.OK, HTTPStatus.UNAUTHORIZED]
