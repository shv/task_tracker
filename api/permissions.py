from collections.abc import Mapping

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from tasks.models import Task


class TaskPermission(BasePermission):
    message = "Only the author may edit task fields; assignees may PATCH is_completed."

    def has_object_permission(self, request: Request, view: APIView, obj: Task) -> bool:
        # The view's queryset already limits objects to authors and current assignees.
        if request.method in SAFE_METHODS or obj.author_id == request.user.pk:
            return True
        return (
            request.method == "PATCH"
            and isinstance(request.data, Mapping)
            and set(request.data) <= {"is_completed"}
        )
