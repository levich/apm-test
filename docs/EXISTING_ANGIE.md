# Контейнер APM с существующим Angie

Этот вариант предназначен для Linux-сервера, на котором Angie уже установлен и обслуживает сайты. Manager и worker запускаются из одного образа APM в Docker, агент APM работает на хосте рядом с Angie и использует его бинарный файл, основной конфиг и PID для проверки и reload. Второй Angie не запускается.

APM генерирует свои HTTP/stream-включения. Основной конфиг, прежние виртуальные хосты, модули, `user`, `pid`, `events` и настройки процессов остаются под управлением администратора. Существующие сайты не появляются в панели автоматически: переносите их отдельно, исключая дублирование доменов и портов.

## Требования

- Linux, rootful Docker Engine, Compose v2, Python 3.13 и uv на хосте; системный Angie с API и stream-модулем. Сетевой сценарий проверяется на OSS 1.12.4, PRO требует отдельной приёмки.
- Один хост и общая файловая система: одинаковый **абсолютный** `APM_DATA_DIR` у агента, manager, worker и Angie, без symlink в пути. В примерах это `/srv/apm`. SQLite и Unix socket должны находиться на локальной файловой системе.
- Агент работает в пространстве процессов и файлов Angie и имеет право посылать ему сигналы. HTTP API Angie не позволяет записывать конфиг и делать reload, поэтому локальный агент обязателен.
- Примеры предполагают checkout в `/opt/apm`, сервис `angie.service` и worker-пользователя `angie`. Измените пути и имя пользователя для своей установки.

`compose.existing.yaml` — самостоятельный файл; не объединяйте его с `compose.yaml` или `compose.extended.yaml`. Он не содержит сервиса `angie` и host network. Backend панели публикуется на `127.0.0.1:8181`; порт должен быть свободен. Внешний HTTPS обслуживает установленный Angie.

## 1. Подготовить конфигурацию и данные

Сохраните копию конфигурации Angie, подключённых файлов и сертификатов. Из `/opt/apm`:

```sh
cp .env.existing.example .env.existing
chmod 600 .env.existing
# Отредактируйте .env.existing перед сборкой и запуском.
uv sync --frozen --no-dev --no-editable
docker compose --env-file .env.existing -f compose.existing.yaml build manager
docker compose --env-file .env.existing -f compose.existing.yaml run --rm --no-deps init
```

Проверьте значения в `.env.existing`:

| Переменная | Назначение |
|---|---|
| `APM_ANGIE_MODE=existing` | Генерация включений для существующего сервера |
| `APM_DATA_DIR=/srv/apm` | Один абсолютный путь на хосте и в контейнерах; отдельный каталог APM |
| `APM_ANGIE_BINARY=/usr/sbin/angie` | Бинарный файл работающего сервера |
| `APM_ANGIE_CONFIG=/etc/angie/angie.conf` | Существующий основной конфиг |
| `APM_ANGIE_PREFIX=/etc/angie` | Prefix сервера: его `-p`, либо `--prefix` из `angie -V` |
| `APM_ANGIE_STATUS_URL` | Локальный API этого экземпляра; по умолчанию `http://127.0.0.1:18081/status/angie` |
| `APM_PUBLIC_URL=https://apm.example.com` | Внешний HTTPS-адрес панели |
| `APM_COOKIE_SECURE=true` | Secure cookies при доступе по HTTPS |

Пути конфига и prefix должны быть абсолютными. Сверьте их с `systemctl cat angie` и `angie -V`, включая `-c`, `-p` и PID. Если сервис передаёт `pid` через `-g`, перенесите эквивалентную директиву в основной конфиг, чтобы агент использовал тот же PID. Пример prefix необходимо проверить для своей сборки.

Init создаёт каталоги данных для UID/GID `10001:10001`. Worker-пользователю Angie нужны чтение PEM/htpasswd и доступ к webroot через группу 10001. Эта группа также имеет доступ к управляющему Unix socket; добавляйте только доверенные сервисные учётные записи.

```sh
# Если группа GID 10001 уже есть, используется она.
getent group 10001 || sudo groupadd --gid 10001 apm
sudo usermod --append --groups 10001 angie
```

## 2. Установить агент и создать начальные включения

Измените `/opt/apm` и имя Angie-сервиса в шаблоне, если они отличаются:

```sh
sudo install -m 644 deploy/existing/apm-agent.service /etc/systemd/system/apm-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now apm-agent
sudo systemctl status apm-agent --no-pager
```

`ExecStartPre` выполняет `apm bootstrap-agent`: создаёт начальную версию с пустыми включениями, сохраняя основной конфиг и не выполняя reload. Повторный запуск сохраняет текущую версию; отсутствие основного конфига считается ошибкой. Агент слушает `/srv/apm/run/agent.sock`, TCP-порт не открывается.

В systemd заданы `Group=10001` и `UMask=0007` для подключения worker к сокету. EnvironmentFile читает `.env.existing`; при изменении настроек перезапустите агент и пересоздайте контейнеры с тем же env-файлом.

## 3. Подключить включения и HTTPS панели

В **основной** файл `APM_ANGIE_CONFIG` добавьте по одной отдельной строке include в соответствующие существующие блоки:

```nginx
http {
    # Существующие директивы, include и виртуальные хосты остаются здесь.
    include /srv/apm/current/http.conf;
}

stream {
    # Существующие TCP/UDP-маршруты остаются здесь.
    include /srv/apm/current/stream.conf;
}
```

Не создавайте второй блок `http` или `stream`, если он уже есть. Для stream при необходимости загрузите установленный совместимый динамический модуль в main-контексте. Обе строки должны находиться непосредственно в основном конфиге, каждая на отдельной строке, с абсолютным путём, без glob. Двойные кавычки вокруг пути допустимы. Это позволяет проверять кандидата со всей конфигурацией без переключения работающей версии. Относительные include сохраняют исходную базовую директорию.

В `http` также добавьте локальный API и HTTPS-виртуальный хост панели из [http.conf.example](../deploy/existing/http.conf.example). Укажите свой домен и существующий сертификат. [stream.conf.example](../deploy/existing/stream.conf.example) показывает stream-включение. Шаблоны — фрагменты для ручного добавления: строка APM include должна оставаться непосредственно в основном файле.

Если у сервера уже есть локальный API, укажите его в `APM_ANGIE_STATUS_URL`, сохранив единственный listener. API должен возвращать `generation` нужного экземпляра. Новый API оставляйте на loopback. Для HTTPS панели используйте сертификат вне ресурсов APM, чтобы доступ к панели не зависел от первой операции применения.

Проверьте и перечитайте конфигурацию с prefix из env-файла; ниже значения из примера:

```sh
sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf
sudo systemctl reload angie
curl --fail http://127.0.0.1:18081/status/angie
```

## 4. Запустить контейнеры

```sh
docker compose --env-file .env.existing -f compose.existing.yaml config --quiet
docker compose --env-file .env.existing -f compose.existing.yaml up -d
docker compose --env-file .env.existing -f compose.existing.yaml exec manager apm setup-token
```

Откройте `APM_PUBLIC_URL`, введите токен и создайте администратора. Стандартного пароля нет. Страница «Операции» показывает проверку и фактическое применение. После создания тестового маршрута проверьте его и прежние сайты.

Для discovery задайте `APM_DISCOVERY_ENABLED=true`, разрешённые сети/домены и включите профиль:

```sh
docker compose --env-file .env.existing -f compose.existing.yaml --profile discovery up -d
```

При выключенном discovery шлюз не запускается и Docker socket не монтируется. Адреса `127.0.0.1` в маршрутах относятся к хосту Angie; backend должен быть доступен оттуда.

## Применение и ограничения

Агент проверяет копию основного конфига рядом с оригиналом, заменяя две строки APM include путями кандидата. `angie -t` проверяет существующие сайты и новый комплект APM. При ошибке current остаётся прежним, reload не выполняется. После успешной проверки агент атомарно переключает current, отправляет reload и ждёт роста generation. При неподтверждённом reload он возвращает прежнюю версию APM. Основной конфиг остаётся неизменным. Не редактируйте конфиг и не выполняйте сторонние reload одновременно с применением APM.

APM не добавляет admin/status listeners и catch-all `default_server`: их настраивает администратор. Согласуйте домены и порты APM с существующими sites: одинаковые имена на одном listener могут быть приняты Angie с предупреждением и выбрать прежний server. Настройки процессов, `worker_connections`, загрузка модулей, общий MIME include и обработка неизвестных доменов остаются в основном конфиге. `quic_bpf` через runtime APM в этом режиме отклоняется; настраивайте его на хосте. HTTP/stream snippets и расширения уровня контекста, например Lua/CrowdSec, требуют согласования с конфигурацией хоста. Для CrowdSec понадобятся Lua-файлы и модули из штатного образа APM Angie.

Агент использует бинарный файл и модули хоста: `APM_ANGIE_IMAGE` и extended overlay здесь не используются. Для Angie в стороннем контейнере нужен агент в том же пространстве процессов/файлов, общая группа и одинаковый путь данных; этот профиль рассчитан на системный Angie на том же Linux-хосте. Удалённое управление другим сервером через TCP API этим профилем не предоставляется.

Политика логов хоста сохраняется; APM access logs относятся к его виртуальным хостам. Данные APM и конфигурацию хоста резервируйте отдельно: архив APM не содержит `/etc/angie` и внешние сертификаты панели.

## Обновление, восстановление и отключение

Обновляйте код агента и образ контейнеров до одной версии. `scripts/update.sh` предназначен для штатного Compose; здесь используйте явные команды. До первой копии задайте пароль командой `exec manager apm backup-password` с теми же Compose-флагами.

```sh
docker compose --env-file .env.existing -f compose.existing.yaml stop worker manager
sudo systemctl stop apm-agent
docker compose --env-file .env.existing -f compose.existing.yaml run --rm --no-deps manager backup
# Обновите checkout только после успешной копии.
uv sync --frozen --no-dev --no-editable
docker compose --env-file .env.existing -f compose.existing.yaml build manager
sudo systemctl start apm-agent
docker compose --env-file .env.existing -f compose.existing.yaml up -d
```

При restore остановите manager, worker, агент и сам Angie, чтобы current и PEM не менялись под работающим сервером. Выполните `run --rm --no-deps manager restore /srv/apm/exports/BACKUP_ID.apm` с теми же Compose-флагами. Затем запустите Angie, агент и контейнеры; снова задайте пароль будущих копий. Возврат внешней конфигурации остаётся отдельной операцией администратора.

Для отключения остановите worker, удалите две строки include APM и виртуальный хост панели из основного конфига, проверьте `angie -t` и выполните reload, затем остановите агент и Compose. Сохраните данные для восстановления.

Принцип включений описан в [документации Angie](https://angie.software/angie/docs/configuration/configfile/); подтверждение reload использует [generation локального API](https://angie.software/angie/docs/configuration/modules/http/http_api/).
