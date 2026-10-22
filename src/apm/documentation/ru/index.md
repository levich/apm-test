# Руководство Angie Proxy Manager

Начните с установки и системных настроек, затем создайте маршруты и проверьте операции. Каждая статья содержит назначение, права, настройки и ограничения текущей реализации.

## Разделы

- [Списки доступа](access-lists.md)
- [API и вычисляемые статусы](api.md)
- [Аудит](audit.md)
- [Внешняя авторизация](auth-providers.md)
- [Сертификаты](certificates.md)
- [Локальный CLI](cli.md)
- [Клиентские сертификаты](client-cas.md)
- [Конфигурационные файлы](configuration-files.md)
- [CrowdSec / AppSec](crowdsec-profiles.md)
- [Обзор](dashboard.md)
- [Установка и Compose](deployment.md)
- [Docker discovery](discovery.md)
- [DNS-провайдеры](dns-profiles.md)
- [Документация](documentation.md)
- [Ключи ECH](ech.md)
- [Системные настройки](environment.md)
- [Правила GeoIP](geo-policies.md)
- [HTTP-заголовки](header-policies.md)
- [Импорт и резервные копии](imports.md)
- [Журналы](logs.md)
- [Метрики](metrics.md)
- [Операции](operations.md)
- [Прокси-хосты](proxy-hosts.md)
- [Перенаправления](redirect-hosts.md)
- [Настройки сервера](runtime.md)
- [Безопасность аккаунта](security.md)
- [Статика / PHP](sites.md)
- [TCP / UDP](streams.md)
- [Политики TLS](tls-policies.md)
- [Группы backend](upstreams.md)
- [Пользователи](users.md)

Изменение настроек и применение — разные этапы. Не считайте ресурс активным до успешной операции. Observer читает; operator управляет маршрутами/ACL/upstream; admin также управляет политиками, сертификатами, пользователями, импортом и системными действиями.
