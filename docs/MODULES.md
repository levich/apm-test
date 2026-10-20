# Модули, функции APM и лицензия Angie PRO

Таблицы относятся к APM `0.1.0.dev0`; в манифесте проекта целевой Angie — `1.12.4`. Сведения сверены с кодом проекта и официальной документацией Angie **20.10.2026**. Наличие модуля и наличие настройки в APM не означают завершённую сетевую приёмку: её статус указан в [матрице совместимости](COMPATIBILITY.md).

**Реализованные настройки APM не требуют Angie PRO сами по себе:** они рассчитаны на OSS с соответствующими модулями, TLS-библиотекой и внешними сервисами. Возможности, для которых нужен именно PRO, приведены во второй таблице; готовых настроек этих возможностей в APM сейчас нет. Покупка лицензии не добавляет отсутствующие формы или логику compiler.

Angie PRO распространяется по коммерческой лицензии. Для использования его бинарного файла и PRO-возможностей нужна соответствующая лицензионная поставка; APM под MIT не предоставляет её. Условия поставки описаны на [официальной странице Angie PRO](https://en.angie.software/angie/pro/). В этой инструкции «PRO не нужна» относится только к лицензии Angie: у MaxMind, DNS API, CrowdSec, CAPTCHA и IdP могут быть собственные условия доступа.

## Как читать таблицу

- **База** — минимальная OSS-сборка, предусмотренная `deploy/local/Dockerfile`, и стандартные модули Angie, которые она не отключает. Состав конкретного официального или стороннего образа проверяется отдельно.
- **Extended** — дополнительный модуль предусмотрен `deploy/extended/Dockerfile`; расширенная сборка ещё требует приёмки. При системном Angie модуль устанавливает администратор.
- **Проверка сборки** — доступность зависит от TLS-библиотеки, ядра и результата capability probe.
- **Внешний компонент** — отдельный сервис или Python-компонент APM; покупка PRO не заменяет его настройку.

Имена вида `http_ssl` и `stream_proxy` обозначают модули Angie. Сторонние динамические модули обычно загружаются как `ngx_…_module.so`. Для готовых пакетов используются префиксы `angie-module-*` в OSS и `angie-pro-module-*` в PRO; наличие слова `pro` в имени пакета означает совместимость с соответствующей редакцией, а не исключительность самой функции. Например, GeoIP2, Lua, Brotli и Headers More доступны как сторонние модули для обеих редакций. [Каталог модулей Angie](https://en.angie.software/angie/docs/installation/external-modules/).

`compose.extended.yaml` собирает **OSS** из закреплённых исходников и заменяет бинарный файл в базовом образе. Он не сохраняет PRO при наложении на PRO-базу. Для PRO используйте лицензированный образ через `APM_ANGIE_IMAGE` в обычном профиле и совместимые с ним модули; готового extended-профиля PRO проект не предоставляет.

<a id="apm-functions"></a>

## 1. Какие зависимости нужны функциям текущего APM

| Функция | Модуль Angie / другие зависимости | Где предусмотрено | Нужна PRO | Ограничение или результат отсутствия зависимости |
|---|---|---|---|---|
| HTTP-прокси, redirects и WebSocket | `http_core`, `http_proxy`, `http_rewrite` | База | Нет | Без модулей соответствующие директивы не проходят проверку; WebSocket также должен поддерживаться приложением |
| Входящий HTTPS и HTTPS до backend | `http_ssl`, OpenSSL, сертификат/ключ; для backend — `http_proxy` и доверенные CA | База | Нет | Без SSL-сборки или корректного сертификата HTTPS недоступен |
| HTTP/2 | `http_v2`, для входящего TLS — `http_ssl` | База, флаг `--with-http_v2_module` | Нет | Нужны поддержка протокола в бинарном файле и входящий TLS по настройкам APM |
| HTTP/3 / QUIC | `http_v3`, совместимая TLS-библиотека, доступный UDP на HTTPS-порту | База с `--with-http_v3_module`; проверка сборки | Нет | Одного TCP/443 недостаточно; при отсутствии capability APM отклонит включение |
| gRPC / gRPCS | `http_grpc`, для gRPCS — TLS и доверенные CA | База, capability `grpc` | Нет | Нужен gRPC-backend; gRPCS и streaming ещё требуют расширения сетевых тестов |
| TCP и UDP-прокси | `stream`, `stream_proxy`, `stream_upstream` | База, `--with-stream` | Нет | Без stream конфигурация не проверяется; TCP TLS и входящий PROXY protocol не применяются к UDP |
| Входящий TCP TLS и TLS до stream-backend | `stream_ssl`, `stream_proxy`, OpenSSL, PEM и CA | База, `--with-stream_ssl_module` | Нет | Для входящего TLS нужен готовый сертификат; это не UDP/DTLS |
| Приём и передача PROXY protocol | Входной listener `http_core`/`stream_core`; исходящая передача — `stream_proxy` | База | Нет | Реальный IP и доверие к источнику настраиваются отдельно; входящий PROXY несовместим с QUIC в текущем APM |
| Upstream: веса, `backup`, `down`, round-robin, least_conn, ip_hash | `http_upstream` и модули методов/zone; для stream — `stream_upstream`, least_conn/hash | База | Нет | В stream поле `ip_hash` генерируется как `hash $remote_addr consistent`; активные health probes этим не включаются |
| IP ACL, Basic Auth, сочетание проверок | `http_access`, `http_auth_basic`, `http_core` (`satisfy`), файл htpasswd | База | Нет | Basic Auth требует сохранённых паролей; отсутствующий пароль блокирует генерацию |
| Authelia, Authentik, OAuth2 Proxy, Tinyauth, VoidAuth, Anubis | `http_auth_request`, `http_proxy`, отдельно работающий сервис авторизации | База с `--with-http_auth_request_module` + внешний компонент | Нет | Без внешнего сервиса проверки/входа авторизация не работает; нужен тест cookies и отказов |
| OIDC-вход в панель, TOTP и recovery codes | Python Authlib, PyOTP и код APM; для OIDC — IdP | Внешний компонент APM | Нет | Модули NJS/OIDC/Auth TOTP внутри Angie для этих функций панели не требуются |
| HSTS, noindex, добавление заголовков, фильтр User-Agent | `http_headers`, `http_proxy`, `http_rewrite` | База | Нет | Наличие заголовка не заменяет проверку доступа |
| Удаление заголовков через `header-policies.remove` | Headers More (`ngx_http_headers_more_filter_module`) | Extended / отдельная установка | Нет | Без capability `headers_more` APM отклонит эту настройку; обычное добавление заголовков остаётся доступно |
| Лимиты запросов/соединений, размера тела, таймауты и буферы | `http_limit_req`, `http_limit_conn`, `http_core`, `http_proxy` | База | Нет | Буферизация и таймауты backend в текущем compiler относятся к HTTP/HTTPS; AppSec требует request buffering |
| Gzip | `http_gzip` | База | Нет | Работает без Brotli/Zstd; статические предварительно сжатые файлы не включаются одним выбором gzip в форме |
| Brotli | `ngx_http_brotli_filter_module`, библиотека Brotli | Extended / отдельная установка | Нет | Без capability `brotli` включение отклоняется; модуль `_static` не нужен для сжатия ответа на лету |
| Zstd | `ngx_http_zstd_filter_module`, `libzstd` | Extended / отдельная установка | Нет | Без capability `zstd` включение отклоняется |
| Статические файлы, index и обычный список каталога | `http_static`, `http_index`, `http_autoindex`, доступ к файлам | База | Нет | Нужны каталог сайта и права чтения; index.html/index.php ищутся в установленном порядке |
| Оформленный список файлов | Fancyindex (`ngx_http_fancyindex_module`) | Extended / отдельная установка | Нет | Без capability `fancyindex` apply отклоняется; обычная статика не требует этого модуля |
| PHP | `http_fastcgi` и отдельный PHP-FPM с тем же абсолютным путём к скриптам | База + внешний компонент | Нет | FPM не запускается автоматически; пустой адрес FPM не включает исполнение PHP |
| Let's Encrypt HTTP-01/DNS-01, свои PEM и продление | Certbot в worker, ACME CA, DNS-адаптер/профиль для DNS-01; TLS-модули для обслуживания HTTPS | Внешний компонент APM + база | Нет | APM не использует встроенный `http_acme` Angie; доступны отдельные проверки/применение, а не только сохранение формы |
| Клиентские сертификаты mTLS, CRL и OCSP stapling | `http_ssl`, CA/CRL/цепочка сертификата и поддержка TLS | База; проверка окружения | Нет | Нужны правильные материалы CA/сертификата; отзыв и OCSP требуют отдельной сетевой проверки |
| ECH | `http_ssl`, TLS-библиотека с ECH, ключи и публикация ECHConfig в DNS | Проверка сборки; OpenSSL ECH предусмотрен extended | Нет | APM проверяет `ssl_encrypted_hello_key`; handshake и DNS-активация требуют приёмки |
| Сжатие TLS-сертификата | `http_ssl` и TLS-библиотека с certificate compression | Проверка сборки; соответствующий OpenSSL предусмотрен extended | Нет | Проверяется директива `ssl_certificate_compression`; не путать со сжатием HTTP-ответа gzip/Brotli |
| Реальный IP за доверенным proxy/CDN | `http_realip`, доверенные CIDR; для соответствующих stream-сценариев — `stream_realip` | База с флагами realip | Нет | Ошибочное доверие к источнику позволяет подменять клиентский адрес; диапазоны Cloudflare обновляются отдельно |
| GeoIP: страна и ASN | `ngx_http_geoip2_module`, `libmaxminddb`, GeoLite2-Country/ASN MMDB, доступ MaxMind для загрузки | Extended + внешний компонент | Нет | Без модуля или загруженной версии MMDB политика не применяется; лицензия PRO не предоставляет базы MaxMind |
| CrowdSec: решения LAPI | HTTP Lua, NDK при динамической сборке, LuaJIT, `lua-cjson`, `lua-resty-core`, Lua-файлы APM, `resty-http`, LAPI и bouncer key | Extended + внешние компоненты | Нет | Один общий CrowdSec-профиль на сервер; один модуль Lua без библиотек и LAPI недостаточен |
| AppSec и CAPTCHA CrowdSec | Зависимости CrowdSec, отдельный AppSec с правилами, request buffering; CAPTCHA — ключи провайдера | Extended + внешние компоненты | Нет | Реальные AppSec/CAPTCHA и отказы ещё требуют приёмки; не используются модули ModSecurity/NAXSI |
| Подтверждение reload, статистика и метрики APM | HTTP API Angie (`http_api`, `api /status/`), status zones и локальный агент | База | Нет | Чтение `/status/` доступно в OSS; динамический изменяющий API PRO — отдельная возможность |
| Access logs и отчёт GoAccess | `http_log`, файлы журналов; для HTML-отчёта — отдельный GoAccess | База + внешний компонент | Нет | Логи включаются в runtime; GoAccess не входит в сам Angie и требует отдельного профиля |
| Docker discovery, включая удалённый Engine | Python worker, шлюз APM, HTTP API Docker, доступ к backend-IP | Внешние компоненты APM | Нет | Модуль Angie `http_docker` не используется; нужен один endpoint и маршрутизация к контейнерам |
| Backup/restore, импорт, роли, аудит | Python-компоненты APM, SQLite, ключ шифрования; PostgreSQL-драйвер для соответствующего экспорта | Внешние компоненты APM | Нет | Лицензия PRO не заменяет backup/restore и миграцию; статус импорта зависит от исходной схемы |
| MPTCP | Поддержка `listen … multipath` в Angie, ядро Linux с разрешённым MPTCP | Проверка сборки и ядра | Нет | Проверяется MPTCP socket в окружении агента; в Docker Desktop используется Linux-ядро VM, не ядро macOS |
| QUIC BPF | Совместимые Angie, Linux и привилегированное окружение BPF | Заблокировано capability APM | Нет | В текущем агенте `quic_bpf.supported=false`; PRO не снимает эту блокировку, в existing настройка выполняется вне runtime APM |

Таблица описывает именно зависимости. Код APM выполняет `angie -t` и сохраняет прежнюю рабочую конфигурацию при отклонении кандидата; отсутствие дополнительного модуля не означает, что нужно покупать PRO.

Для TLS-возможностей ориентируйтесь на поддерживаемые библиотекой директивы и [документацию HTTP SSL](https://en.angie.software/angie/docs/configuration/modules/http/http_ssl/). Для API различие между статусом OSS и изменениями PRO явно указано в [документации API](https://en.angie.software/angie/docs/configuration/modules/http/http_api/).

<a id="pro-only"></a>

## 2. Возможности Angie, требующие PRO

Здесь перечислены серверные возможности, которые официальная документация помечает **PRO**. В OSS соответствующий вариант отсутствует; для использования нужен Angie PRO с подходящей лицензией. Эти строки не означают, что возможности уже реализованы в APM.

| Возможность | Модуль / директива | Без PRO | Поддержка в APM `0.1.0.dev0` |
|---|---|---|---|
| Изменение upstream через API без reload | `http_api`, изменяющий раздел `/config/`. [API](https://en.angie.software/angie/docs/configuration/modules/http/http_api/) | Нет | Не используется: APM генерирует конфигурацию и делает проверяемый reload |
| Активные проверки HTTP-backend | `http_upstream_probe`, `upstream_probe`. [HTTP Probe](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream_probe/) | Нет | Нет формы/генерации; healthcheck Compose проверяет инфраструктуру APM, а не каждый upstream |
| Активные проверки TCP/UDP-backend | `stream_upstream_probe`, `upstream_probe`, `upstream_probe_timeout`. [Stream Probe](https://en.angie.software/angie/docs/configuration/modules/stream/stream_upstream_probe/) | Нет | Нет формы/генерации |
| Балансировка по обратной связи от backend | `http_upstream`, `feedback`. [Upstream](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) | Нет | В `Upstream.strategy` сейчас только round_robin, least_conn и ip_hash |
| Привязка клиентского соединения к серверному, в том числе для NTLM | `http_upstream`, `bind_conn`. [Upstream](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) | Нет для этого механизма | Не генерируется; обычная HTTP-проксировка не подтверждает совместимость NTLM |
| Sticky learn с внешним хранилищем сессий | `sticky learn … remote_action=… remote_result=…`. [Sticky](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) | Нет для внешнего хранилища | Нет настройки; наличие обычных sticky-режимов в OSS не добавляет эту интеграцию |
| Особая политика удержания резервной группы | `http_upstream`, `backup_switch`. [Upstream](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) | Нет | Не генерируется; поле `backup` в APM доступно в OSS и не равно `backup_switch` |
| Очередь при отсутствии доступного сервера upstream | `http_upstream`, `queue`. [Upstream](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) | Нет | Не генерируется; очередь административных заданий APM — другой механизм |
| Сохранение динамического списка upstream-серверов в state-файле | `http_upstream`, `state`. [Upstream](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) | Нет | Не используется; сохранение ресурсов в SQLite и версий конфигурации APM не требует этой директивы |
| Сегментация proxy cache по нескольким путям с общей зоной | `http_proxy`: несколько `proxy_cache_path` с общим `keys_zone` и выбором `path`. [Proxy cache](https://en.angie.software/angie/docs/configuration/modules/http/http_proxy/) | Нет для сегментации | Нет отдельной формы; обычный proxy cache существует в OSS, но также не управляется отдельной формой текущего APM |

Параметры PRO требуют правильного контекста конфигурации. Поле `advanced` прокси-хоста находится внутри `server` и не предназначено для произвольной вставки директив уровня `upstream`. Ручная настройка возможностей PRO требует конфигурации в соответствующем контексте и проверки всего экземпляра; установка PRO не расширяет контекст поля `advanced`.

## 3. Что часто ошибочно относят к PRO

| Функция / ситуация | Уточнение |
|---|---|
| CrowdSec, AppSec и GeoIP | Дополнительные OSS-модули и внешние сервисы. Отсутствие их в базовом образе — ограничение комплектации |
| HTTP/3, ECH и сжатие сертификата | Требуют совместимых протоколов/TLS-библиотеки. Доступность определяется сборкой и тестами |
| `ip_hash`, shared zone, обычный `backup` | Доступны в Angie OSS; PRO-политики приведены отдельно выше |
| Обычные sticky cookie/route/локальный learn, least_time и slow_start | В документации Angie они не отнесены целиком к PRO. В текущей форме upstream APM эти параметры отсутствуют. [Upstream](https://en.angie.software/angie/docs/configuration/modules/http/http_upstream/) |
| LDAP, NJS и внешние модули аутентификации | Наличие пакетов для PRO не делает их исключительно PRO. Например, Auth LDAP есть и для OSS; профили прямого LDAP/NJS в APM пока не завершены. [Модули Angie](https://en.angie.software/angie/docs/installation/external-modules/) |
| MFA и OIDC панели | Реализованы в Python-приложении APM; отдельный коммерческий модуль Angie для них не нужен |
| Встроенный ACME и Docker-модуль Angie | APM использует собственный путь Certbot/discovery; их зависимости указаны в первой таблице |
| QUIC BPF не включается | Текущий capability gate APM запрещает настройку; лицензия не меняет код gate |

## 4. Проверка конкретного развёртывания

В вариантах A/C команды выполняются в выбранном Compose-профиле:

```sh
dc exec angie angie -V
dc exec angie angie -m
```

В B проверьте реально используемый бинарный файл на хосте:

```sh
sudo /usr/sbin/angie -V
sudo /usr/sbin/angie -m
sudo /usr/sbin/angie -p /etc/angie -t -c /etc/angie/angie.conf
```

Пути B замените своими. `-V` показывает версию и параметры сборки, `-m` — сведения о модулях; проверяйте также установленные `.so`, их зависимости и фактическую загрузку в конфиге. Агент публикует найденные возможности через защищённый `GET /api/v1/capabilities`. Для ECH и сжатия сертификата есть синтаксические probes; для MPTCP — проверка ядра; для ряда модулей используется обнаружение имён/файлов, которое само по себе не подтверждает рабочий сетевой сценарий.

В existing-режиме загрузка модулей в основной конфиг остаётся обязанностью администратора. В управляемом режиме APM формирует `load_module` из обнаруженных путей. Модули должны соответствовать версии, редакции и ABI бинарного файла; нельзя считать модуль из OSS автоматически совместимым с PRO только по имени.

PRO в проекте пока не прошла приёмку, а готовая лицензия и бинарные файлы не поставляются. Проверяйте доступную у поставщика версию PRO, условия лицензии и совместимость модулей отдельно; номер целевой версии в манифесте не подтверждает наличие готового PRO-образа. Подключение описано в [инструкции по развёртыванию](DEPLOYMENT.md#optional).

Основание со стороны проекта: [схемы доступных настроек](../src/apm/schemas.py), [compiler](../src/apm/compiler.py), [capability detection](../src/apm/agent.py), [минимальная OSS-сборка](../deploy/local/Dockerfile), [расширенная сборка](../deploy/extended/Dockerfile), [runtime и Lua-файлы](../deploy/angie/Dockerfile).
