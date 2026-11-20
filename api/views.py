from typing import cast

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import QuerySet
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from api.permissions import TaskPermission
from api.schema import (
    AUTH_ERROR_RESPONSES,
    CSRF_PARAMETER,
    PAGE_PARAMETER,
    PERMISSION_ERROR_RESPONSE,
    SESSION_CSRF_PARAMETER,
    VALIDATION_ERROR_RESPONSE,
)
from api.serializers import (
    CommentPageSerializer,
    CommentSerializer,
    CsrfSerializer,
    ErrorSerializer,
    LoginSerializer,
    TaskPageSerializer,
    TaskSerializer,
    UserPageSerializer,
    UserSerializer,
)
from tasks.models import Comment, Task
from tasks.queries import tasks_for_user


@extend_schema(tags=["Tasks"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={
            200: TaskPageSerializer,
            **AUTH_ERROR_RESPONSES,
            404: ErrorSerializer,
        },
    ),
    create=extend_schema(
        request=TaskSerializer,
        parameters=[CSRF_PARAMETER],
        responses={
            201: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            **AUTH_ERROR_RESPONSES,
        },
    ),
    retrieve=extend_schema(
        responses={
            200: TaskSerializer,
            **AUTH_ERROR_RESPONSES,
            404: ErrorSerializer,
        },
    ),
    update=extend_schema(
        request=TaskSerializer,
        parameters=[CSRF_PARAMETER],
        description="Only the task author may use PUT. The title field is required.",
        responses={
            200: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **AUTH_ERROR_RESPONSES,
        },
    ),
    partial_update=extend_schema(
        request=TaskSerializer,
        parameters=[CSRF_PARAMETER],
        description=(
            "The author may edit task fields. The current assignee may only send "
            "is_completed; additional fields are rejected with 403."
        ),
        responses={
            200: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **AUTH_ERROR_RESPONSES,
        },
    ),
    destroy=extend_schema(
        request=None,
        parameters=[CSRF_PARAMETER],
        description="Only the task author may delete it. Its comments are deleted too.",
        responses={204: None, **AUTH_ERROR_RESPONSES, 404: ErrorSerializer},
    ),
)
@method_decorator(transaction.atomic, name="dispatch")
class TaskViewSet(
    CreateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet[Task],
):
    queryset: QuerySet[Task] = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, TaskPermission]
    lookup_value_converter = "int"

    def get_queryset(self) -> QuerySet[Task]:
        queryset = tasks_for_user(self.request.user.pk)
        if self.action in {"update", "partial_update", "destroy"}:
            # Keep permissions and writes on the same task version during reassignment.
            queryset = queryset.select_for_update()
        return queryset

    def perform_create(self, serializer: BaseSerializer[Task]) -> None:
        serializer.save(author=self.request.user)


@extend_schema(tags=["Comments"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={
            200: CommentPageSerializer,
            404: ErrorSerializer,
            **AUTH_ERROR_RESPONSES,
        },
    ),
    create=extend_schema(
        request=CommentSerializer,
        parameters=[CSRF_PARAMETER],
        responses={
            201: CommentSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **AUTH_ERROR_RESPONSES,
        },
    ),
)
@method_decorator(transaction.atomic, name="dispatch")
class CommentViewSet(CreateModelMixin, ListModelMixin, GenericViewSet[Comment]):
    queryset: QuerySet[Comment] = Comment.objects.all()
    serializer_class = CommentSerializer
    task: Task

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        super().initial(request, *args, **kwargs)
        queryset = tasks_for_user(request.user.pk)
        if request.method == "POST":
            # Reassignment must not revoke access between this check and insertion.
            queryset = queryset.select_for_update()
        self.task = get_object_or_404(queryset, pk=self.kwargs["task_id"])

    def get_queryset(self) -> QuerySet[Comment]:
        return self.queryset.filter(task=self.task)

    def perform_create(self, serializer: BaseSerializer[Comment]) -> None:
        serializer.save(task=self.task, author=self.request.user)


@extend_schema(tags=["Users"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={
            200: UserPageSerializer,
            **AUTH_ERROR_RESPONSES,
            404: ErrorSerializer,
        },
    ),
)
class UserViewSet(ListModelMixin, GenericViewSet[AbstractBaseUser]):
    queryset: QuerySet[AbstractBaseUser] = (
        get_user_model()
        .objects.filter(is_active=True)
        .only("id", "username")
        .order_by("username", "pk")
    )
    serializer_class = UserSerializer


@extend_schema(tags=["Authentication"])
@method_decorator(never_cache, name="dispatch")
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: CsrfSerializer})
    def get(self, request: Request) -> Response:
        return Response({"csrf_token": get_token(request._request)})


@extend_schema(tags=["Authentication"])
@method_decorator(never_cache, name="dispatch")
class LoginView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        parameters=[SESSION_CSRF_PARAMETER],
        responses={
            200: UserSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: PERMISSION_ERROR_RESPONSE,
        },
    )
    def post(self, request: Request) -> Response:
        # DRF skips CSRF for anonymous sessions, but login must also be protected.
        SessionAuthentication().enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request._request, **serializer.validated_data)
        if user is None:
            raise AuthenticationFailed("Invalid username or password.")
        login(request._request, user)
        return Response(UserSerializer(user).data)


@extend_schema(tags=["Authentication"])
@method_decorator(never_cache, name="dispatch")
class LogoutView(APIView):
    authentication_classes = [SessionAuthentication]

    @extend_schema(
        request=None,
        parameters=[SESSION_CSRF_PARAMETER],
        responses={204: None, 403: PERMISSION_ERROR_RESPONSE},
    )
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Authentication"])
@method_decorator(never_cache, name="dispatch")
class CurrentUserView(APIView):
    @extend_schema(responses={200: UserSerializer, **AUTH_ERROR_RESPONSES})
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(cast(AbstractBaseUser, request.user)).data)
