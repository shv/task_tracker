from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers


class ErrorSerializer(serializers.Serializer[dict[str, object]]):
    detail = serializers.CharField()


class UserSerializer(serializers.ModelSerializer[AbstractBaseUser]):
    class Meta:
        model = get_user_model()
        fields = ("id", "username")
        read_only_fields = fields


class TaskWriteSerializer(serializers.Serializer[dict[str, object]]):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True, default="")
    assignee_id = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    is_completed = serializers.BooleanField(default=False)


class TaskSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(allow_blank=True)
    author_id = serializers.IntegerField(min_value=1)
    assignee_id = serializers.IntegerField(min_value=1, allow_null=True)
    is_completed = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CommentWriteSerializer(serializers.Serializer[dict[str, object]]):
    text = serializers.CharField(max_length=10000)


class CommentSerializer(CommentWriteSerializer):
    id = serializers.IntegerField(min_value=1)
    task_id = serializers.IntegerField(min_value=1)
    author_id = serializers.IntegerField(min_value=1)
    created_at = serializers.DateTimeField()


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
