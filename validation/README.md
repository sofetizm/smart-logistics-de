# Дополнительная проверка без Docker

Основной runtime проекта — PostgreSQL 17 из Docker Compose. Этот каталог содержит инфраструктуру локальной проверки в среде без Docker и без разрешения на System V shared memory.

Использованы `@electric-sql/pglite` 0.3.14 (PostgreSQL 17.5 / WebAssembly), `@electric-sql/pglite-socket` 0.0.19 и Node.js 25.9.0. В адаптере добавлена сборка полных сообщений PostgreSQL из TCP-фрагментов: исходный socket-пакет подавал фрагменты сразу в движок, что ломало большие пакеты. Проверялся полный датасет и основной код проекта.

Из этого каталога:

```bash
npm ci
node pglite-server.mjs 55439 ../artifacts/wasm-demo
# Во втором терминале — отдельная БД для тестов:
node pglite-server.mjs 55440 ../artifacts/wasm-test
```

Нужны Python-зависимости из основного `requirements.txt` и PostgreSQL `psql` в PATH для запуска `all`. Строки подключения передаются через `DATABASE_URL` и `TEST_DATABASE_URL`; сервер слушает только 127.0.0.1. Параметры клиента: user/password `postgres`, sslmode `disable`; у тестового подключения имя базы должно заканчиваться `_test`. Это локальный тестовый протокол, не сервис для публикации в сеть.

После подключения из корня проекта выполните `python -m etl.run all`, `python -m pytest -q` и `python -m tests.repeatability`. PGlite сериализует соединения, поэтому нельзя запускать тесты и основной конвейер против одного экземпляра. Для настоящей проверки конкуренции и Docker-инфраструктуры используйте основной Compose-профиль.

Первичные справочные материалы:

- [PostgreSQL 17: агрегатные функции](https://www.postgresql.org/docs/17/functions-aggregate.html)
- [CatBoostRegressor](https://catboost.ai/docs/en/concepts/python-reference_catboostregressor)
- [PGlite Socket](https://pglite.dev/docs/pglite-socket)
