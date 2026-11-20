from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from tasks.models import Comment, Task


class ErrorSerializer(serializers.Serializer[dict[str, object]]):
    detail = serializers.CharField()


class UserSerializer(serializers.ModelSerializer[AbstractBaseUser]):
    class Meta:
        model = get_user_model()
        fields = ("id", "username")
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer[Task]):
    author_id = serializers.IntegerField(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source="assignee",
        queryset=get_user_model().objects.filter(is_active=True),
        pk_field=serializers.IntegerField(min_value=1),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Task
        fields = (
            "id",
            "title",
            "description",
            "author_id",
            "assignee_id",
            "is_completed",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "author_id", "created_at", "updated_at")


class CommentSerializer(serializers.ModelSerializer[Comment]):
    task_id = serializers.IntegerField(read_only=True)
    author_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "task_id", "author_id", "text", "created_at")
        read_only_fields = ("id", "task_id", "author_id", "created_at")


@extend_schema_serializer(many=False)
class PageSerializer(serializers.Serializer[dict[str, object]]):
    count = serializers.IntegerField(min_value=0)
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)


class TaskPageSerializer(PageSerializer):
    results = TaskSerializer(many=True)


class CommentPageSerializer(PageSerializer):
    results = CommentSerializer(many=True)


class UserPageSerializer(PageSerializer):
    results = UserSerializer(many=True)


class LoginSerializer(serializers.Serializer[dict[str, object]]):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class CsrfSerializer(serializers.Serializer[dict[str, object]]):
    csrf_token = serializers.CharField()
