# Подробная инструкция по развёртыванию Angie Proxy Manager

Инструкция относится к исходникам версии `0.1.0.dev0` и закреплённой в проекте Angie `1.12.4`. Образы APM собираются из исходников: публичный репозиторий образов пока не предоставляется. Это внутренняя сборка; подтверждённые сценарии и ограничения перечислены в [матрице совместимости](COMPATIBILITY.md) и [протоколе проверок](VALIDATION.md).

## Содержание

1. [Выбор варианта установки](#variants)
2. [Подготовка сервера и исходников](#prepare)
3. [Linux: Angie внутри Compose](#managed)
4. [Linux: существующий системный Angie](#existing)
5. [Локальный Docker Desktop](#local)
6. [Проверка установки и первый вход](#verify)
7. [Первый прокси-хост и сертификат](#proxy)
8. [Статический сайт и PHP-FPM](#sites)
9. [Данные и резервное копирование](#backup)
10. [Обновление, восстановление и возврат версии](#maintenance)
11. [CrowdSec, GeoIP и Docker discovery](#optional)
12. [Диагностика и остановка](#troubleshooting)

<a id="variants"></a>

## 1. Выбор варианта установки

| Вариант | Когда использовать | Compose-файлы | Где работает Angie | Где находятся данные |
|---|---|---|---|---|
| A. Linux с Angie в Compose | Отдельный сервер для APM | `compose.yaml` | В контейнере с сетью хоста | `./data` на хосте → `/data` |
| B. Существующий Angie | На сервере уже работают сайты | Только `compose.existing.yaml` | Системный сервис на том же хосте | `/srv/apm` → `/srv/apm` |
| C. Локальный тест | Проверка на macOS / Docker Desktop | `compose.yaml` + `compose.local.yaml` | В контейнере в сети Compose | Docker volume → `/data` |

Выберите один вариант. A и B по умолчанию используют одинаковое имя проекта Compose и порт backend `8181`: их нельзя запускать рядом без отдельной настройки. Локальный вариант имеет имя проекта `angie-proxy-manager-local` и отдельное хранилище, но тоже занимает `8181`.

Перед выбором образа проверьте [таблицу функций, модулей и требований PRO](MODULES.md): для текущих функций APM достаточно соответствующей OSS-сборки; отдельные серверные возможности PRO пока не имеют настроек в панели.

Основные компоненты:

| Сервис | Назначение |
|---|---|
| `init` | Создаёт каталоги и устанавливает права; нормальное завершение — `Exited (0)` |
| `manager` | Интерфейс, API, пользователи, SQLite и желаемое состояние |
| `worker` | Очередь применения, сертификаты и фоновые операции |
| `angie` | Обслуживает трафик; содержит Unix-агент APM в вариантах A/C |
| `docker-gateway` | Предоставляет ограниченный набор запросов чтения Docker для discovery |
| `apm-agent.service` | Агент на хосте в варианте B: проверяет конфигурацию и выполняет reload |

В дальнейших командах используется функция `dc`, которая сохраняет набор Compose-флагов выбранного варианта, и переменная `apm_data_path` с путём данных внутри контейнера. Определите обе в разделе своего варианта. В новом терминале снова перейдите в каталог проекта и определите их заново. Не подменяйте функцию обычным `docker compose` при обслуживании вариантов B/C.

<a id="prepare"></a>

## 2. Подготовка сервера и исходников

### 2.1. Требования

- Для A/B: Linux `amd64` или `arm64`, обычный rootful Docker Engine и Compose plugin с командой `docker compose`. Rootless-установка этим профилем не проверялась.
- Для C: работающий Docker Desktop и Compose с поддержкой YAML-тега `!reset`. Поддержку проверяет `config --quiet` перед запуском.
- Доступ к реестрам и источникам сборки: Docker Hub, GHCR, `docker.angie.software`, GitHub и пакетным репозиториям базовых образов. Для резервной сборки Angie нужен `download.angie.software`.
- Локальное постоянное хранилище для SQLite, ключей, сертификатов, конфигураций и сайтов. Рассчитывайте свободное место также на образы, логи и архивы. Сетевые файловые системы для SQLite и управляющего Unix socket не используйте.
- Для публичного сайта: домен и возможность настроить DNS. Для HTTP-01 нужен входящий TCP/80, для DNS-01 — доступ к DNS API.
- Для B дополнительно: системный Angie с API и stream-модулем, Python 3.13, `uv`, systemd и права администратора на хосте.

Установку Docker для своей ОС выполните по [официальной инструкции Docker Engine](https://docs.docker.com/engine/install/); Compose — по [инструкции Compose plugin](https://docs.docker.com/compose/install/linux/). На Docker Desktop Compose входит в поставку. Правила объединения файлов и `!reset` описаны в [справке Docker](https://docs.docker.com/reference/compose-file/merge/).

Для B установите `uv` по [официальной инструкции Astral](https://docs.astral.sh/uv/getting-started/installation/). Если Python 3.13 отсутствует, установите его командой `uv python install 3.13`, как описано в [руководстве uv по Python](https://docs.astral.sh/uv/guides/install-python/). В A/C Python на хосте для запуска APM не нужен: он входит в образ.

Проверка Linux-хоста:

```sh
docker version
docker compose version
docker info
uname -m
df -h
sudo ss -lntup
```

Команды Docker ниже предполагают, что текущая учётная запись имеет доступ к Docker daemon. Если у вас доступ только через `sudo`, используйте его последовательно для всех команд Docker.

### 2.2. Подготовить каталог проекта

Скопируйте полученные исходники в постоянный каталог, например `/opt/apm`. Используйте фактический адрес своего Git-репозитория или переданный архив проекта; URL публичного репозитория здесь не предполагается.

```sh
cd /opt/apm
test -f compose.yaml
test -f Dockerfile
test -f uv.lock
```

Все относительные пути далее считаются от этого каталога. Не переносите рабочий каталог варианта A без переноса `data`: относительный bind mount начнёт указывать на другое место. Для C сохраняйте имя проекта и имя volume.

### 2.3. Порты и доступ

| Порт | A: Linux Compose | B: системный Angie | C: локальный тест |
|---|---|---|---|
| TCP/80 | HTTP сайтов и HTTP-01 | Существующий listener Angie | `127.0.0.1:8088` → контейнерный 80 |
| TCP/443 | HTTPS сайтов | Существующий listener Angie | `127.0.0.1:8443` → контейнерный 443 |
| UDP/443 | HTTP/3 при его включении | По настройкам хоста | `127.0.0.1:8443/udp` → контейнерный 443 |
| TCP/81 | HTTPS панели | Не добавляется APM | `127.0.0.1:81` → контейнерный 81 |
| TCP/8181 | Backend панели, только `127.0.0.1` | Backend панели, только `127.0.0.1` | Backend панели, только `127.0.0.1` |
| TCP/18081 | API Angie, только `127.0.0.1` | Локальный API, настраивается вручную | Внутри контейнера Angie, не публикуется |

В A Angie использует сеть хоста, поэтому нужные порты должны быть свободны. Для B сохраняются работающие listener, но домены и порты новых объектов не должны конфликтовать с прежними. В C достаточно свободных локальных `81`, `8181`, `8088`, `8443`.

Разрешайте доступ к панели `81` только из своей административной сети или через VPN. `8181`, `18081` и Docker API для внешних клиентов не нужны. Для сайтов настройте firewall и внешние правила сети на требуемые TCP/80, TCP/443 и, если используется HTTP/3, UDP/443.

<a id="managed"></a>

## 3. Вариант A: Linux с Angie внутри Compose

### 3.1. Создать настройки

```sh
cd /opt/apm
umask 077
test -f .env || cp .env.example .env
chmod 600 .env
```

Отредактируйте `.env`. Для начала достаточно проверить:

```dotenv
APM_PUBLIC_URL=https://apm.example.com:81
APM_COOKIE_SECURE=true
APM_DEFAULT_LANGUAGE=ru
APM_ANGIE_IMAGE=docker.angie.software/angie:1.12.4-debian
APM_DISCOVERY_ENABLED=false
APM_ACME_EMAIL=admin@example.com
```

Замените домен панели и email своими. Если домена панели ещё нет, временно укажите `https://IP_СЕРВЕРА:81`. `APM_PUBLIC_URL` задаёт публичный URL приложения, в том числе callback OIDC; переменная не создаёт DNS, не меняет listener и не выпускает сертификат.

Для A оставьте `APM_BACKEND_URL` по умолчанию: `http://127.0.0.1:8181`. Значения для агента и worker должны совпадать, иначе следующее применение может изменить маршрут панели.

По умолчанию APM слушает панель на `0.0.0.0:81`. При необходимости задайте в `.env` `APM_ADMIN_LISTEN=АДРЕС_ИНТЕРФЕЙСА:81` и укажите соответствующий `APM_PUBLIC_URL`. Привязка к адресу возможна только если он существует на хосте Angie.

### 3.2. Проверить Compose, собрать и запустить

```sh
dc() { docker compose -f compose.yaml "$@"; }
apm_data_path=/data

dc config --quiet
dc build manager
dc build angie
dc up -d --no-build --wait --wait-timeout 120
dc ps -a
```

Собирайте последовательно: образ Angie копирует приложение из `apm-manager:dev`. Каталог `./data` создаётся и подготавливается `init` для UID/GID `10001:10001`; вручную открывать его правами `777` не требуется.

Ожидается: `init` завершён с кодом 0, `manager` и `angie` — `healthy`, `worker` и `docker-gateway` работают. Если команда ожидания завершилась с ошибкой, перейдите к [диагностике](#troubleshooting).

Панель доступна по `https://apm.example.com:81` или выбранному адресу. Начальный сертификат самоподписанный: браузер покажет предупреждение о доверии. Он обеспечивает первый доступ и не является сертификатом Let's Encrypt для вашего домена. Выбор сертификата у прокси-хоста не заменяет автоматически сертификат панели на порту 81.

Продолжите с [проверки установки и создания администратора](#verify).

<a id="existing"></a>

## 4. Вариант B: существующий системный Angie

Этот вариант работает с Angie на том же Linux-хосте. APM не управляет удалённым Angie только через HTTP API: нужен локальный агент с доступом к бинарному файлу, конфигурации и процессам сервера.

Подробности включений и ограничений приведены в [отдельной инструкции](EXISTING_ANGIE.md). Ниже — полный порядок установки с типовыми путями `/opt/apm`, `/srv/apm`, `/etc/angie`.

### 4.1. Зафиксировать параметры действующего сервера

Сохраните конфигурацию Angie вместе с подключёнными файлами и внешними сертификатами. Затем проверьте:

```sh
sudo systemctl cat angie
sudo /usr/sbin/angie -V
sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf
```

Пути выше — пример: используйте параметры реально работающего сервиса. Сверьте бинарный файл, `-c`, `-p`, `--prefix`, PID и имя сервисной учётной записи. Если PID задаётся сервисом через `-g`, эквивалентная директива должна быть доступна агенту в основном конфиге. Не заменяйте существующий `angie.conf` конфигурацией APM целиком.

### 4.2. Настроить APM и общее хранилище

```sh
cd /opt/apm
umask 077
test -f .env.existing || cp .env.existing.example .env.existing
chmod 600 .env.existing
```

Проверьте `.env.existing`:

```dotenv
APM_PUBLIC_URL=https://apm.example.com
APM_COOKIE_SECURE=true
APM_DEFAULT_LANGUAGE=ru
APM_ANGIE_MODE=existing
APM_DATA_DIR=/srv/apm
APM_ANGIE_BINARY=/usr/sbin/angie
APM_ANGIE_CONFIG=/etc/angie/angie.conf
APM_ANGIE_PREFIX=/etc/angie
APM_ANGIE_STATUS_URL=http://127.0.0.1:18081/status/angie
APM_DISCOVERY_ENABLED=false
```

`APM_DATA_DIR` должен быть одним и тем же абсолютным путём у manager, worker, агента и Angie. Используйте отдельный каталог без символических ссылок в пути. Путь `/srv/apm` внутри контейнеров также будет `/srv/apm`.

Если выбираете другой каталог, измените также `apm_data_path`, пути include и все примеры обслуживания ниже.

```sh
dc() { docker compose --env-file .env.existing -f compose.existing.yaml "$@"; }
apm_data_path=/srv/apm

uv sync --frozen --no-dev --no-editable --reinstall-package angie-proxy-manager
dc config --quiet
dc build manager
dc run --rm --no-deps init

getent group 10001 || sudo groupadd --gid 10001 apm
sudo usermod --append --groups 10001 angie
```

Замените `angie` последней команды на worker-пользователя своей установки. Он должен читать PEM, htpasswd и файлы сайтов из данных APM. Группа 10001 также имеет доступ к управляющему сокету: не добавляйте в неё посторонних пользователей. Новое членство начинает действовать у вновь запущенных процессов; для уже работающих worker Angie запланируйте перезапуск сервиса с учётом обслуживания существующих сайтов.

### 4.3. Установить агент

В шаблонах systemd проверьте путь `/opt/apm` и имя сервиса `angie.service`. Агент и watchdog используют host `.venv`; замены исходников без переустановки пакета недостаточно:

```sh
sudo install -m 644 deploy/existing/apm-agent.service /etc/systemd/system/apm-agent.service
sudo install -m 644 deploy/existing/apm-safety-watchdog.service /etc/systemd/system/apm-safety-watchdog.service
sudo install -d /etc/systemd/system/angie.service.d
sudo install -m 644 deploy/existing/angie-apm-safety.conf /etc/systemd/system/angie.service.d/apm-safety.conf
sudo systemctl daemon-reload
sudo systemctl enable --now apm-agent
sudo systemctl enable --now apm-safety-watchdog
sudo systemctl status apm-agent --no-pager
```

`ExecStartPre` создаёт начальные пустые включения. Сам агент слушает `/srv/apm/run/agent.sock`; управляющий TCP-порт не открывается. Агент читает `.env.existing`, работает с группой 10001 и `UMask=0007`.

### 4.4. Подключить маршруты APM и панель

В основном `APM_ANGIE_CONFIG` добавьте include непосредственно в соответствующие блоки:

```nginx
http {
    # Прежние настройки и сайты остаются здесь.
    include /srv/apm/current/http.conf;
}

stream {
    # Прежние TCP/UDP-настройки остаются здесь.
    include /srv/apm/current/stream.conf;
}
```

Это фрагмент структуры: второго блока `http` или `stream` создавать не нужно. Если `stream` отсутствует, добавьте его и при необходимости загрузите установленный stream-модуль. Обе строки APM include должны быть в основном файле, каждая отдельно, с абсолютным путём, без glob. Вложенное включение этих строк через `conf.d` не подходит для проверки кандидата агентом.

В `http` добавьте локальный API и HTTPS-виртуальный хост панели по [шаблону](../deploy/existing/http.conf.example). Укажите свой домен, действующий сертификат и ключ. Если локальный API уже есть, используйте его URL вместо второго listener. У панели должен быть независимый сертификат, доступный до первого применения APM.

```sh
sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf
sudo systemctl reload angie
curl --fail http://127.0.0.1:18081/status/angie

dc up -d --no-build --wait --wait-timeout 120
dc ps -a
```

APM не создаёт listener панели или status API в режиме existing и не меняет настройки процессов системного Angie. Домены прежних сайтов автоматически в панель не импортируются. При одинаковых `server_name` и портах Angie может выбрать прежний виртуальный хост даже после успешной проверки; устраняйте такие пересечения заранее.

Перед первым применением убедитесь, что worker Angie получил новые группы, затем проверьте и APM-маршрут, и один из прежних сайтов. Не редактируйте основной конфиг и не выполняйте сторонние reload одновременно с применением APM.

<a id="local"></a>

## 5. Вариант C: локальный Docker Desktop

Откройте терминал в каталоге проекта; `/opt/apm` здесь не обязателен. Подготовьте `.env`, сохраняя существующий файл:

```sh
umask 077
test -f .env || cp .env.example .env
chmod 600 .env
```

Проверьте в нём значения:

```dotenv
APM_PUBLIC_URL=https://localhost:81
APM_COOKIE_SECURE=true
APM_DEFAULT_LANGUAGE=ru
APM_DISCOVERY_ENABLED=false
```

```sh
dc() { docker compose -f compose.yaml -f compose.local.yaml "$@"; }
apm_data_path=/data

dc config --quiet
dc build manager
dc build angie
dc up -d --no-build --wait --wait-timeout 120
dc ps -a
```

Профиль сам задаёт `APM_BACKEND_URL=http://manager:8181` для агента и worker. Angie работает в сети Compose, а не в сети macOS. Данные сохраняются в volume `angie-proxy-manager-local_local-data` при стандартном имени проекта.

| Назначение | Адрес |
|---|---|
| Панель | `https://localhost:81` |
| HTTP-маршруты | `http://localhost:8088` с нужным Host |
| HTTPS-маршруты | `https://localhost:8443` с нужным именем TLS |
| Backend для диагностики | `http://127.0.0.1:8181/health/live` |

Для приложения на macOS указывайте в прокси-хосте `host.docker.internal` и порт приложения. Приложение должно слушать адрес, доступный из Docker Desktop. `127.0.0.1` внутри Angie означает сам контейнер. Для соседнего контейнера используйте имя сервиса в общей сети.

HTTP-01 требует внешнего TCP/80. Локального порта `8088` без дополнительного проброса недостаточно для публичного выпуска сертификата. Этот профиль предназначен для проверки и не подтверждает работу production host network на Linux.

### 5.1. Если недоступен реестр Angie

Из корня проекта можно собрать базовый Angie из официального исходного архива:

```sh
mkdir -p build/cache
curl -fL https://download.angie.software/files/angie-1.12.4.tar.gz -o build/cache/angie.tar.gz
docker build -f deploy/local/Dockerfile -t apm-angie-source:1.12.4 .
dc build --build-arg ANGIE_IMAGE=apm-angie-source:1.12.4 angie
dc up -d --no-build --wait --wait-timeout 120
```

Сначала должен быть собран `manager`. Dockerfile проверяет SHA256 по `build/sources.lock.json`. Это базовая сборка без набора расширенных сторонних модулей. При последующих пересборках Angie сохраняйте тот же `--build-arg`, иначе Compose снова попробует официальный реестр. Общий доступ к сети для остальных зависимостей всё равно нужен.

<a id="verify"></a>

## 6. Проверка установки и первый вход

### 6.1. Проверить backend и связь с агентом

Для всех трёх вариантов:

```sh
dc ps -a
dc logs --tail=100 manager worker
curl --fail http://127.0.0.1:8181/health/live
curl --fail http://127.0.0.1:8181/health/ready
```

`/health/live` должен вернуть HTTP 200 и версию. `/health/ready` возвращает 200 при доступной БД и свежем состоянии агента от worker; сразу после старта возможен 503. Исправный healthcheck manager сам по себе не подтверждает готовность Angie или успешное применение маршрута.

В A/C дополнительно:

```sh
dc logs --tail=100 angie
curl --insecure --fail https://localhost:81/health/live
```

`--insecure` здесь нужен только для диагностического запроса к начальному самоподписанному сертификату. Для B проверьте HTTPS по фактическому домену панели с доверенным сертификатом и `systemctl status apm-agent`.

### 6.2. Создать администратора

```sh
dc exec manager apm setup-token
```

Откройте адрес панели, введите токен, email и пароль администратора длиной от 12 символов. Стандартных логина и пароля нет. Токен предназначен для локального получения и после setup больше не используется. Если администратор уже создан, `setup-token` вернёт `Setup already completed`: входите существующим пользователем.

На странице «Обзор» проверьте связь с Angie и применённую версию. В «Операциях» убедитесь, что начальное применение завершилось успешно. В аккаунте можно включить TOTP; сохраните recovery codes вне сервера.

Сохранение формы означает запись желаемого состояния и постановку задания в очередь. Применение считается завершённым после успешной проверки конфигурации, reload и подтверждения поколения Angie. Не ориентируйтесь только на сообщение «Сохранено».

<a id="proxy"></a>

## 7. Первый прокси-хост и сертификат

### 7.1. Проверить доступность приложения

Адрес backend должен быть доступен именно из окружения Angie:

| Вариант | Пример адреса приложения |
|---|---|
| A: сеть хоста | `127.0.0.1:8080` для приложения на хосте или опубликованного контейнерного порта |
| B: системный Angie | Адрес и порт, доступные с Linux-хоста |
| C: Docker Desktop | `host.docker.internal:8080` для приложения на macOS; имя сервиса для общей Docker-сети |

В варианте A контейнер Angie с host network не получает автоматически DNS-имена сервисов bridge-сети Compose. Не используйте имя контейнера как backend без проверки его разрешения и доступности.

### 7.2. Создать маршрут

1. Откройте «Прокси-хосты» → «Создать».
2. На вкладке «Основное» задайте название, домен `app.example.com`, протокол, адрес и порт приложения.
3. Для первой проверки можно оставить «Без сертификата · только HTTP» на вкладке SSL.
4. Сохраните и дождитесь успешного задания в «Операциях».
5. Проверьте запрос с нужным Host.

Для A/B, где `SERVER_IP` — адрес вашего сервера:

```sh
curl --fail --resolve app.example.com:80:SERVER_IP http://app.example.com/
```

Для C:

```sh
curl --fail -H 'Host: app.example.com' http://127.0.0.1:8088/
```

`SERVER_IP` замените на настоящий адрес. `--resolve` позволяет проверить маршрут до изменения DNS; он не настраивает DNS для браузеров и центра сертификации.

### 7.3. Запросить Let's Encrypt при создании или редактировании

На вкладке SSL выберите «Запросить новый сертификат Let's Encrypt», затем способ проверки, email и согласие с условиями CA.

| Проверка | Что подготовить |
|---|---|
| HTTP-01 | Публичные A/AAAA домена ведут на этот сервер, внешний TCP/80 доступен Angie, challenge не перехватывает другой proxy |
| DNS-01 | Заранее создан и проверен DNS-профиль с правом изменения TXT в нужной зоне; подходит для wildcard |

Ограничения проверок описаны в [документации Let's Encrypt](https://letsencrypt.org/docs/challenge-types/).

Нажмите «Сохранить и запросить сертификат» и следите за «Операциями» и страницей «Сертификаты». Выдача и применение происходят отдельно от сохранения формы. После успешного выпуска проверьте HTTPS; перенаправление HTTP → HTTPS включается параметром «Принудительный HTTPS». Для HTTP/3 дополнительно нужен UDP на HTTPS-порту.

Для серии проб можно использовать отдельный тестовый экземпляр с `APM_ACME_SERVER=https://acme-staging-v02.api.letsencrypt.org/directory`. Сертификаты staging не доверены браузерами; адрес и назначение среды приведены в [документации staging Let's Encrypt](https://letsencrypt.org/docs/staging-environment/). После смены CA пересоздайте контейнеры с актуальным env; для публичного использования запросите сертификат production CA. Реальная выдача через конкретные DNS-провайдеры ещё требует приёмки, см. [матрицу](COMPATIBILITY.md).

Подсказки «?» у параметров объясняют наследование доступа, TLS, лимиты и буферизацию. Для DNS-профилей секреты вводятся отдельно и не возвращаются через API.

<a id="sites"></a>

## 8. Статический сайт и PHP-FPM

### 8.1. Разместить статические файлы

Создайте каталог сайта в хранилище APM. Пример для A/C с `/data` внутри контейнера Angie:

```sh
dc exec --user 0:10001 angie sh -c 'umask 0007; mkdir -p /data/sites/company; printf "%s\n" "APM static site is running" > /data/sites/company/index.html; chown -R 10001:10001 /data/sites/company'
```

Команда записывает демонстрационный `index.html`: используйте новый каталог `company` либо другое свободное имя, не перезаписывайте существующий сайт. В A он соответствует `./data/sites/company`, в C — каталогу внутри named volume.

В B разместите файлы на хосте в `/srv/apm/sites/company`, обеспечив чтение и проход по родительским каталогам worker-пользователю Angie через группу 10001. Например, для нового пустого каталога:

```sh
sudo install -d -o 10001 -g 10001 -m 2750 /srv/apm/sites/company
```

В панели «Статика / PHP» создайте объект: домен `www.example.com`, каталог `company`. Поле каталога принимает имя, а не абсолютный путь. Angie ищет сначала `index.html`, затем `index.php`. Сохраните, дождитесь применения и проверьте сайт запросом с нужным Host, как в предыдущем разделе.

### 8.2. Подключить PHP

PHP-FPM разворачивается отдельно; штатный Compose не содержит PHP-сервиса. До включения PHP подготовьте:

1. FastCGI-адрес FPM, доступный Angie, например `php-fpm:9000` в общей Docker-сети или `127.0.0.1:9000` при работе на одном Linux-хосте.
2. Одинаковые абсолютные пути к скриптам в Angie и FPM. Например, в A/C файл должен быть доступен обоим как `/data/sites/company/index.php`; в B — как `/srv/apm/sites/company/index.php`.
3. Права чтения файлов для процессов FPM и Angie.

В форме сайта укажите FastCGI-адрес в «Адрес PHP-FPM», без `http://` и без пути. Не публикуйте FPM в интернет. Если оставить поле пустым, PHP не исполняется и исходники могут отдаваться как статические файлы. Не размещайте PHP-код до подготовки FPM и успешного применения соответствующей настройки.

Сертификат для страницы «Статика / PHP» сначала запросите или загрузите в разделе «Сертификаты», затем выберите в форме сайта. Этот выбор не создаёт автоматический redirect с HTTP. «Список файлов каталога» используйте для публичного каталога; «Оформленный список файлов» требует доступного модуля fancyindex.

<a id="backup"></a>

## 9. Данные и резервное копирование

### 9.1. Что сохранять

| Объект | Назначение |
|---|---|
| `apm.sqlite3` | Пользователи, ресурсы, операции и состояние |
| `master.key` | Ключ расшифровки секретов БД; без него одной SQLite недостаточно |
| `certificates/`, `acme/`, `bootstrap/` | Сертификаты, ключи и состояние выпуска |
| `revisions/`, `current`, `angie.conf` | Версии и активная конфигурация; активная версия после restore строится заново из желаемого состояния |
| `sites/` | Файлы сайтов, если они хранятся в данных APM |
| `exports/` | Созданные зашифрованные архивы |
| `backup.password` | Локально сохранённый пароль будущих архивов |

Сам каталог данных находится в `./data` для A, в `/srv/apm` для B и в Docker volume для C. `.env` / `.env.existing`, Compose-надстройки и выбранные версии образов сохраняйте отдельно. В B также отдельно резервируйте основной конфиг Angie, включённые файлы, сертификат панели и unit systemd.

Архив APM включает SQLite, `master.key`, сертификаты и обычные файлы данных, в том числе содержимое `sites/`. Он исключает `run/`, `logs/`, `exports/`, `backup.password`, symlink и прежние каталоги восстановления. Внешние bind mounts за пределами данных APM и БД/файлы вашего PHP-приложения требуют собственного резервного копирования.

### 9.2. Задать пароль и сделать копию

Один раз задайте пароль архива, не короче 16 символов:

```sh
dc exec manager apm backup-password
```

Сохраните пароль отдельно от сервера. В интерфейсе администратор может создать и скачать архив через «Импорт / копии». Для согласованной копии перед обновлением используйте офлайн-порядок: в A/C остановите manager, worker и Angie; в B — manager, worker и агент. На время копии не изменяйте файлы сайтов.

Для A/C:

```sh
dc stop worker manager angie
dc run --rm --no-deps manager backup
dc up -d --no-build --wait --wait-timeout 120
```

Для B:

```sh
dc stop worker manager
sudo systemctl stop apm-agent apm-safety-watchdog
dc run --rm --no-deps manager backup
sudo systemctl start apm-agent apm-safety-watchdog
dc up -d --no-build --wait --wait-timeout 120
```

CLI напечатает путь `.../exports/UUID.apm`. Скопируйте файл из контейнера manager или скачайте через UI. Пример с заменой `BACKUP_ID` на напечатанный UUID:

```sh
mkdir -p "$HOME/apm-backups"
chmod 700 "$HOME/apm-backups"
dc cp "manager:${apm_data_path}/exports/BACKUP_ID.apm" "$HOME/apm-backups/"
```

Храните хотя бы одну копию вне сервера: потеря диска не должна уничтожить архив вместе с исходными данными. Проверяйте восстановление на отдельном экземпляре с тем же образом и правильным паролем.

<a id="maintenance"></a>

## 10. Обновление, восстановление и возврат версии

### 10.1. Обновление A/C

Процедура предусматривает остановку сайтов на время обновления. До смены исходников или образов сделайте архив старой версией приложения. Сохраните также предыдущие образы, например под собственным тегом:

```sh
docker tag apm-manager:dev apm-manager:before-update
docker tag apm-angie:dev apm-angie:before-update

dc stop worker manager angie
dc run --rm --no-deps manager backup
```

После успешной копии обновите исходники до выбранной версии, затем:

```sh
dc config --quiet
dc build manager
dc build angie
dc up -d --no-build --wait --wait-timeout 120
```

Если Angie собирался через локальную базу, вместо обычной команды используйте `dc build --build-arg ANGIE_IMAGE=apm-angie-source:1.12.4 angie` с базой, соответствующей новой версии исходников. После обновления проверьте ready, операции, HTTP/HTTPS и важные маршруты. Перед следующим обновлением назначайте новый тег сохранения, чтобы не затереть нужный предыдущий образ.

`scripts/update.sh` выполняет копию и сборку только для обычного Compose A. Он не получает исходники новой версии и не подходит для B/C. Для C всегда сохраняйте `compose.local.yaml` в командах, иначе изменятся сеть и хранилище.

### 10.2. Обновление B

Агент на хосте и контейнеры должны использовать одну версию исходников:

```sh
docker tag apm-manager:dev apm-manager:before-update
dc stop worker manager
sudo systemctl stop apm-agent apm-safety-watchdog
dc run --rm --no-deps manager backup
```

После успешной копии обновите исходники, затем:

```sh
uv sync --frozen --no-dev --no-editable --reinstall-package angie-proxy-manager
dc config --quiet
dc build manager
sudo systemctl restart apm-agent
sudo systemctl enable --now apm-safety-watchdog
dc up -d --no-build --wait --wait-timeout 120
```

Если меняли unit, перед стартом выполните `sudo systemctl daemon-reload`. Обычная остановка агента и APM-контейнеров не останавливает уже работающий системный Angie. Проверьте после обновления и APM-сайты, и прежние виртуальные хосты.

### 10.3. Восстановление из архива

Используйте образ приложения, соответствующий архиву. При переносе на новый сервер сначала подготовьте исходники, env, образы, хранилище и контейнеры выбранного варианта; затем остановите их для restore. Если архив содержит администратора, повторный setup не нужен.

Для A/C:

```sh
dc stop worker manager angie
dc cp "$HOME/apm-backups/BACKUP_ID.apm" "manager:${apm_data_path}/exports/BACKUP_ID.apm"
dc run --rm --no-deps manager restore "${apm_data_path}/exports/BACKUP_ID.apm"
dc up -d --no-build --wait --wait-timeout 120
dc exec manager apm backup-password
```

Для B сначала остановите также системный Angie:

```sh
dc stop worker manager
sudo systemctl stop apm-agent apm-safety-watchdog
sudo systemctl stop angie
dc cp "$HOME/apm-backups/BACKUP_ID.apm" "manager:${apm_data_path}/exports/BACKUP_ID.apm"
dc run --rm --no-deps manager restore "${apm_data_path}/exports/BACKUP_ID.apm"
```

Restore удаляет активную ссылку `current`, чтобы заново сформировать конфигурацию для текущего хоста. В B перед запуском системного Angie нужно восстановить начальные включения, иначе его основной конфиг будет ссылаться на отсутствующие файлы. Из `/opt/apm`, с фактическими путями вашей установки:

```sh
sudo /opt/apm/.venv/bin/python - <<'PY'
import os
from apm.agent import Agent
from apm.config import Settings

os.setgid(10001)
os.umask(0o007)
Agent(Settings(_env_file="/opt/apm/.env.existing")).initialize()
PY

sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf
sudo systemctl start angie
sudo systemctl restart apm-agent
sudo systemctl enable --now apm-safety-watchdog
dc up -d --no-build --wait --wait-timeout 120
dc exec manager apm backup-password
```

В обоих вариантах CLI запросит пароль архива. Restore отзывает прежние сессии, сохраняет прежние данные в `.before-restore-*` внутри каталога данных и ставит новое применение в очередь. Дождитесь его успеха и проверьте сайты. Пароль будущих копий задаётся заново, потому что `backup.password` не входит в архив.

Если восстановление прервалось и остался `.restore-journal.json`, остановите сервисы и разберите сохранённые staging/previous-каталоги локально. Автоматически удалять журнал и повторять restore без проверки не следует.

### 10.4. Возврат предыдущей версии

Возврат состоит из прежних исходников/образов и соответствующей им резервной копии. Запуск старого образа поверх уже мигрировавшей БД не заменяет restore: автоматической обратной миграции нет.

При остановленных сервисах верните прежний checkout и сохранённые теги:

```sh
docker tag apm-manager:before-update apm-manager:dev
docker tag apm-angie:before-update apm-angie:dev
```

Вторая команда нужна только для A/C. В B также верните Python-окружение агента через `uv sync --frozen --no-dev --no-editable` из прежних исходников. Затем выполните restore старого архива по предыдущему подразделу и запускайте с `--no-build`, чтобы не заменить возвращённые образы новой сборкой.

<a id="optional"></a>

## 11. CrowdSec, GeoIP и Docker discovery

Быстрые переходы: [модули и IP клиента](#protection-prerequisites), [CrowdSec / AppSec](#crowdsec), [GeoIP](#geoip), [локальный discovery](#docker-discovery), [Docker на другой машине](#remote-docker).

<a id="protection-prerequisites"></a>

### 11.1. Модули Angie и реальный IP клиента

Полная [таблица «функция → модуль → необходимость PRO»](MODULES.md) показывает зависимости функций APM и отдельно возможности Angie PRO, которые пока не имеют готовых настроек в панели.

Профили защиты создаются администратором и привязываются к прокси-хосту на вкладке «Дополнительно». Для CrowdSec нужны HTTP Lua, LuaJIT, `lua-cjson`, `lua-resty-core` и библиотеки интеграции APM; для GeoIP — HTTP GeoIP2 и `libmaxminddb`. Наличие профиля в панели не устанавливает модули.

В A/C сначала соберите обычные `apm-manager:dev` и `apm-angie:dev`, как в разделе своего варианта. Затем для A используйте:

```sh
dc() { docker compose -f compose.yaml -f compose.extended.yaml "$@"; }
```

Для C:

```sh
dc() { docker compose -f compose.yaml -f compose.local.yaml -f compose.extended.yaml "$@"; }
```

С новой функцией:

```sh
dc config --quiet
dc build angie
dc up -d --no-build --wait --wait-timeout 120
```

Этот профиль собирает `apm-angie-extended:dev` с Lua и GeoIP2. Расширенная сборка и реальные интеграции ещё требуют отдельной приёмки; при ошибке сборки или `Unsupported capability` не считайте защиту подключённой. Сохраняйте все выбранные `-f` при обслуживании. При обновлении сначала пересобирайте обычные manager/Angie из новой версии исходников, затем extended; для возврата сохраняйте также фактически используемый `apm-angie-extended:dev`.

В B модули ставятся на хосте под версию и редакцию системного Angie. Например, для OSS пакеты называются `angie-module-lua` и `angie-module-geoip2`; используйте [инструкцию Angie по модулям](https://en.angie.software/angie/docs/installation/external-modules/) и [GeoIP2](https://en.angie.software/angie/docs/installation/external-modules/geoip2/). Загрузите установленные модули в main-контексте существующего конфига; APM в режиме existing не добавляет `load_module` за администратора.

Для CrowdSec в B дополнительно подготовьте те же файлы, что копирует `deploy/angie/Dockerfile`: `access.lua` и `apm.lua` из `src/apm/integrations/` в `/opt/apm/lua/`, содержимое `crowdsec/lib/` и `resty-http/lib/` — туда же с сохранением структуры каталогов. HTML-шаблоны должны оставаться в `/opt/apm/src/apm/integrations/crowdsec/templates/`. Установите системные Lua-зависимости, обеспечьте чтение worker-пользователю Angie и согласуйте общие `lua_package_path`, `init_by_lua*` и shared dictionaries с существующим конфигом. Даже при другом расположении checkout текущий compiler использует эти абсолютные пути.

Если перед Angie стоит CDN или другой reverse proxy, настройте «Настройки сервера» → `trusted_proxies` только на его реальные CIDR. Без этого GeoIP и CrowdSec будут видеть адрес промежуточного proxy. Доверие к `0.0.0.0/0` или `::/0` позволяет подменять клиентский IP через X-Forwarded-For; произвольный заголовок в curl не является достоверной проверкой географии или блокировки.

<a id="crowdsec"></a>

### 11.2. CrowdSec и AppSec

#### Подготовить Security Engine и bouncer key

APM содержит адаптер bouncer внутри Angie. CrowdSec Security Engine, его LAPI и при необходимости AppSec запускаются отдельно. Для Linux установите Engine по [официальной инструкции CrowdSec](https://docs.crowdsec.net/u/getting_started/installation/linux/); AppSec требует совместимой версии Engine, не ниже 1.6. Самостоятельный nginx-bouncer поверх APM для этой интеграции устанавливать не требуется.

На машине CrowdSec создайте отдельный ключ для APM:

```sh
sudo cscli bouncers add apm-angie
sudo cscli bouncers list
```

Полученный ключ сохраните для поля секрета `api_key`; это ключ bouncer, а не логин machine из `local_api_credentials.yaml`. Команда описана в [справке `cscli bouncers add`](https://docs.crowdsec.net/docs/cscli/cscli_bouncers_add/).

Адреса задаются относительно Angie, потому что именно его Lua-код обращается к защите:

| Размещение CrowdSec | LAPI | AppSec |
|---|---|---|
| На том же Linux-хосте, A/B | `http://127.0.0.1:8080` | `http://127.0.0.1:7422` |
| На другой машине через VPN | `http://10.66.0.30:8080` | `http://10.66.0.30:7422` |
| C, CrowdSec на macOS | Адрес хоста, доступный контейнеру Angie | Аналогично, порт 7422 |

В LAPI проверьте `api.server.listen_uri`, в acquisition AppSec — `listen_addr`. Для удалённого доступа привяжите их к частному/VPN-адресу и разрешите соединения только от Angie. Loopback удалённой машины из Angie недоступен. Не публикуйте 8080/7422 в интернет. Примеры используют IP; для DNS-имён Lua HTTP-клиенту также нужен корректный `resolver` в конфигурации Angie. Системный DNS хоста сам по себе этого не гарантирует. Для C имя `host.docker.internal` требует соответствующей настройки Lua resolver либо замены на проверенный адрес.

#### Подключить LAPI в панели

В «CrowdSec / AppSec» создайте включённый профиль, например `crowdsec-main`:

| Поле | Начальная настройка и смысл |
|---|---|
| `lapi_url` | Адрес LAPI из таблицы, без дополнительного пути |
| `appsec_url` | Адрес AppSec; используется при включённом `appsec` |
| `appsec` | На первом шаге выключить, если AppSec ещё не запущен |
| `observe` | Включить для наблюдения за решениями перед блокировкой |
| `failure_action` | `deny` возвращает 503 при сбое защиты; `allow` пропускает запрос при сбое |
| `captcha_provider` | На первом шаге `off` |
| Секрет `api_key` | Ключ, полученный через `cscli bouncers add` |

Секрет задаётся в «Обновить учётные данные (без чтения)»; повторно показываться он не будет. В прокси-хосте откройте «Дополнительно», выберите этот CrowdSec-профиль, сохраните и дождитесь успешного apply. На одном экземпляре Angie текущая интеграция допускает **один общий CrowdSec-профиль** для всех защищаемых прокси-хостов. Независимые профили с разными LAPI одновременно отклоняются compiler.

`observe` переводит обнаруженные блокировки в наблюдение, но не отменяет `failure_action=deny` при недоступности защиты. Проверяйте и успешные запросы, и выбранное поведение отказа. После проверки отключите `observe`, чтобы решения начали блокировать запросы.

#### Включить AppSec

На машине CrowdSec установите правила по [официальному руководству AppSec](https://docs.crowdsec.net/docs/appsec/quickstart/general_setup/):

```sh
sudo cscli collections install crowdsecurity/appsec-virtual-patching crowdsecurity/appsec-generic-rules
```

Создайте отдельный `/etc/crowdsec/acquis.d/apm-appsec.yaml`. Пример для CrowdSec на том же Linux-хосте:

```yaml
source: appsec
listen_addr: 127.0.0.1:7422
appsec_configs:
  - crowdsecurity/appsec-default
labels:
  type: appsec
```

Для другого размещения измените listener на доступный Angie частный адрес. Параметры acquisition приведены в [справке источника AppSec](https://docs.crowdsec.net/docs/next/log_processor/data_sources/appsec/).

```sh
sudo systemctl restart crowdsec
sudo systemctl status crowdsec --no-pager
sudo cscli appsec-configs list
```

В профиле APM включите `appsec`, проверьте `appsec_url`, затем сохраните. Для защищаемого прокси-хоста `request_buffering` должен быть включён: compiler отклоняет AppSec с выключенной буферизацией. Нечитаемое тело запроса может быть отклонено. Перед рабочим включением проверьте загрузку файлов, крупные тела, HTTP/2–3 и потоковые запросы своего приложения.

При выборе CAPTCHA дополнительно нужны секреты `site_key`, `secret_key` и регистрация домена у соответствующего провайдера. CAPTCHA и полная матрица отказов текущего адаптера ещё не приняты; начинайте с обычной блокировки и отдельного тестового хоста.

#### При необходимости подключить анализ access logs

Приём решений LAPI и проверка AppSec не требуют, чтобы APM сам собирал журналы для CrowdSec. Если нужны поведенческие сценарии по запросам к вашим сайтам, настройте acquisition отдельно. Штатный `logs/access.log` APM имеет собственный JSON-формат и по умолчанию маскирует IP; нельзя просто пометить его `type: nginx` и ожидать корректных решений.

Для совместимого источника можно добавить в «Дополнительно» → «Своя конфигурация Angie» выбранного прокси-хоста отдельный журнал с настоящим IP:

```nginx
access_log /data/logs/crowdsec-access.log combined;
```

Для B используйте `/srv/apm/logs/crowdsec-access.log`. В A путь на хосте — `/opt/apm/data/logs/crowdsec-access.log`, если checkout находится в `/opt/apm`. Параметры `access_log` на уровне server заменяют наследование HTTP-журналов для этого хоста; при необходимости сохраните нужные штатные журналы отдельными директивами. У нового файла должна быть собственная ротация. Передайте CrowdSec только каталог нужных логов с доступом на чтение; весь каталог данных APM для этого не нужен.

Пример `/etc/crowdsec/acquis.d/apm-access.yaml` для CrowdSec на хосте варианта A:

```yaml
source: file
filenames:
  - /opt/apm/data/logs/crowdsec-access.log
labels:
  type: nginx
```

В B измените путь, в C организуйте чтение из named volume отдельным контейнером или доставку логов. Если CrowdSec находится на другой машине, доставляйте журнал или используйте отдельный log processor; доступ к LAPI не передаёт ему файлы автоматически. Источник файлов описан в [документации acquisition](https://docs.crowdsec.net/docs/next/log_processor/data_sources/file/).

```sh
sudo cscli collections install crowdsecurity/nginx
sudo systemctl restart crowdsec
sudo cscli metrics
```

#### Проверить интеграцию

Убедитесь, что у bouncer появляются обращения в `cscli bouncers list`, а обычные запросы к тестовому хосту доходят до приложения. Для проверки решения используйте IP отдельного тестового клиента, с которого придёт реальный запрос, сохраняя доступ к панели с другого адреса:

```sh
sudo cscli decisions add --ip TEST_CLIENT_IP --duration 2m --type ban
sudo cscli decisions list
```

Замените `TEST_CLIENT_IP` реальным адресом тестового клиента. При выключенном `observe` ожидается блокировка запроса; при включённом — пропуск при подтверждённом решении LAPI. Сообщения наблюдения имеют уровень `notice`, тогда как стандартный error log APM настроен на `warn`. Чтобы видеть их на тестовом хосте, временно добавьте в его дополнительные директивы `error_log /data/logs/error.log notice;` (в B — путь `/srv/apm/logs/error.log`) и примените конфигурацию. Затем удалите тестовое решение:

```sh
sudo cscli decisions delete --ip TEST_CLIENT_IP
```

Флаги приведены в [справке решений CrowdSec](https://docs.crowdsec.net/docs/cscli/cscli_decisions_add/). Для AppSec дополнительно выполните пробный запрос по [тестовому пути из руководства CrowdSec](https://docs.crowdsec.net/docs/appsec/quickstart/general_setup/#testing-detection) и проверьте `cscli alerts list`: одно присутствие правил не подтверждает прохождение запросов через AppSec.

<a id="geoip"></a>

### 11.3. GeoIP: базы MaxMind и политика доступа

Убедитесь, что доступен HTTP GeoIP2 по разделу 11.1. APM использует бинарные MMDB `GeoLite2-Country` и `GeoLite2-ASN`; устанавливать базы на компьютер с браузером не нужно. Загрузку выполняет worker, а lookup — Angie.

#### Получить данные доступа и загрузить MMDB

1. Создайте аккаунт MaxMind с доступом к GeoLite2 и license key для загрузок. Условия доступа и обновления приведены в [документации MaxMind](https://dev.maxmind.com/geoip/updating-databases/).
2. В панели «Правила GeoIP» создайте включённый профиль. В «Обновить учётные данные (без чтения)» задайте `account_id` и `license_key`. Это учётные данные MaxMind, не API-ключ CrowdSec.
3. Сохраните профиль, пока не привязывая его к хосту. Нажмите «Обновить MMDB» в строке профиля.
4. Дождитесь успеха операции `geoip.update` и последующего apply в «Операциях». Только после этого привязывайте политику к прокси-хосту.

Worker должен иметь DNS и исходящий HTTPS-доступ к `download.maxmind.com` и хостам перенаправления загрузок. Он скачивает обе базы, проверяет структуру и сохраняет их в `APM_DATA_DIR/geoip/<sha256>/`. `database_version` заполняется сервисом. Одна успешная загрузка обновляет версию **у всех GeoIP-профилей**: текущий compiler требует единую версию баз у используемых политик.

Без загруженных баз привязка политики завершится ошибкой `Update the GeoIP databases before using a geography policy`, а прежняя рабочая конфигурация сохранится. В этой версии нет встроенного расписания загрузки MMDB: обновляйте базы кнопкой регулярно и проверяйте результат. Задание также доступно через защищённый API `POST /api/v1/resources/geo-policies/{id}/update-database` с обычной авторизацией и CSRF.

#### Настроить правило

| Поле | Значение |
|---|---|
| `countries` | Коды стран ISO из двух заглавных букв, например `RU`, `KZ`, по одному на строке |
| `asns` | Номера автономных систем, например `13335`, без префикса `AS`, по одному на строке |
| `mode=deny` | Запрещает совпавшую страну или ASN; остальные адреса разрешаются с учётом исключений |
| `mode=allow` | Разрешает совпавшую страну или ASN; остальные адреса запрещаются с учётом исключений |
| `allow_private` | Разрешает предусмотренные compiler локальные/частные диапазоны независимо от географического правила |
| `allow_unknown` | Разрешает пустой результат определения страны; при заданных ASN их проверка продолжает участвовать в результате |

`allow_private` по умолчанию включён и охватывает `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1`, `fc00::/7`. `allow_unknown` также по умолчанию включён. При совместном списке стран и ASN в режиме allow достаточно совпадения любого из них; в режиме deny блокирует любое совпадение, если не сработало разрешение частного диапазона.

Пример ограниченной политики: `mode=allow`, `countries=RU,KZ`, пустые `asns`, `allow_unknown=false`. Решите отдельно, нужно ли оставлять `allow_private=true`: запросы из локальной сети или VPN могут пройти независимо от страны. Значения в текстовом поле стран вводите отдельными строками либо через запятую.

Откройте прокси-хост → «Дополнительно» → «Правила GeoIP», выберите профиль, сохраните и дождитесь apply. Проверьте запросы с разрешённого и запрещённого публичного IP; ожидаемый отказ — HTTP 403. Локальный curl не доказывает действие страны, если частные адреса разрешены. Для CDN сначала настройте реальный IP клиента. Сохраните доступ к панели для исправления политики.

GeoIP и реальное обновление MMDB текущей сборки ещё требуют сетевой приёмки. Успех загрузки подтверждает наличие баз, но не корректность всех выбранных правил для вашего трафика.

<a id="docker-discovery"></a>

### 11.4. Docker discovery на том же сервере

По умолчанию выключен. Задайте в env своего варианта разрешённые сети и доменные зоны, например:

```dotenv
APM_DISCOVERY_ENABLED=true
APM_DISCOVERY_NETWORKS='["apps"]'
APM_DISCOVERY_DOMAINS='["example.com"]'
APM_DISCOVERY_ACME_TERMS_AGREED=true
APM_ACME_EMAIL=admin@example.com
```

Для B дополнительно включите сервис шлюза:

```sh
dc --profile discovery up -d --no-build
```

При дальнейшем обслуживании B сохраняйте этот профиль. Для A/C достаточно `dc up -d --no-build`. В штатном A/C `docker-gateway` запускается и монтирует Docker socket даже при выключенном discovery; в B он включается отдельным профилем. Менеджер и worker не получают socket напрямую.

Labels `apm.*` и поля DNS-профилей описаны в [README](../README.md#docker-labels). Discovery требует явно заданного порта и IPv4 в разрешённой сети. Доступность обнаруженного IP проверяйте из окружения Angie.

<a id="remote-docker"></a>

### 11.5. Docker discovery с другой машины

#### Схема и ограничения текущей реализации

`APM_DOCKER_URL` задаёт один HTTP(S)-endpoint Docker API для worker. Он читает контейнеры и поток событий через HTTP-клиент; `DOCKER_HOST`, Docker context и адрес `ssh://` не подключают discovery. Отдельных настроек клиентских TLS-сертификатов и SSH-туннеля в APM нет. Практический вариант ниже — штатный шлюз APM на Docker-хосте и доступ к нему по уже настроенной VPN.

Пример адресов: сервер APM/Angie `10.66.0.10`, удалённый Linux Docker-хост `10.66.0.20`, сеть контейнеров `apps` с IPv4-подсетью `172.30.40.0/24`. Замените адреса на свои; подсети не должны пересекаться с сетями APM, VPN и других Docker-хостов.

| Соединение | Что должно быть доступно |
|---|---|
| worker → удалённый gateway | `10.66.0.20:2375` по VPN: метаданные и `/events` |
| Angie → приложение | Например, `172.30.40.5:8080` по маршруту через удалённый Docker-хост |

Первое соединение не создаёт второе. Discovery использует `NetworkSettings.Networks[apm.network].IPAddress` и **внутренний** `apm.port`. Он не подставляет VPN-адрес Docker-хоста или опубликованный порт из `ports:`. Labels для переопределения адреса backend, агрегация нескольких Docker Engine и Swarm service discovery сейчас не предусмотрены.

#### Запустить gateway на удалённом Docker-хосте

Передайте на него ту же версию исходников APM и соберите образ. Из каталога полученных исходников на **удалённой машине**:

```sh
docker build -f Dockerfile -t apm-manager:dev .
```

Создайте там `compose.discovery-gateway.yaml`:

```yaml
name: apm-remote-discovery
services:
  docker-gateway:
    image: apm-manager:dev
    command: [gateway, --host, "10.66.0.20", --port, "2375"]
    network_mode: host
    user: "0:0"
    restart: unless-stopped
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: [/tmp]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

VPN-адрес должен существовать на этой Linux-машине, а порт быть свободен. Шлюз привязан только к указанному адресу; разрешите вход на 2375 только от сервера APM через VPN и не маршрутизируйте этот доступ из внешних сетей.

```sh
docker compose -f compose.discovery-gateway.yaml config --quiet
docker compose -f compose.discovery-gateway.yaml up -d --no-build
docker compose -f compose.discovery-gateway.yaml logs --tail=100
```

Это порт шлюза APM, а не открытый Docker daemon: включать TCP-listener Engine не нужно. Gateway разрешает только GET `/_ping`, `/version`, `/containers/json`, `/events` и их версионированные варианты. HTTP-авторизации в самом gateway нет; изоляция доступа обеспечивается VPN и сетевыми правилами. Монтирование Docker socket с `:ro` само по себе не запрещает управляющие API-вызовы — их отсекает allowlist приложения. Общие варианты защиты Docker API описаны в [документации Docker](https://docs.docker.com/engine/security/protect-access/).

#### Настроить маршрутизацию к приложениям

Для внутреннего адреса контейнера на удалённом bridge обычно недостаточно доступности Docker-хоста. До включения discovery:

1. Настройте маршрут из окружения Angie к `172.30.40.0/24` через `10.66.0.20`; для VPN также включите эту подсеть в маршруты/AllowedIPs соответствующего peer.
2. На Docker-хосте настройте IP forwarding, доступ с VPN к нужным портам контейнеров и обратный маршрут. Docker firewall тоже должен разрешать такое подключение: произвольная bridge-сеть по умолчанию не предоставляет удалённый доступ к IP контейнеров.
3. Выберите и настройте подходящий режим direct routing по [документации Docker о публикации портов и маршрутизации](https://docs.docker.com/engine/network/port-publishing/#direct-routing). Один статический маршрут без настройки forwarding/firewall недостаточен. Публикация порта может участвовать в правилах доступа Docker, но discovery всё равно выбирает внутренний адрес и порт.
4. Проверьте конкретный `container-IP:apm.port` из Angie, включая ответ приложения. Для A/B это сеть Linux-хоста; для C проверять нужно из контейнера Angie.

Для C можно проверить пример так, заменив адрес и порт фактическими:

```sh
dc exec angie curl --fail --connect-timeout 5 http://172.30.40.5:8080/
```

Для A/B тот же curl выполняется на Linux-хосте. Если отдельная маршрутизация контейнерной сети невозможна, создайте ручной прокси-хост на `10.66.0.20:ОПУБЛИКОВАННЫЙ_ПОРТ` и уберите `apm.enable=true` у этого приложения. Это поддерживаемый способ использовать опубликованный порт без автоматической подмены адресов discovery.

#### Разметить удалённое приложение и подключить APM

Пример labels в Compose приложения на удалённой машине:

```yaml
services:
  app:
    labels:
      apm.enable: "true"
      apm.host: app.example.com
      apm.network: apps
      apm.port: "8080"
      apm.scheme: http
      apm.tls: "off"
    networks: [apps]
networks:
  apps:
    external: true
    name: apps
```

Это фрагмент для существующего сервиса: сохраните его образ, mounts и остальные настройки. Сеть `apps` должна уже существовать и быть настроена для нужной маршрутизации. `apm.network` — её фактическое имя в Engine, а не только имя ключа Compose с автоматически добавленным префиксом проекта. Для нескольких реплик одинакового домена TLS, scheme и DNS-профиль должны совпадать.

На **сервере APM** измените `.env` или `.env.existing`:

```dotenv
APM_DOCKER_URL=http://10.66.0.20:2375
APM_DISCOVERY_ENABLED=true
APM_DISCOVERY_NETWORKS='["apps"]'
APM_DISCOVERY_DOMAINS='["example.com"]'
```

Для TLS добавьте настройки согласия/email из раздела 11.4, выберите `apm.tls: http` или `dns` и подготовьте соответствующую проверку домена. DNS сайта должен указывать на Angie, не на Docker-хост.

```sh
dc up -d --no-build manager worker
```

Пересоздание manager/worker применяет новые env. Для B локальный профиль `discovery` при удалённом gateway не нужен. В A/C локальный gateway остаётся зависимостью worker в штатном Compose, но при изменённом `APM_DOCKER_URL` запросы идут к удалённому адресу.

Проверьте API из контейнера worker:

```sh
dc exec -T worker python - <<'PY'
import httpx
from apm.config import Settings

with httpx.Client(base_url=Settings().docker_url, timeout=10, trust_env=False) as client:
    for path in ("/_ping", "/version", "/containers/json?all=1"):
        response = client.get(path)
        response.raise_for_status()
        print(path, response.status_code)
    assert client.get("/containers/not-an-id/json").status_code == 403
    with client.stream("GET", "/events") as response:
        response.raise_for_status()
        print("/events", response.status_code)
PY
```

Поток `/events` должен проходить без буферизации или обрезания внешним reverse proxy. Worker также делает полное сопоставление примерно раз в минуту. Для внеочередного запуска есть защищённый API `POST /api/v1/operations/reconcile`, требующий авторизации администратора и CSRF. Проверьте «Операции», появление upstream и прокси-хоста с источником `docker`, затем выполните реальный запрос через Angie. Изменение/остановка удалённого контейнера должно отражаться после события или полного сопоставления.

Один экземпляр APM использует один endpoint. При переключении с локального Docker на удалённый прежние маршруты с источником `docker`, отсутствующие в новом списке, выключаются при сопоставлении. Ручные объекты не перезаписываются. Поэтому переход endpoint планируйте как смену источника обнаружения. Отказ API не создаёт маршрутизацию к приложениям и не подтверждает её исправность; полный удалённый сценарий в текущей сборке ещё требует отдельной сетевой приёмки.

### 11.6. PRO и аналитика

- Для PRO нужен лицензированный совместимый образ и собственная приёмка возможностей; лицензия в проект не входит. Базовый образ выбирается через `APM_ANGIE_IMAGE` в варианте A. `compose.extended.yaml` пересобирает бинарный файл из OSS-исходников: для сохранения PRO используйте совместимые модули в PRO-образе, как описано в [таблице модулей](MODULES.md).
- `compose.analytics.yaml` рассчитан на bind mount `./data` варианта A. Не подключайте его к C без замены mounts на используемый named volume, а к B — без настройки путей его хранилища. Сам профиль GoAccess пока требует отдельной проверки.
- Access logs включаются в «Настройках сервера». Описание OIDC, recovery-команд и API находится в [README](../README.md) и [архитектуре](ARCHITECTURE.md).

<a id="troubleshooting"></a>

## 12. Диагностика и остановка

### 12.1. Основные команды

```sh
dc ps -a
dc logs --tail=200 manager worker
curl --fail http://127.0.0.1:8181/health/live
curl --fail http://127.0.0.1:8181/health/ready
```

В A/C смотрите `dc logs --tail=200 angie`. В B:

```sh
sudo systemctl status angie apm-agent --no-pager
sudo journalctl -u apm-agent -n 100 --no-pager
sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf
curl --fail http://127.0.0.1:18081/status/angie
```

Перед передачей логов исключите секреты, приватные ключи и содержимое сгенерированных конфигураций. `docker compose config` без `--quiet` может раскрыть переменные окружения; для проверки синтаксиса используйте `config --quiet`.

### 12.2. Типовые проблемы

| Симптом | Что проверить |
|---|---|
| `port is already allocated` / `address already in use` | Listener хоста и другие Compose-проекты; не останавливайте чужой сервис без выяснения его назначения |
| Ошибка неизвестного `!reset` | Обновите Compose plugin; проверяйте именно командой `docker compose` |
| Не собирается Angie из реестра | Доступ к `docker.angie.software`; для локального теста используйте сборку из закреплённого исходного архива |
| Панель не открывается, backend жив | Angie, listener 81 или внешний HTTPS в B, firewall, правильность `APM_BACKEND_URL` у worker и агента |
| Вход не сохраняется | Открывайте HTTPS при `APM_COOKIE_SECURE=true`; проверяйте Host с портом у внешнего proxy. Отключение Secure cookie допустимо только для отдельного HTTP-стенда разработки |
| `/health/ready` → 503 | Работает ли worker, доступен ли Unix socket, одинаковы ли путь данных и группа; в B запущен ли `apm-agent` |
| `Permission denied` | UID/GID 10001, права родительских каталогов, доступ worker Angie; на хостах с SELinux также его контексты и audit log |
| Форма сохранена, маршрут не изменился | Задание в «Операциях», журнал ошибки apply и применённая версия; очередь могла остановиться после неудачного отката |
| В B успешно применилось, но открывается прежний сайт | Повторяющиеся домены/listener и предупреждения Angie о конфликте `server_name` |
| HTTP 502 | Адрес/порт backend из окружения Angie, DNS контейнеров, выбранный HTTP/HTTPS/FastCGI-протокол |
| PHP сообщает `Primary script unknown` | Одинаковый абсолютный путь скрипта у Angie и FPM, mounts и права чтения |
| Сайт с выбранным сертификатом возвращает 503 | Состояние сертификата, результат выпуска/загрузки и последующего применения |
| Не проходит HTTP-01 | Публичные A/AAAA, внешний TCP/80 и маршрут challenge; localhost:8088 не заменяет внешний порт 80 |
| Не проходит DNS-01 | Зона, права изменения TXT, учётные данные профиля, время распространения и задание очистки |
| Опция модуля отклонена | Возможности используемой сборки Angie; включение переключателя не устанавливает модуль |

Для восстановления доступа к аккаунту:

```sh
dc exec manager apm reset-password admin@example.com --reset-mfa
```

Команда запросит новый пароль и отзовёт сессии пользователя. Уберите `--reset-mfa`, если сброс TOTP не требуется. Для возобновления apply после локального ремонта и разбора журнала применяется `dc exec manager apm resume-applies`; команда откажет при незавершённом apply-журнале. Не удаляйте его ради обхода проверки.

### 12.3. Остановка и повторный запуск

```sh
dc stop
dc up -d --no-build --wait --wait-timeout 120
```

`dc down` удаляет контейнеры и сеть выбранного проекта. Bind mount A/B и named volume C при обычном `down` сохраняются. `down --volumes` удаляет именованные тома, в том числе данные C; не используйте эту опцию для обычной остановки. Смена имени Compose-проекта в C создаёт другое хранилище и может выглядеть как потеря данных.

В B остановка Compose не останавливает системный Angie: последний применённый конфиг продолжает обслуживать сайты. Чтобы полностью отключить интеграцию APM, сначала остановите worker, удалите две строки APM include и виртуальный хост панели из основной конфигурации, выполните `angie -t` и reload, затем остановите агент и Compose. Сохраните данные и архивы.

## 13. Выпуск сертификата для APM при установке с существущем Angie

Для этого выпусти отдельный сертификат **на хосте, где работает Angie**, через Certbot. Затем укажи его файлы в [шаблоне панели](/Users/levich/Documents/work/APM/deploy/existing/http.conf.example:15).

Ниже замени `apm.example.com` на домен панели, а `admin@example.com` — на свой email.

1. **Подготовь домен.**

   DNS-запись `A` должна указывать на сервер. Если есть `AAAA`, IPv6 тоже должен вести на него. Для проверки HTTP-01 нужен доступ из интернета к порту **80**, для панели — **443**. [Условия проверки Let’s Encrypt](https://letsencrypt.org/docs/challenge-types/#http-01-challenge).

2. **Установи Certbot и создай каталог проверки:**

   ```bash
   sudo apt-get update
   sudo apt-get install -y certbot
   sudo install -d -m 755 /var/www/letsencrypt
   ```

3. **Добавь HTTP-блок в существующий `http {}` Angie:**

   ```nginx
   server {
       listen 80;
       server_name apm.example.com;

       location ^~ /.well-known/acme-challenge/ {
           root /var/www/letsencrypt;
           default_type text/plain;
           try_files $uri =404;
       }

       location / {
           return 404;
       }
   }
   ```

   HTTPS-блок панели добавляй после выпуска сертификата: иначе проверка конфигурации завершится ошибкой из-за отсутствующих PEM-файлов.

   Проверь конфигурацию и выполни reload:

   ```bash
   sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf \
     && sudo systemctl reload angie
   ```

4. **Выпусти сертификат:**

   ```bash
   sudo certbot certonly \
     --webroot -w /var/www/letsencrypt \
     --cert-name apm.example.com \
     -d apm.example.com \
     --email admin@example.com \
     --agree-tos \
     --deploy-hook '/usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf && systemctl reload angie'
   ```

   Certbot разместит проверочный файл в webroot. Сохранённый `deploy-hook` будет проверять и перечитывать конфигурацию Angie после успешного продления. [Документация Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot).

5. **Укажи полученные файлы в HTTPS-блоке панели:**

   ```nginx
   server_name apm.example.com;

   ssl_certificate /etc/letsencrypt/live/apm.example.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/apm.example.com/privkey.pem;
   ```

   Используй эти пути напрямую. В `.env.existing` задай:

   ```dotenv
   APM_PUBLIC_URL=https://apm.example.com
   APM_COOKIE_SECURE=true
   ```

   После добавления HTTPS-блока повтори проверку конфигурации и reload из шага 3.

6. **Включи автоматическое продление и проверь его:**

   ```bash
   sudo systemctl enable --now certbot.timer
   sudo certbot renew --cert-name apm.example.com --dry-run --run-deploy-hooks
   ```

   HTTP-блок и каталог `/var/www/letsencrypt` сохрани для следующих продлений. Таймер входит в [Debian-пакет Certbot](https://packages.debian.org/trixie/all/certbot/filelist).
