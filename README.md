# Task Tracker

Система управления задачами на Django.

## Локальный запуск

В каталоге клонированного репозитория выполните:

```bash
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver
```

## Структура

```text
config/          Настройки Django, маршруты, ASGI и WSGI
manage.py        Команды управления Django
pyproject.toml   Зависимости и метаданные проекта
poetry.lock      Зафиксированные версии зависимостей
poetry.toml      Локальная для проекта настройка Poetry
```
