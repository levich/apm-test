# Системные настройки

Настройки читаются из APM_* и .env при запуске процесса. После изменения перезапустите нужные сервисы; затем примените конфигурацию. Списки передавайте JSON-массивами. Значения ниже — встроенные defaults, а не содержимое вашего .env.

## `APM_DATA_DIR`

<!-- environment:APM_DATA_DIR -->
Общий каталог SQLite, ключей, сертификатов, ревизий, журналов и сайтов. В existing-режиме одинаковый абсолютный путь у всех сервисов.

По умолчанию: `"data"`.

Формат: `string`. Пример: `"data"`.

## `APM_DATABASE_URL`

<!-- environment:APM_DATABASE_URL -->
URL базы данных. Реализация и миграции рассчитаны на SQLite; не считайте другие SQLAlchemy backend поддержанными без отдельной проверки.

По умолчанию: `null`.

Формат: `string / null`. Пример: `"sqlite:////data/apm.sqlite3"`.

## `APM_COOKIE_SECURE`

<!-- environment:APM_COOKIE_SECURE -->
Передавать cookie только по HTTPS. false допустимо для изолированной локальной разработки по HTTP.

По умолчанию: `true`.

Формат: `boolean`. Пример: `true`.

## `APM_SESSION_SECONDS`

<!-- environment:APM_SESSION_SECONDS -->
Срок серверной сессии в секундах, по умолчанию 12 часов.

По умолчанию: `43200`.

Формат: `integer`. Пример: `43200`.

## `APM_AGENT_SOCKET`

<!-- environment:APM_AGENT_SOCKET -->
Путь Unix-сокета агента. null использует APM_DATA_DIR/run/agent.sock. Нужен общий доступ manager/worker/агента по правам файлов.

По умолчанию: `null`.

Формат: `string / null`. Пример: `"/data/run/agent.sock"`.

## `APM_ANGIE_BINARY`

<!-- environment:APM_ANGIE_BINARY -->
Исполняемый файл Angie, доступный агенту. В existing-режиме обычно /usr/sbin/angie.

По умолчанию: `"angie"`.

Формат: `string`. Пример: `"angie"`.

## `APM_ANGIE_MODE`

<!-- environment:APM_ANGIE_MODE -->
managed генерирует полный конфиг; existing подключает http.conf/stream.conf к существующему серверу без замены основного конфига.

По умолчанию: `"managed"`.

Формат: `string`. Допустимые значения: managed, existing. Пример: `"managed"`.

## `APM_ANGIE_CONFIG`

<!-- environment:APM_ANGIE_CONFIG -->
Основной конфиг Angie; null в managed использует APM_DATA_DIR/angie.conf. В existing требуется абсолютный существующий путь.

По умолчанию: `null`.

Формат: `string / null`. Пример: `"/etc/angie/angie.conf"`.

## `APM_ANGIE_PREFIX`

<!-- environment:APM_ANGIE_PREFIX -->
Prefix для запуска Angie -p, одинаковый для проверки и reload. В existing обязателен абсолютный путь.

По умолчанию: `null`.

Формат: `string / null`. Пример: `"/etc/angie"`.

## `APM_ANGIE_STATUS_URL`

<!-- environment:APM_ANGIE_STATUS_URL -->
Локальный API Angie с generation для подтверждения reload. Должен быть доступен агенту и не публиковаться наружу.

По умолчанию: `"http://127.0.0.1:18081/status/angie"`.

Формат: `string`. Пример: `"http://127.0.0.1:18081/status/angie"`.

## `APM_BACKEND_URL`

<!-- environment:APM_BACKEND_URL -->
Адрес manager, на который Angie проксирует панель. Для локального Compose http://manager:8181. Значения worker и агента должны совпадать.

По умолчанию: `"http://127.0.0.1:8181"`.

Формат: `string`. Пример: `"http://127.0.0.1:8181"`.

## `APM_ADMIN_LISTEN`

<!-- environment:APM_ADMIN_LISTEN -->
Адрес и порт HTTPS-панели в managed-конфиге Angie, например 0.0.0.0:81. Не меняет порт процесса manager.

По умолчанию: `"0.0.0.0:81"`.

Формат: `string`. Пример: `"0.0.0.0:81"`.

## `APM_DEFAULT_LANGUAGE`

<!-- environment:APM_DEFAULT_LANGUAGE -->
Язык по умолчанию: ru или en. Язык пользователя и cookie переключателя интерфейса имеют приоритет при отображении.

По умолчанию: `"ru"`.

Формат: `string`. Пример: `"ru"`.

## `APM_DOCKER_URL`

<!-- environment:APM_DOCKER_URL -->
Origin read-only Docker gateway для discovery. Пример http://docker-gateway:2375; не используйте публичный незащищённый Docker API.

По умолчанию: `"http://docker-gateway:2375"`.

Формат: `string`. Пример: `"http://docker-gateway:2375"`.

## `APM_DISCOVERY_ENABLED`

<!-- environment:APM_DISCOVERY_ENABLED -->
Запустить наблюдение событий и регулярное сопоставление Docker labels. Необходимо явно разрешить сети и доменные зоны.

По умолчанию: `false`.

Формат: `boolean`. Пример: `false`.

## `APM_DISCOVERY_NETWORKS`

<!-- environment:APM_DISCOVERY_NETWORKS -->
JSON-массив разрешённых сетей Docker, например ["apps"]. Контейнер должен иметь IPv4 в выбранной сети.

По умолчанию: `[]`.

Формат: `array`. Пример: `["apps"]`.

## `APM_DISCOVERY_DOMAINS`

<!-- environment:APM_DISCOVERY_DOMAINS -->
JSON-массив разрешённых доменных зон, например ["example.com"]. Домены вне списка discovery не импортирует.

По умолчанию: `[]`.

Формат: `array`. Пример: `["example.com"]`.

## `APM_DISCOVERY_ACME_TERMS_AGREED`

<!-- environment:APM_DISCOVERY_ACME_TERMS_AGREED -->
Явное согласие с условиями ACME для автоматических запросов сертификатов Docker discovery.

По умолчанию: `false`.

Формат: `boolean`. Пример: `false`.

## `APM_ACME_EMAIL`

<!-- environment:APM_ACME_EMAIL -->
Email ACME-аккаунта для автоматически создаваемых сертификатов. Укажите адрес владельца системы.

По умолчанию: `""`.

Формат: `string`. Пример: `"admin@example.com"`.

## `APM_OIDC_ISSUER`

<!-- environment:APM_OIDC_ISSUER -->
Issuer OpenID Connect провайдера; пустая строка отключает OIDC. Metadata берутся из /.well-known/openid-configuration.

По умолчанию: `""`.

Формат: `string`. Пример: `"https://id.example.com"`.

## `APM_OIDC_CLIENT_ID`

<!-- environment:APM_OIDC_CLIENT_ID -->
Client ID приложения APM в OIDC-провайдере. Используется вместе с issuer и, если нужен, client secret.

По умолчанию: `""`.

Формат: `string`. Пример: `"apm"`.

## `APM_OIDC_CLIENT_SECRET_FILE`

<!-- environment:APM_OIDC_CLIENT_SECRET_FILE -->
Путь файла с OIDC client secret, читаемый при старте manager. Секрет не передаётся через форму пользователя.

По умолчанию: `null`.

Формат: `string / null`. Пример: `"/run/secrets/oidc-client-secret"`.

## `APM_PUBLIC_URL`

<!-- environment:APM_PUBLIC_URL -->
Внешний URL панели и база для OIDC callback. Не создаёт DNS, listener и сертификат автоматически.

По умолчанию: `"https://localhost:81"`.

Формат: `string`. Пример: `"https://localhost:81"`.

## `APM_OIDC_ONLY`

<!-- environment:APM_OIDC_ONLY -->
Отключить обычный парольный вход и использовать OIDC. Заранее привяжите существующего администратора к OIDC subject.

По умолчанию: `false`.

Формат: `boolean`. Пример: `false`.

## `APM_CERTBOT_BINARY`

<!-- environment:APM_CERTBOT_BINARY -->
Исполняемый файл Certbot в worker. Используется certonly; секреты EAB передаются через временный файл.

По умолчанию: `"certbot"`.

Формат: `string`. Пример: `"certbot"`.

## `APM_ACME_SERVER`

<!-- environment:APM_ACME_SERVER -->
Directory URL ACME CA для автоматически создаваемых сертификатов. Отдельные ресурсы сертификатов имеют собственное поле server.

По умолчанию: `"https://acme-v02.api.letsencrypt.org/directory"`.

Формат: `string`. Пример: `"https://acme-v02.api.letsencrypt.org/directory"`.

## `APM_METRICS_RETENTION_DAYS`

<!-- environment:APM_METRICS_RETENTION_DAYS -->
Срок истории метрик и очистки ротированных журналов в днях. Размер истории дополнительно ограничен 10080 точками.

По умолчанию: `7`.

Формат: `integer`. Пример: `7`.

## `APM_PRE_RUN_DIR`

<!-- environment:APM_PRE_RUN_DIR -->
Каталог локальных *.sh hooks установки. Файлы не должны быть symlink или доступны группе/всем на запись; каждый выполняется до 60 секунд.

По умолчанию: `"/etc/apm/pre-run.d"`.

Формат: `string`. Пример: `"/etc/apm/pre-run.d"`.

## `APM_DEVELOPMENT`

<!-- environment:APM_DEVELOPMENT -->
Режим разработки. Не считайте его заменой настройки cookie_secure или ограничения публикации backend.

По умолчанию: `false`.

Формат: `boolean`. Пример: `false`.

## `APM_ANGIE_IMAGE`

<!-- environment:APM_ANGIE_IMAGE -->
Параметр Compose/build, не Settings Python. По умолчанию docker.angie.software/angie:1.12.4-debian. Выбирайте образ с нужными совместимыми модулями; PRO требует вашей лицензии.

[Compose](deployment.md) · [Docker discovery](discovery.md) · [Runtime](runtime.md)
