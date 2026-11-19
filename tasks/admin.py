from django.contrib import admin

from tasks.models import Comment, Task

# Register your models here.

admin.site.register([Task, Comment])
