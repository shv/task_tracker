from typing import NoReturn

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

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
    TaskWriteSerializer,
    UserPageSerializer,
    UserSerializer,
)

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


@extend_schema(tags=["Tasks"])
@extend_schema_view(
    list=extend_schema(
        parameters=[PAGE_PARAMETER],
        responses={200: TaskPageSerializer, **ERROR_RESPONSES},
    ),
    create=extend_schema(
        request=TaskWriteSerializer,
        responses={
            201: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            **ERROR_RESPONSES,
        },
    ),
    retrieve=extend_schema(
        responses={200: TaskSerializer, 404: ErrorSerializer, **ERROR_RESPONSES},
    ),
    update=extend_schema(
        request=TaskWriteSerializer,
        responses={
            200: TaskSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: ErrorSerializer,
            **ERROR_RESPONSES,
        },
    ),
    partial_update=extend_schema(
        request=TaskWriteSerializer,
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
class TaskViewSet(ViewSet):
    lookup_value_converter = "int"

    def list(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented

    def create(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented

    def retrieve(self, request: Request, pk: int | None = None) -> NoReturn:
        raise EndpointNotImplemented

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
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: CsrfSerializer, 501: ErrorSerializer})
    def get(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented


@extend_schema(tags=["Authentication"])
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: UserSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            **ERROR_RESPONSES,
        },
    )
    def post(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented


@extend_schema(tags=["Authentication"])
class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None, **ERROR_RESPONSES})
    def post(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented


@extend_schema(tags=["Authentication"])
class CurrentUserView(APIView):
    @extend_schema(responses={200: UserSerializer, **ERROR_RESPONSES})
    def get(self, request: Request) -> NoReturn:
        raise EndpointNotImplemented
