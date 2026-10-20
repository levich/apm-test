# Angie Proxy Manager

Панель управления Angie OSS / PRO для одного Linux-сервера. Python 3.13, FastAPI, SQLAlchemy, SQLite, Tabler, Jinja2 и HTMX. Собственный код — MIT.

**Текущая версия: `0.1.0.dev0`, внутренняя контрольная сборка. План релиза 1.0 ещё не выполнен полностью.** Состояние каждой группы функций и оставшиеся работы перечислены в [матрице](docs/COMPATIBILITY.md). Публикация проекта и образов не выполнялась.

## Что уже работает

- Одноразовая установка администратора, серверные сессии, CSRF, три роли, шифрование секретов, TOTP/recovery codes, OIDC с явной привязкой пользователя.
- Формы RU/EN: HTTP/HTTPS, locations, redirects, TCP/UDP, upstream-группы, ACL, сертификаты, DNS, TLS, заголовки, внешняя авторизация, география и runtime.
- Неизменяемые версии конфигурации, `angie -t`, reload с проверкой поколения, автоматический возврат и остановка применений при ошибке отката.
- Certbot HTTP-01/DNS-01; адаптеры Webnames, Yandex, REG.RU, Selectel v2 и Cloud.ru Evolution. Реальный wildcard у провайдеров пока не принят.
- Docker discovery по `apm.*`, события и полное сопоставление; шлюз с явным списком разрешённых запросов чтения.
- Локальные ресурсы Tabler, документация API, операции, аудит, метрики, журналы, зашифрованные backup/restore и консервативный импорт.

На настоящем Angie 1.12.4 проверены HTTP, TLS, gRPC через HTTP/2, HTTP/3 через QUIC, TCP, UDP и сохранение рабочего маршрута после ошибочного изменения. Контейнерная установка Linux, расширенная сборка и PRO требуют отдельной приёмки.

## Быстрый запуск на Linux

Нужен обычный rootful Docker Engine и Compose v2 на Linux amd64/arm64. Порты 80, 81, 443, 8181 и 18081 должны быть свободны; для HTTP/3 нужен UDP/443. Angie использует host network.

```sh
cp .env.example .env
# Укажите внешний адрес панели в APM_PUBLIC_URL.
docker compose build manager
docker compose build angie
docker compose up -d
docker compose exec manager apm setup-token
```

Откройте `https://SERVER:81`, введите локально полученный токен и создайте администратора. Для первоначального HTTPS используется локальный самоподписанный сертификат. Стандартного пароля нет. Backend опубликован на `127.0.0.1:8181`.

Сначала настройте ресурс, затем следите за заданием на странице «Операции». Успешное сохранение означает запись желаемого состояния; фактическое применение подтверждается отдельно. Ошибка `angie -t` сохраняет прежнюю работающую версию.

Для расширенного OSS-образа после сборки обычных образов:

```sh
docker compose -f compose.yaml -f compose.extended.yaml build angie
docker compose -f compose.yaml -f compose.extended.yaml up -d
```

Этот Dockerfile и закреплённые исходники подготовлены, но сборка ещё не прошла приёмку. PRO подключается через `APM_ANGIE_IMAGE` с лицензированным Debian-образом 1.12.4 и совместимыми модулями. Лицензия и бинарные файлы PRO в проект не включены.

## Локальный тест с Angie в Docker Desktop

Для локального запуска используйте дополнительный файл: он подключает Angie к сети Compose, публикует порты только на loopback и хранит тестовые данные в отдельном Docker volume. Backend панели доступен Angie как `manager:8181`.

Адрес backend задан одинаково у агента и worker, чтобы повторное применение сохраняло доступ к панели. Worker запускается после проверки готовности Angie и его Unix-агента.

```sh
docker compose -f compose.yaml -f compose.local.yaml build manager
docker compose -f compose.yaml -f compose.local.yaml build angie
docker compose -f compose.yaml -f compose.local.yaml up -d --no-build
docker compose -f compose.yaml -f compose.local.yaml exec manager apm setup-token
```

Панель: `https://localhost:81` с локальным самоподписанным сертификатом. HTTP-маршруты: `http://localhost:8088`, HTTPS/QUIC: `https://localhost:8443`. Адреса backend в маршрутах относятся к сети контейнеров; для приложения на macOS используйте `host.docker.internal`. Нужен Compose с поддержкой YAML-тега `!reset`.

Если реестр Angie недоступен, можно собрать локальную базу из официального архива. Dockerfile проверяет SHA256 по `build/sources.lock.json`; расширенные сторонние модули в эту базу не входят:

```sh
mkdir -p build/cache
curl -fL https://download.angie.software/files/angie-1.12.4.tar.gz -o build/cache/angie.tar.gz
docker build -f deploy/local/Dockerfile -t apm-angie-source:1.12.4 .
docker compose -f compose.yaml -f compose.local.yaml build --build-arg ANGIE_IMAGE=apm-angie-source:1.12.4 angie
docker compose -f compose.yaml -f compose.local.yaml up -d --no-build
```

Остановка: `docker compose -f compose.yaml -f compose.local.yaml down`. Volume сохраняется для следующего запуска; добавление `--volumes` удаляет локальные тестовые данные. Этот профиль не подтверждает production host network на Linux.

## Запуск с существующим сервером Angie

Если Angie уже установлен на этом Linux-хосте, используйте самостоятельный `compose.existing.yaml`: manager и worker работают в контейнерах, локальный агент проверяет конфигурацию и делает reload существующего сервера. APM подключает свои HTTP/stream-маршруты через include, сохраняя основной конфиг и прежние виртуальные хосты. Второй контейнер Angie не нужен.

Подготовьте `.env.existing` из `.env.existing.example`, общий абсолютный путь данных, локальный агент и включения по [пошаговой инструкции](docs/EXISTING_ANGIE.md). После подготовки:

```sh
docker compose --env-file .env.existing -f compose.existing.yaml up -d
docker compose --env-file .env.existing -f compose.existing.yaml exec manager apm setup-token
```

Этот Compose-файл используется отдельно от основного. Панель открывается по HTTPS через существующий Angie; backend остаётся на `127.0.0.1:8181`. Доступа только к HTTP API Angie недостаточно — необходим локальный агент с правами проверки и reload.

## Локальная разработка

```sh
uv sync --frozen --group dev --no-editable
export APM_DATA_DIR="$PWD/data"
export APM_COOKIE_SECURE=false  # только локальный HTTP
uv run --frozen --no-sync apm serve --host 127.0.0.1 --port 8181
```

В другом терминале с теми же переменными выполните `uv run --no-sync apm setup-token`. Интерфейс и API работают без Angie; применяемые операции требуют worker и локального Unix-агента. Для обновления установленного wheel после изменения исходников повторите `uv sync --no-editable` или задайте `PYTHONPATH=src`.

```sh
uv run --no-sync pytest
uv run --no-sync ruff check src tests scripts
uv run --no-sync playwright install chromium
uv run --no-sync python scripts/browser_check.py --url http://127.0.0.1:8181 --data ./data --output ./test-results/browser
```

Браузерная проверка использует отдельный пустой каталог данных и создаёт тестового пользователя. Для настоящего бинарного файла:

```sh
uv run --no-sync python scripts/check_angie.py \
  --binary /path/to/angie --conf-dir /path/to/angie/conf --work ./test-results/angie
```

Этот сценарий использует высокие локальные порты, тестовые upstream-серверы и временные данные. Наличие rootless-проверки не подтверждает host network, s6, BPF или поведение PRO.

## Docker labels

Разрешите discovery в `.env`, задайте списки сетей и доменных зон. У контейнера должны быть IPv4-адрес в разрешённой сети и явно указанный порт приложения.

```dotenv
APM_DISCOVERY_ENABLED=true
APM_DISCOVERY_NETWORKS=["apps"]
APM_DISCOVERY_DOMAINS=["example.com"]
APM_DISCOVERY_ACME_TERMS_AGREED=true
APM_ACME_EMAIL=admin@example.com
```

```yaml
labels:
  apm.enable: "true"
  apm.host: app.example.com
  apm.network: apps
  apm.port: "8080"
  apm.scheme: http
  apm.tls: dns
  apm.dns-profile: production-dns
```

Создайте DNS-профиль `production-dns` заранее и разрешите discovery в его форме. Для HTTP-01 используйте `apm.tls: http`; A/AAAA-записи создаются отдельно. Одинаковые домены объединяют контейнеры в upstream только при совместимых метках. Ручные объекты не перезаписываются; удаление контейнера выключает маршрут при следующем сопоставлении.

## Сертификаты и DNS

В создании и редактировании прокси-хоста настройки разделены на вкладки «Основное», «Пути», «SSL» и «Дополнительно». Во вкладке SSL выберите готовый сертификат или «Запросить новый сертификат Let's Encrypt», укажите HTTP-01/DNS-01, email и согласие с условиями. Для DNS-01 нужен заранее созданный DNS-профиль; wildcard использует DNS-01. Кнопка «Сохранить и запросить сертификат» создаёт связанный сертификат и ставит выпуск в очередь. Результат показывается в «Операциях»; повторное сохранение хоста с привязанным сертификатом не запускает новый выпуск.

Кнопка «?» рядом с параметром открывает описание с примерами и условиями применения. Справка доступна для всех 40 параметров хоста и вложенных путей на RU/EN, работает по нажатию, с клавиатуры и на телефоне. Escape закрывает только подсказку и возвращает фокус к кнопке; значения формы при этом сохраняются.

Certbot запускается в worker в режиме `certonly`; Angie получает статические версионные PEM-пути. DNS-токены шифруются ключом `data/master.key`, который хранится отдельно от SQLite. Поля секретов доступны только на запись.

| Провайдер | Поля секрета | Поля профиля |
|---|---|---|
| Webnames | `username`, `password` | `zone` |
| Yandex Cloud DNS | `iam_token` или `service_account_id`, `key_id`, `private_key` | `zone`, `zone_id` |
| REG.RU | `username`, `password` | `zone` |
| Selectel v2 | `token` или `username`, `password`, `domain_name`, `project_id` | `zone`, `zone_id` |
| Cloud.ru Evolution | `token` или `key_id`, `secret` | `zone`, `zone_id` |

Проверка профиля проверяет чтение, а не обещает наличие разрешения записи. Собственные DNS-адаптеры сохраняют посторонние TXT-значения. Webnames сериализует запросы и хранит историю лимитов. После перезапуска worker очищает сохранённые незавершённые challenge.

Для проб ACME задайте staging directory выбранного CA. Нельзя считать приёмку DNS завершённой на основании имитации API. Необходимы реальные тестовые зоны всех пяти провайдеров.

## Статика / PHP

В формах создания и редактирования сайта кнопка «?» описывает все восемь параметров на RU/EN: название, включение, домены, каталог, сертификат, PHP-FPM и два варианта списка файлов. Справка содержит примеры и требования к каждому параметру.

«Каталог сайта» — имя подкаталога в `APM_DATA_DIR/sites`, например `company` для `/data/sites/company` при стандартном каталоге данных. Файлы нужно разместить или подключить отдельно; Angie ищет `index.html`, затем `index.php`. Для PHP укажите доступный FastCGI-адрес, например `php-fpm:9000`, и обеспечьте одинаковые абсолютные пути к скриптам в Angie и PHP-FPM. PHP-контейнер форма не запускает. Для сайта с PHP не оставляйте адрес FPM пустым: исходники могут отдаваться как обычные файлы.

Сертификат предварительно запросите или загрузите на странице «Сертификаты», затем выберите в форме сайта. HTTPS добавляется без автоматического перенаправления с HTTP. Список файлов раскрывает содержимое каталога; вариант fancyindex требует соответствующего модуля Angie.

## Импорт, копии и восстановление

```sh
apm export-npm snapshot.json --sqlite /path/to/npm/database.sqlite \
  --certificates /path/to/letsencrypt
# PostgreSQL: DSN запрашивается скрытым вводом и не сохраняется.
apm export-npm snapshot.json --postgres
```

Экспортёр открывает SQLite только для чтения; PostgreSQL — в `REPEATABLE READ READ ONLY`. Загрузите snapshot через «Импорт / копии». Сначала показывается отчёт. Неизвестные защитные расширения, несогласованные ACL, отсутствующие PEM и произвольные директивы блокируют активацию. Можно создать выключенные черновики для ручной проверки. Поддержка конкретных схем NPM/NPMPlus ещё требует реальных исходных снимков.

```sh
docker compose exec manager apm backup-password
# Копия через UI попадает в data/exports и доступна только администратору.
docker compose stop manager worker angie
docker compose run --rm --no-deps manager backup
docker compose run --rm --no-deps manager restore /data/exports/BACKUP_ID.apm
docker compose up -d
```

Архив защищён Scrypt и Fernet и включает ключ шифрования БД. Сохраните пароль вне сервера. Restore выполняется при остановленных сервисах, отзывает сессии, сохраняет прежний каталог данных и ставит повторную генерацию конфигурации в очередь. После restore снова задайте пароль будущих копий командой `apm backup-password`. Для переноса между серверами после восстановления проверьте адреса backend и доступность DNS/API.

`scripts/update.sh` делает копию перед сборкой и запуском обновления. Для возврата используйте прежний образ и соответствующий архив; обратная миграция БД не предполагается.

## Наблюдаемость и дополнительные сервисы

Access logs включаются явно в runtime; журнал действий панели ведётся отдельно. По умолчанию IP в access logs маскируются, query string не записывается. Метрики собираются с локального API Angie. Ошибки агента не раскрывают конфигурацию или секреты в ответе API.

Для GoAccess включите `access_logs` и `analytics`, затем запустите Compose с `-f compose.analytics.yaml`. Отчёт доступен через защищённый маршрут `/analytics/goaccess`; у sidecar нет сети, сертификатов, DNS-токенов и Docker socket. Профиль ещё требует контейнерной проверки.

CrowdSec использует закреплённую официальную Lua-библиотеку и собственный адаптер. На сервере допускается один общий профиль bouncer. AppSec требует буферизации; нечитаемые тела HTTP/2–3 отклоняются. Полная приёмка CAPTCHA, больших тел, streaming и отказов ещё впереди. GeoIP-профиль принимает MaxMind `account_id` и `license_key` и обновляет версии Country/ASN по отдельному заданию.

Произвольные директивы и pre-run hooks предназначены для доверенного администратора. Hooks монтируются из конфигурации развёртывания в `/etc/apm/pre-run.d`; HTTP API не принимает команды. Локальные команды восстановления: `apm reset-password EMAIL --reset-mfa`, `apm resume-applies`.

## Документы и лицензии

- [Согласованный план реализации 1.0](PLAN.md)
- [Архитектура и API](docs/ARCHITECTURE.md)
- [Контейнер APM с существующим Angie](docs/EXISTING_ANGIE.md)
- [Матрица 25 групп и критерии выпуска](docs/COMPATIBILITY.md)
- [Протокол проведённых проверок](docs/VALIDATION.md)
- [Первоначальный план — архив, заменён планом 1.0](docs/archive/original-plan.md)
- [Манифест сборки](build/manifest.json), `uv.lock`, `build/sources.lock.json`
- [MIT](LICENSE), [лицензии зависимостей](THIRD_PARTY_NOTICES.md)

Референсы: [Angie](https://angie.software/angie/docs/), [NPMPlus](https://github.com/ZoeyVid/NPMPlus), [Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html), [Tabler](https://tabler.io/admin-template). Код NPMPlus в проект не переносился.
