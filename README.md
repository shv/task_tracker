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

## Запуск через Docker Compose

Compose поднимает приложение и PostgreSQL и применяет миграции:

```bash
docker compose up --build -d dev
docker compose exec dev poetry run python manage.py createsuperuser
```

Ссылки ниже используют порт Compose `8089`;
для локального `runserver` используйте порт `8000`.

## Вход и API

В браузере войдите через [форму DRF](http://localhost:8089/api/auth/login/),
затем откройте [задачи](http://localhost:8089/api/v1/tasks/).

Для JWT получите пару токенов, указав созданные имя пользователя и пароль:

```bash
curl http://localhost:8089/api/v1/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"<username>","password":"<password>"}'
```

Передавайте `access` в `Authorization: Bearer <access>` или вставьте его
в **Authorize** в Swagger. Создание задачи: POST `/api/v1/tasks/`
с JSON `{"title":"Первая задача"}`.

Пути относительно `/api/v1/`:

| Метод | Путь | Действие |
| --- | --- | --- |
| GET / POST | `tasks/` | Список / создание задач |
| GET / PUT / PATCH / DELETE | `tasks/{id}/` | Просмотр / изменение / удаление |
| GET / POST | `tasks/{id}/comments/` | Чтение / добавление комментариев |
| GET | `users/` | Пользователи для назначения |

Назначение: PATCH с `{"assignee_id": 2}`, завершение: `{"is_completed": true}`.
Автор управляет задачей, исполнитель может менять только `is_completed`.
Обновление JWT: POST `auth/token/refresh/` с `{"refresh":"<refresh>"}`;
сохраняйте новую пару токенов из ответа.

## Документация

- [Swagger UI](http://localhost:8089/api/docs/)
- [ReDoc](http://localhost:8089/api/redoc/)
- [OpenAPI](http://localhost:8089/api/schema/)
- [Веб-интерфейс DRF](http://localhost:8089/api/v1/tasks/)
- [Правила доступа](docs/domain.md) и [авторизация](docs/authentication.md)
