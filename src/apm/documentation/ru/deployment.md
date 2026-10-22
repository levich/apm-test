# Установка и Compose

## Выбор установки

- `compose.yaml`: Linux, собственный Angie в host network; нужны Docker Engine и Compose v2, свободные TCP 80/81/443/8181/18081 и UDP 443 для HTTP/3.
- `compose.yaml` + `compose.local.yaml`: локальный Docker Desktop, отдельный volume; панель https://localhost:81, HTTP localhost:8088, TLS localhost:8443. Backend приложения на macOS: host.docker.internal.
- `compose.existing.yaml`: самостоятельный профиль для уже установленного Angie. Второй сервер Angie не запускается; нужен локальный Unix-агент на хосте.
- `compose.extended.yaml`: расширенная сборка с дополнительными модулями; совместимость и фактическую поддержку проверяйте в capabilities.
- `compose.analytics.yaml`: необязательный GoAccess. Runtime должен включать access_logs и analytics.

## Первый запуск managed

```sh
cp .env.example .env
# Укажите APM_PUBLIC_URL и прочие параметры.
docker compose build manager
docker compose build angie
docker compose up -d
docker compose exec manager apm setup-token
```

Откройте HTTPS-панель, введите локально полученный одноразовый токен, создайте администратора с паролем от 12 символов. Bootstrap-сертификат самоподписанный. Сначала добавьте backend, DNS-профиль/сертификат при необходимости, затем прокси-хост. Проверьте «Операции». Для локального запуска добавляйте `-f compose.yaml -f compose.local.yaml` ко всем командам Compose.

## Существующий Angie

Подготовьте .env.existing из .env.existing.example. У manager, worker и хостового агента должны совпадать абсолютный APM_DATA_DIR, пути бинарного файла, root config и prefix. Установите локальный агент с правом angie -t и reload; HTTP API Angie без агента недостаточно. Агент должен работать в том же сетевом окружении, что и Angie.

В существующем root config добавьте include ровно по контексту:

```nginx
http {
    include /srv/apm/current/http.conf;
}
stream {
    include /srv/apm/current/stream.conf;
}
```

APM не заменяет основной конфиг и прежние virtual hosts. Настройте отдельный HTTPS virtual host панели, проксирующий manager на 127.0.0.1:8181; status API и Unix-сокет остаются локальными. Настройки процесса и глобальные default listeners задаются владельцем существующего Angie.

```sh
docker compose --env-file .env.existing -f compose.existing.yaml up -d
docker compose --env-file .env.existing -f compose.existing.yaml exec manager apm setup-token
```

## Сервисы, пути и обновление

manager обслуживает UI/API, worker выполняет очередь и мониторинг, agent проверяет и применяет конфигурацию, docker-gateway отдаёт разрешённые запросы чтения. Общий каталог данных содержит SQLite, master.key, сертификаты, acme, revisions, current и журналы. Сохраняйте резервную копию всего каталога с ключом, не только базы.

Перед обновлением создайте зашифрованную копию, остановите сервисы, обновите исходники/образы, пересоберите manager и Angie и запустите. Проверьте health, generation и маршруты. Не удаляйте volume командой down --volumes, если данные нужны. В production отдельно проверьте архитектуру CPU, права каталогов и поддержку используемых модулей.

[Все переменные](environment.md) · [CLI](cli.md) · [Резервные копии](imports.md)
