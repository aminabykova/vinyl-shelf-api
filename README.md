# Vinyl Shelf API

Рабочая заглушка API сервиса цифровой коллекции виниловых пластинок. Реализует все эндпоинты из `openapi.yaml`: валидацию, статусы экземпляров и лотов, проверки владения и коды ошибок. Данные хранятся в памяти и пропадают при перезапуске.

## Запуск

Нужен Python 3.9 или новее.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8080
```

После запуска:

- интерактивная документация и проверка запросов: <http://localhost:8080/docs> (кнопка **Authorize**, токен `user-1`);
- схема, сгенерированная приложением: <http://localhost:8080/openapi.json>.

## Авторизация

Настоящий JWT проверяет API Gateway, в заглушке его нет. Принимается токен вида `user-<число>`: заголовок `Authorization: Bearer user-1` означает пользователя с id 1, `user-2` - пользователя 2 и так далее. Без токена или с другим значением ответ `401`.

## Эндпоинты

| Метод | Путь | Что делает | Успех |
|---|---|---|---|
| GET | `/api/v1/catalog/lookup?barcode=` | Релизы по штрихкоду | 200 |
| POST | `/api/v1/collection/items` | Черновик карточки (`DRAFT`) | 201 |
| PATCH | `/api/v1/collection/items/{id}` | Состояние, заметка, подтверждение (`IN_COLLECTION`) | 200 |
| POST | `/api/v1/marketplace/listings` | Выставить на продажу (`ON_SALE`) | 201 |
| DELETE | `/api/v1/marketplace/listings/{id}` | Снять лот (`IN_COLLECTION`) | 204 |
| POST | `/api/v1/social/reviews` | Ревью на релиз | 201 |
| PATCH | `/api/v1/social/reviews/{id}` | Изменить своё ревью | 200 |
| POST | `/api/v1/collection/wantlist` | Добавить релиз в Wantlist | 201 |
| DELETE | `/api/v1/collection/wantlist/{id}` | Удалить из Wantlist | 204 |

Ошибки всегда в формате `{"code": "...", "message": "..."}`: `400` (в том числе ошибки валидации), `401`, `403`, `404`, `409`, `503`.

## Как проверить

1. **Автотесты** (26 проверок, запросы к приложению без сервера):

   ```bash
   pytest
   ```

2. **Сценарий по живому серверу** (сервер запущен на порту 8080):

   ```bash
   ./smoke.sh
   ```

   Скрипт делает запросы через `curl`, печатает код каждого ответа и итог. На Windows запускайте через Git Bash или WSL.

3. **Вручную**: файл `requests.http` (VS Code с расширением REST Client или JetBrains) либо Swagger UI на `/docs`. Схему `openapi.yaml` можно импортировать в Postman.

## Что в заглушке упрощено

| В боевой системе | В заглушке |
|---|---|
| Discogs API, Redis и БД каталога | Словарь релизов в `app/store.py`; штрихкоды `0602537284332` (два релиза), `5099902988627`, `0888837000000`; штрихкод `0000000000000` имитирует недоступность Discogs (`503`) |
| JWT и сервис аутентификации | Токен `user-<число>` |
| Collection, Marketplace, Social как отдельные сервисы и брокер | Одно приложение; смена статуса экземпляра делается в том же запросе, что создание лота |
| Notification Service и Push / Email | Журнал в памяти: при создании лота подписчикам Wantlist (с `notify = true`, кроме продавца) добавляется запись, её видно в `GET /debug/notifications` |
| Покупка релиза на маркетплейсе | Не реализована, ревью можно оставить на релиз из коллекции (`IN_COLLECTION` или `ON_SALE`) |

Служебные эндпоинты вне схемы API: `POST /debug/reset` (очистить данные), `GET /debug/notifications`, `GET /health`.

## Структура

```
app/main.py      эндпоинты и бизнес-правила
app/schemas.py   модели запросов и ответов
app/store.py     данные в памяти и тестовые релизы
app/auth.py      заглушка авторизации
app/errors.py    единый формат ошибок
tests/           автотесты, включая сверку путей с openapi.yaml
openapi.yaml     схема API
requests.http    готовые запросы
smoke.sh         сценарий для curl
```
