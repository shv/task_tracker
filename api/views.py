from typing import NoReturn, cast

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import QuerySet
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
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
from rest_framework.viewsets import GenericViewSet, ViewSet

from api.exceptions import EndpointNotImplemented
from api.permissions import TaskPermission
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

ERROR_RESPONSES = {
    403: OpenApiResponse(
        ErrorSerializer, description="Authentication or access denied."
    ),
    501: OpenApiResponse(ErrorSerializer, description="Endpoint is a stub."),
}
VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
    },
    description="Validation errors grouped by field, including non_field_errors.",
)
PAGE_PARAMETER = OpenApiParameter(
    name="page", type=int, description="Page number, starting from 1. Page size: 20."
)
CSRF_PARAMETER = OpenApiParameter(
    name="X-CSRFToken",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="CSRF token from auth/csrf/. Refresh the token after login.",
)


@extend_schema(tags=["Tasks"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={
            200: TaskPageSerializer,
            403: ERROR_RESPONSES[403],
            404: ErrorSerializer,
        },
    ),
    create=extend_schema(
        request=TaskSerializer,
        responses={
            201: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ERROR_RESPONSES[403],
        },
    ),
    retrieve=extend_schema(
        responses={
            200: TaskSerializer,
            403: ERROR_RESPONSES[403],
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
            403: ERROR_RESPONSES[403],
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
            403: ERROR_RESPONSES[403],
        },
    ),
    destroy=extend_schema(
        request=None,
        parameters=[CSRF_PARAMETER],
        description="Only the task author may delete it. Its comments are deleted too.",
        responses={204: None, 403: ERROR_RESPONSES[403], 404: ErrorSerializer},
    ),
)
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
        return tasks_for_user(self.request.user.pk)

    def perform_create(self, serializer: BaseSerializer[Task]) -> None:
        serializer.save(author=self.request.user)


@extend_schema(tags=["Comments"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={
            200: CommentPageSerializer,
            404: ErrorSerializer,
            403: ERROR_RESPONSES[403],
        },
    ),
    create=extend_schema(
        request=CommentSerializer,
        parameters=[CSRF_PARAMETER],
        responses={
            201: CommentSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            403: ERROR_RESPONSES[403],
        },
    ),
)
class CommentViewSet(CreateModelMixin, ListModelMixin, GenericViewSet[Comment]):
    queryset: QuerySet[Comment] = Comment.objects.all()
    serializer_class = CommentSerializer
    task: Task

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        super().initial(request, *args, **kwargs)
        self.task = get_object_or_404(
            tasks_for_user(request.user.pk), pk=self.kwargs["task_id"]
        )

    def get_queryset(self) -> QuerySet[Comment]:
        return self.queryset.filter(task=self.task)

    def perform_create(self, serializer: BaseSerializer[Comment]) -> None:
        serializer.save(task=self.task, author=self.request.user)


@extend_schema(tags=["Users"])
class UserViewSet(ViewSet):
    @extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={200: UserPageSerializer, **ERROR_RESPONSES},
    )
    def list(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented


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
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        parameters=[CSRF_PARAMETER],
        responses={
            200: UserSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ERROR_RESPONSES[403],
        },
    )
    def post(self, request: Request) -> Response:
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
    @extend_schema(
        request=None,
        parameters=[CSRF_PARAMETER],
        responses={204: None, 403: ERROR_RESPONSES[403]},
    )
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Authentication"])
@method_decorator(never_cache, name="dispatch")
class CurrentUserView(APIView):
    @extend_schema(responses={200: UserSerializer, 403: ERROR_RESPONSES[403]})
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(cast(AbstractBaseUser, request.user)).data)
