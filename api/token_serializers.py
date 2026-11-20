from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    PasswordField,
    TokenObtainPairSerializer,
)
from rest_framework_simplejwt.serializers import (
    TokenRefreshSerializer as SimpleTokenRefreshSerializer,
)


class TokenPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["password"] = PasswordField(trim_whitespace=False)


class TokenRefreshSerializer(SimpleTokenRefreshSerializer):
    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        try:
            return super().validate(attrs)
        except get_user_model().DoesNotExist as error:
            raise AuthenticationFailed(
                "No active account found for the given token."
            ) from error
