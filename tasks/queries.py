from django.db.models import Q, QuerySet

from tasks.models import Task


def tasks_for_user(user_id: int | None) -> QuerySet[Task]:
    return Task.objects.filter(Q(author_id=user_id) | Q(assignee_id=user_id))
