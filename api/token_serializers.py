from collections.abc import Iterator
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import (
    PasswordField,
    TokenObtainPairSerializer,
)
from rest_framework_simplejwt.serializers import (
    TokenBlacklistSerializer as SimpleTokenBlacklistSerializer,
)
from rest_framework_simplejwt.serializers import (
    TokenRefreshSerializer as SimpleTokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken


@contextmanager
def locked_refresh(raw_token: str) -> Iterator[None]:
    with transaction.atomic():
        # SimpleJWT decodes strings here but annotates the argument as Token.
        token = RefreshToken(raw_token)  # type: ignore[arg-type]
        try:
            OutstandingToken.objects.select_for_update().get(
                jti=token[api_settings.JTI_CLAIM]
            )
        except OutstandingToken.DoesNotExist as error:
            raise InvalidToken("Token is not recognised.") from error
        # The serializer rechecks the blacklist after locking: only one request wins.
        yield


class TokenPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # SimpleJWT's default field strips spaces that can be part of a password.
        self.fields["password"] = PasswordField(trim_whitespace=False)


class TokenRefreshSerializer(SimpleTokenRefreshSerializer):
    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        try:
            with locked_refresh(attrs["refresh"]):
                return super().validate(attrs)
        except get_user_model().DoesNotExist as error:
            raise AuthenticationFailed(
                "No active account found for the given token."
            ) from error


class TokenBlacklistSerializer(SimpleTokenBlacklistSerializer):
    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        with locked_refresh(attrs["refresh"]):
            return super().validate(attrs)
