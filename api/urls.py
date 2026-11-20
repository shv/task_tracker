from django.urls import include, path
from rest_framework.routers import SimpleRouter

from api.token_views import BlacklistView, RefreshView, TokenPairView
from api.views import (
    CommentViewSet,
    CsrfView,
    CurrentUserView,
    LoginView,
    LogoutView,
    TaskViewSet,
    UserViewSet,
)

app_name = "api"

router = SimpleRouter(use_regex_path=False)
router.register("tasks", TaskViewSet, basename="task")
router.register("tasks/<int:task_id>/comments", CommentViewSet, basename="comment")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("auth/token/", TokenPairView.as_view(), name="token-pair"),
    path(
        "auth/token/refresh/",
        RefreshView.as_view(),
        name="token-refresh",
    ),
    path(
        "auth/token/blacklist/",
        BlacklistView.as_view(),
        name="token-blacklist",
    ),
]
