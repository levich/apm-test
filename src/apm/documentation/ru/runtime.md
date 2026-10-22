# Настройки сервера

Общесерверные параметры Angie; допускается один ресурс. Изменения требуют применения. В existing-режиме APM управляет только своими include, а основные настройки процесса остаются в конфиге владельца Angie. Только администратор.

## Настройки

### `name`

<!-- setting:name -->
Название ресурса для поиска и выбора в панели, например test. Не меняет его ID и связанные ресурсы.

Формат: `string`. По умолчанию: `обязательно`. Ограничения: minLength=1; maxLength=128.

Пример: `"test"`.

### `enabled`

<!-- setting:enabled -->
Включает объект в генерируемую конфигурацию. Выключенный объект сохраняется в панели. Изменение вступает в силу после сохранения и успешного применения.

Формат: `boolean`. По умолчанию: `true`.

Пример: `true`.

### `worker_connections`

<!-- setting:worker_connections -->
Максимум соединений на один worker Angie, включая клиентские и upstream. Учитывайте лимиты файлов ОС. В existing-режиме задаётся в основном конфиге Angie.

Формат: `integer`. По умолчанию: `1024`. Ограничения: minimum=128; maximum=1000000.

Пример: `1024`.

### `ipv6`

<!-- setting:ipv6 -->
Добавлять IPv6 listeners HTTP/HTTPS/QUIC для управляемых серверов. На хосте нужна поддержка IPv6; не создаёт DNS AAAA-записи.

Формат: `boolean`. По умолчанию: `true`.

Пример: `true`.

### `access_logs`

<!-- setting:access_logs -->
Включить журнал HTTP-доступа и доступ к нему в панели. По умолчанию выключен. URI журналируется без query-параметров.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `analytics`

<!-- setting:analytics -->
Дополнительный журнал формата GoAccess при включённом access_logs. Для отчёта нужен analytics sidecar из compose.analytics.yaml.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `mask_log_ips`

<!-- setting:mask_log_ips -->
Маскировать IP в HTTP-журналах: IPv4 до /24, IPv6 до первых групп; по умолчанию включено. Влияет на диагностику и аналитику.

Формат: `boolean`. По умолчанию: `true`.

Пример: `true`.

### `log_retention_days`

<!-- setting:log_retention_days -->
Заявленный параметр хранения логов. В текущей реализации ротация использует APM_METRICS_RETENTION_DAYS; изменение этого поля отдельно срок очистки не меняет.

Формат: `integer`. По умолчанию: `7`. Ограничения: minimum=1; maximum=365.

Пример: `7`.

### `trusted_proxies`

<!-- setting:trusted_proxies -->
Доверенные IP/CIDR прокси для X-Forwarded-For. Не указывайте произвольные сети: это влияет на ACL, географию, лимиты и IP журналов.

Формат: `array`. По умолчанию: `[]`.

Пример: `["10.0.0.0/8"]`.

### `trust_cloudflare`

<!-- setting:trust_cloudflare -->
Доверять актуальным диапазонам Cloudflare. Сначала обновите список адресов операцией cloudflare.refresh; без списка применение отклоняется.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `proxy_protocol_http`

<!-- setting:proxy_protocol_http -->
Ожидать PROXY protocol на HTTP listener. Включайте только за балансировщиком, который передаёт этот заголовок.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `proxy_protocol_https`

<!-- setting:proxy_protocol_https -->
Ожидать PROXY protocol на HTTPS listener. Несовместим с QUIC/HTTP3 в текущем компиляторе.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `mptcp`

<!-- setting:mptcp -->
Включить Multipath TCP для TCP listeners. Требуются поддержка ОС и Angie; переключатель не устанавливает модуль.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `quic_bpf`

<!-- setting:quic_bpf -->
Включить маршрутизацию QUIC через BPF. Требуются возможности Angie/ОС; в existing-режиме задавайте в основном конфиге.

Формат: `boolean`. По умолчанию: `false`.

Пример: `false`.

### `default_response`

<!-- setting:default_response -->
Ответ неизвестным HTTP-хостам: 404, закрытие 444, собственный html или redirect. В existing-режиме default server остаётся под управлением владельца Angie.

Формат: `string`. По умолчанию: `"404"`. Ограничения: 404 / 444 / html / redirect.

Пример: `"404"`.

### `default_html`

<!-- setting:default_html -->
HTML для default_response=html. Сохраняется в default.html внутри ревизии; браузеру отдаётся только для неизвестного хоста.

Формат: `string`. По умолчанию: `""`.

Пример: `""`.

### `default_redirect`

<!-- setting:default_redirect -->
HTTP(S)-адрес перенаправления при default_response=redirect. Пример https://example.com.

Формат: `string`. По умолчанию: `"https://example.com"`.

Пример: `"https://example.com"`.

### `http_snippet`

<!-- setting:http_snippet -->
Администраторские директивы в контексте http. Не вставляйте полный конфиг; angie -t проверяет кандидат перед активацией.

Формат: `string`. По умолчанию: `""`.

Пример: `""`.

### `stream_snippet`

<!-- setting:stream_snippet -->
Администраторские директивы в контексте stream. Изменения применяются через проверку, reload и проверку поколения.

Формат: `string`. По умолчанию: `""`.

Пример: `""`.

## Пример работы

Создайте ресурс с понятным названием, заполните обязательные поля и сохраните. Проверьте завершение apply в «Операциях». При ошибке angie -t исправьте параметры или зависимости; прежняя рабочая конфигурация сохраняется. Observer читает данные, admin удаляет ресурсы, которые больше не используются.

[Операции](operations.md) · [Системные настройки](environment.md) · [Оглавление](index.md)
