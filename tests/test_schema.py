from http import HTTPStatus

import pytest
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse


@pytest.mark.parametrize("view_name", ["api-docs", "api-redoc"])
def test_documentation_uses_local_assets(client: Client, view_name: str) -> None:
    response = client.get(reverse(view_name))

    assert response.status_code == HTTPStatus.OK
    assert "/static/drf_spectacular_sidecar/" in response.content.decode()


@pytest.mark.parametrize(
    "asset",
    [
        "drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css",
        "drf_spectacular_sidecar/redoc/bundles/redoc.standalone.js",
    ],
)
def test_documentation_assets_are_installed(asset: str) -> None:
    assert finders.find(asset) is not None


def test_schema_describes_all_endpoints_without_stubs(client: Client) -> None:
    response = client.get(
        reverse("api-schema"), HTTP_ACCEPT="application/vnd.oai.openapi+json"
    )

    assert response.status_code == HTTPStatus.OK
    schema = response.json()
    assert schema["openapi"] == "3.0.3"

    expected_paths = {
        "/api/v1/tasks/": {"get", "post"},
        "/api/v1/tasks/{id}/": {"get", "put", "patch", "delete"},
        "/api/v1/tasks/{task_id}/comments/": {"get", "post"},
        "/api/v1/users/": {"get"},
        "/api/v1/auth/csrf/": {"get"},
        "/api/v1/auth/login/": {"post"},
        "/api/v1/auth/logout/": {"post"},
        "/api/v1/auth/me/": {"get"},
        "/api/v1/auth/token/": {"post"},
        "/api/v1/auth/token/refresh/": {"post"},
        "/api/v1/auth/token/blacklist/": {"post"},
    }
    assert set(schema["paths"]) == set(expected_paths)
    for path, methods in expected_paths.items():
        assert set(schema["paths"][path]) == methods
        for method in methods:
            responses = schema["paths"][path][method]["responses"]
            assert "501" not in responses

    components = schema["components"]["schemas"]
    write_schema = components["TaskRequest"]
    assert write_schema["required"] == ["title"]
    assert set(write_schema["properties"]) == {
        "title",
        "description",
        "assignee_id",
        "is_completed",
    }
    assert not components["PatchedTaskRequest"].get("required")
    comment_request = components["CommentRequest"]
    assert comment_request["required"] == ["text"]
    assert set(comment_request["properties"]) == {"text"}
    assert comment_request["properties"]["text"]["maxLength"] == 10000
    assert set(components["User"]["properties"]) == {"id", "username"}
    assert set(components["TokenPairResponse"]["properties"]) == {"access", "refresh"}
    assert schema["components"]["securitySchemes"]["jwtAuth"]["scheme"] == "bearer"
    task_list_schema = schema["paths"]["/api/v1/tasks/"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert task_list_schema == {"$ref": "#/components/schemas/TaskPage"}


@pytest.mark.parametrize(
    ("path", "method", "required"),
    [
        ("/api/v1/tasks/", "post", False),
        ("/api/v1/tasks/{id}/", "put", False),
        ("/api/v1/tasks/{id}/", "patch", False),
        ("/api/v1/tasks/{id}/", "delete", False),
        ("/api/v1/tasks/{task_id}/comments/", "post", False),
        ("/api/v1/auth/login/", "post", True),
        ("/api/v1/auth/logout/", "post", True),
    ],
)
def test_schema_requires_csrf_only_for_session_endpoints(
    client: Client, path: str, method: str, required: bool
) -> None:
    schema = client.get(
        reverse("api-schema"), HTTP_ACCEPT="application/vnd.oai.openapi+json"
    ).json()

    parameters = schema["paths"][path][method]["parameters"]
    csrf = next(
        parameter for parameter in parameters if parameter["name"] == "X-CSRFToken"
    )
    assert csrf.get("required", False) is required
