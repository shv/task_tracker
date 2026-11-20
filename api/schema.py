from drf_spectacular.utils import OpenApiParameter, OpenApiResponse

from api.serializers import ErrorSerializer

PERMISSION_ERROR_RESPONSE = OpenApiResponse(
    ErrorSerializer, description="Authentication or access denied."
)
AUTH_ERROR_RESPONSES = {401: ErrorSerializer, 403: PERMISSION_ERROR_RESPONSE}
VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {
            "oneOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "string"},
            ]
        },
    },
    description="Field validation errors or a detail message for malformed JSON.",
)
PAGE_PARAMETER = OpenApiParameter(
    name="page", type=int, description="Page number, starting from 1. Page size: 20."
)
CSRF_PARAMETER = OpenApiParameter(
    name="X-CSRFToken",
    type=str,
    location=OpenApiParameter.HEADER,
    required=False,
    description=(
        "Required for session authentication only; JWT does not require CSRF. "
        "Get the token from auth/csrf/ and refresh it after login."
    ),
)

SESSION_CSRF_PARAMETER = OpenApiParameter(
    name="X-CSRFToken",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="CSRF token from auth/csrf/. Refresh the token after login.",
)
