from typing import NoReturn, cast

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q, QuerySet
from django.middleware.csrf import get_token
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
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ViewSet

from api.exceptions import EndpointNotImplemented
from api.serializers import (
    CommentPageSerializer,
    CommentSerializer,
    CommentWriteSerializer,
    CsrfSerializer,
    ErrorSerializer,
    LoginSerializer,
    TaskPageSerializer,
    TaskSerializer,
    UserPageSerializer,
    UserSerializer,
)
from tasks.models import Task

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
        responses={
            200: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **ERROR_RESPONSES,
        },
    ),
    partial_update=extend_schema(
        request=TaskSerializer,
        responses={
            200: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **ERROR_RESPONSES,
        },
    ),
    destroy=extend_schema(
        responses={204: None, 404: ErrorSerializer, **ERROR_RESPONSES},
    ),
)
class TaskViewSet(
    CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet[Task]
):
    queryset: QuerySet[Task] = Task.objects.all()
    serializer_class = TaskSerializer
    lookup_value_converter = "int"

    def get_queryset(self) -> QuerySet[Task]:
        user = self.request.user
        return self.queryset.filter(Q(author_id=user.pk) | Q(assignee_id=user.pk))

    def perform_create(self, serializer: BaseSerializer[Task]) -> None:
        serializer.save(author=self.request.user)

    def update(self, request: Request, pk: int | None = None) -> NoReturn:
        raise EndpointNotImplemented

    def partial_update(self, request: Request, pk: int | None = None) -> NoReturn:
        raise EndpointNotImplemented

    def destroy(self, request: Request, pk: int | None = None) -> NoReturn:
        raise EndpointNotImplemented


@extend_schema(tags=["Comments"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={
            200: CommentPageSerializer,
            404: ErrorSerializer,
            **ERROR_RESPONSES,
        },
    ),
    create=extend_schema(
        request=CommentWriteSerializer,
        responses={
            201: CommentSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **ERROR_RESPONSES,
        },
    ),
)
class CommentViewSet(ViewSet):
    def list(self, request: Request, task_id: int) -> NoReturn:
        raise EndpointNotImplemented

    def create(self, request: Request, task_id: int) -> NoReturn:
        raise EndpointNotImplemented


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
