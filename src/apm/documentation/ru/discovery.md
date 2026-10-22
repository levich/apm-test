# Docker discovery

Включите APM_DISCOVERY_ENABLED, задайте allowlists сетей и доменов, затем labels контейнера. Для ACME также APM_DISCOVERY_ACME_TERMS_AGREED и email. Не помещайте секреты в labels. Автоматические ресурсы редактируются через labels, не через UI; ручные ресурсы не перезаписываются. Удаление контейнера выключает маршрут при следующем сопоставлении.

## `apm.enable`

<!-- label:apm.enable -->
Включить discovery контейнера: строка true. По умолчанию не включён.

## `apm.host`

<!-- label:apm.host -->
Обязательный домен, например app.example.com, в разрешённой зоне APM_DISCOVERY_DOMAINS.

## `apm.network`

<!-- label:apm.network -->
Обязательное имя сети из APM_DISCOVERY_NETWORKS, например apps. Требуется IPv4 контейнера.

## `apm.port`

<!-- label:apm.port -->
Обязательный внутренний порт приложения, 1–65535; discovery не угадывает EXPOSE.

## `apm.scheme`

<!-- label:apm.scheme -->
http, https, grpc или grpcs; по умолчанию http. Это протокол backend.

## `apm.tls`

<!-- label:apm.tls -->
off, http или dns; по умолчанию off. Для http/dns нужны ACME terms; wildcard требует dns.

## `apm.dns-profile`

<!-- label:apm.dns-profile -->
Название заранее созданного DNS-профиля для dns. В нём должен быть включён discovery_allowed.

## `apm.weight`

<!-- label:apm.weight -->
Вес узла группы, 1–1000, по умолчанию 1. Одинаковые совместимые домены объединяются в upstream.

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

Для удалённого Docker требуется VPN/read-only gateway и отдельный сетевой маршрут Angie к контейнерам. Доступность IP из manager не доказывает доступность из Angie. При ошибках проверьте allowlists, IPv4, порт и совместимость labels.
