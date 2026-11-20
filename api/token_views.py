from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from api.schema import VALIDATION_ERROR_RESPONSE
from api.serializers import (
    EmptyResponseSerializer,
    ErrorSerializer,
    LoginSerializer,
    RefreshTokenRequestSerializer,
    TokenPairResponseSerializer,
)


@extend_schema(tags=["Authentication"])
@extend_schema_view(
    post=extend_schema(
        request=LoginSerializer,
        responses={
            200: TokenPairResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            401: ErrorSerializer,
        },
    ),
)
@method_decorator(never_cache, name="dispatch")
class TokenPairView(TokenObtainPairView):
    pass


@extend_schema(tags=["Authentication"])
@extend_schema_view(
    post=extend_schema(
        request=RefreshTokenRequestSerializer,
        responses={
            200: TokenPairResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            401: ErrorSerializer,
        },
    ),
)
@method_decorator(never_cache, name="dispatch")
class RefreshView(TokenRefreshView):
    pass


@extend_schema(tags=["Authentication"])
@extend_schema_view(
    post=extend_schema(
        request=RefreshTokenRequestSerializer,
        responses={
            200: EmptyResponseSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            401: ErrorSerializer,
        },
    ),
)
@method_decorator(never_cache, name="dispatch")
class BlacklistView(TokenBlacklistView):
    pass
