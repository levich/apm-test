# Матрица NPMPlus и готовность 1.0

Все 25 групп остаются обязательными для первого публичного 1.0. Внутренняя версия `0.1.0.dev0` не изменяет согласованный объём. В этой таблице «код» означает реализованный путь UI/API/compiler; сетевое подтверждение указано отдельно. Поддержка PRO не выводится автоматически из совместимости OSS.

Зависимости от модулей и границы OSS/PRO приведены в [таблице модулей и лицензии](MODULES.md). Отметка «PRO не нужна» в ней не изменяет статус приёмки ниже.

| ID | Группа | Реализовано | Проверка и остаток |
|---|---|---|---|
| NP01 | HTTP/2, HTTP/3/QUIC | Переключатели host, QUIC, Alt-Svc, capability gate | Реальный gRPC/HTTP2 и HTTP3/QUIC через OSS 1.12.4; Linux/PRO впереди |
| NP02 | gRPC/gRPCS | Locations, upstream TLS, SNI, CA verification, identity headers | gRPC подтверждён; gRPCS, таймауты и streaming требуют расширения сетевых тестов |
| NP03 | PROXY protocol, stream TLS | Вход/выход, TCP TLS и повторный TLS к backend | Реальные TCP/UDP; PROXY/mTLS stream и ограничения источника ещё не приняты |
| NP04 | Upstream-группы | Веса, backup/down, round-robin/least_conn/ip_hash, ссылки HTTP/stream | Генерация; нужны сетевая проверка failover и подтверждение стратегий на stream |
| NP05 | Статика, PHP, индексы | Разрешённый site root, index, autoindex/fancyindex, внешний FPM | Compiler; отсутствует готовый и принятый профиль PHP-FPM |
| NP06 | ACL host/location | Порядок списков, IP/Basic Auth, satisfy, явное public/replace/inherit | Тесты порядка, хешей, запрета отсутствующих паролей; нужен визуальный итоговый ACL и полная сетевая матрица |
| NP07 | auth_request | Authelia, Authentik, OAuth2 Proxy, Tinyauth, VoidAuth, Anubis; очищение identity headers | Формы/compiler; нужны реальные сервисы, cookies, исключения и проверки отказов |
| NP08 | OIDC, MFA | Authlib, явная идентичность, TOTP, recovery, CLI recovery | MFA/recovery и роли проверены; внешние IdP не приняты |
| NP09 | CrowdSec | Официальная Lua library, LAPI, profile, fail policy | Источники закреплены; один профиль на сервер; нужен реальный LAPI/bouncer тест |
| NP10 | AppSec/bot protection | AppSec, observation, CAPTCHA, Anubis auth profile, запрет нечитаемого body | Нужна приёмка HTTP1.1–3, больших/streaming тел и всех отказов; нет готового профиля Anubis |
| NP11 | Заголовки, noindex | Response/upstream policy, HSTS, frame options, UA, headers-more gate | Compiler; проверить наследование и конфликты в сети |
| NP12 | Лимиты, буферизация | rate/conn/body/timeouts, request/response buffering | Генерация; нужны нагрузочные проверки и связь с AppSec |
| NP13 | Gzip/Brotli/Zstd | Переключатель алгоритма, upstream compression, модули | Gzip доступен; расширенные модули и precompressed files ещё не приняты |
| NP14 | ACME и свои сертификаты | Запрос HTTP/DNS-сертификата из SSL-вкладки прокси-хоста, Certbot, пять DNS API, CA/EAB/profile, ключи, продление и upload | UI и очередь выпуска проверены в Chromium/pytest; адаптеры — через имитацию API; нужен ACME test server и wildcard у пяти провайдеров |
| NP15 | mTLS | CA upload, CRL, verify mode/depth, immutable paths | Валидация CA/CRL; сетевые отзывы и identity headers ещё не приняты |
| NP16 | TLS/OCSP | TLS1.2/1.3, ciphers/curves, stapling, Must-Staple | Реальный TLS; OCSP, PQ/гибридные группы и ограничения CA требуют проверки |
| NP17 | ECH/cert compression | RFC key encoder, DNS confirmation, ротация, global key loading, probes | Формат и приватный ключ проверяются; handshake, auto DNS HTTPS publication, key retirement и расширенный образ ещё не приняты |
| NP18 | Real IP | Доверенные CIDR, Cloudflare refresh, PROXY listener controls | Compiler; нужен тест подмены адресов и источников PROXY |
| NP19 | GeoIP | Country/ASN, private/unknown policy, MaxMind credentials, versioned update | Код; нужны реальные MMDB, updater cadence и сетевые правила |
| NP20 | GoAccess/API docs | Защищённые API docs и HTML report, изолированный sidecar | API docs проверены; GoAccess Compose ещё не запущен |
| NP21 | Логи | Включение, маскирование IP, URI без query, ротация/reopen, API чтения, аудит отдельно | HTTP/analytics format проверяется настоящим Angie; stream logs, все политики хранения и retention UI ещё неполные |
| NP22 | IDN/default/dead hosts | IDNA, default 404/444/HTML/redirect | IDNA и генерация проверены; отдельная форма dead hosts пока отсутствует |
| NP23 | Runtime/модули | Workers/connections, IPv6, snippets, обнаружение совместимых модулей | Исходники расширенного образа закреплены; NJS/LDAP/NTLM/VTS/PUID/PGID профили ещё неполные |
| NP24 | Поставка | Compose, standalone APM с существующим Angie через локальный агент и include, setup, CLI recovery, read-only gateway, pre-run, MPTCP probe | Нативный existing HTTP/TCP и полный local Compose (Angie из исходника, s6, Unix-агент, HTTP, отказ ошибочной конфигурации) проходят на arm64; production host network, amd64, systemd, update/restore и официальная базовая OCI-сборка не приняты; QUIC BPF недоступен |
| NP25 | Импорт NPMPlus | SQLite/PostgreSQL read-only snapshot, ACL mapping, PEM bundle, preview/drafts/activate | SQLite snapshot/ACL/backup проверены; нет квалифицированной матрицы реальных версий NPM/NPMPlus и полного переноса расширений |

## Обязательные условия публичного выпуска

- Завершить перечисленные неполные реализации; добавить профильные sidecar-сервисы и итоговые формы политик.
- Собрать обычный и расширенный OSS-образы на amd64/arm64; закрепить доступные OCI digest, пакеты и SBOM.
- Выполнить установку, обновление и restore на чистом Linux с обычным Docker Engine; отдельно — s6 и host network.
- Получить лицензированную PRO 1.12.4 и подтвердить каждую заявленную возможность.
- Проверить ACME test server и реальные тестовые зоны Webnames, Yandex, REG.RU, Selectel v2 и Cloud.ru Evolution.
- Получить обезличенные исходные снимки поддерживаемых схем NPM/NPMPlus; проверить PostgreSQL snapshot и перенос PEM/ACL/связей.
- Принять реальный OIDC, auth_request, CrowdSec/AppSec/CAPTCHA/Anubis, GeoIP и GoAccess; проверить отказы по умолчанию.
- Завершить сбойную матрицу всех шагов apply/rollback/restore, конкурентные запросы и обновление с возвратом.
- Завершить RU/EN переводы полей и браузерную регрессию всех форм.

Без выполнения этих пунктов версия 1.0 и её полная совместимость не заявляются.
