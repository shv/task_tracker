# Task Tracker

Система управления задачами на Django.

## Локальный запуск

В каталоге клонированного репозитория выполните:

```bash
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver
```

## Проверки через Makefile

Команды запускаются из корня проекта с активным окружением pyenv.
Перед первым запуском установите зависимости для разработки:

```bash
poetry install --with dev
```

| Команда | Назначение |
| --- | --- |
| `make check` | Все проверки: Ruff, форматирование, mypy, Pyright и тесты |
| `make lint` | Проверка Ruff и форматирования без изменения файлов |
| `make format` | Автоматическое исправление замечаний Ruff и форматирование файлов |
| `make typecheck` | Проверка типов через mypy и Pyright |
| `make test` | Запуск тестов через pytest |

Перед коммитом запускайте `make check`. Если нужно исправить форматирование,
выполните `make format`, проверьте изменения и снова запустите `make check`.

## Структура

```text
config/          Настройки Django, маршруты, ASGI и WSGI
manage.py        Команды управления Django
pyproject.toml   Зависимости и метаданные проекта
poetry.lock      Зафиксированные версии зависимостей
poetry.toml      Локальная для проекта настройка Poetry
```
