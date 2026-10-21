#!/bin/bash

# Установка Angie OSS и дополнительных модулей из официального репозитория
# для Debian/Ubuntu. Команды sudo запрашивают права администратора.
# Инструкция по установке: https://angie.software/angie/docs/installation/oss_packages/

# Обновляем локальный индекс пакетов из уже подключённых репозиториев.
sudo apt-get update

# ca-certificates — корневые сертификаты для проверки HTTPS-соединений.
# Документация: https://manpages.debian.org/stable/ca-certificates/update-ca-certificates.8.en.html
# curl — утилита загрузки файлов по HTTP/HTTPS; ниже скачивает ключ репозитория.
# Документация: https://curl.se/docs/manpage.html
# Флаг -y автоматически подтверждает установку пакетов и их зависимостей.
sudo apt-get install -y ca-certificates curl

# Сохраняем официальный ключ подписи в хранилище доверенных ключей APT,
# чтобы APT мог проверять подписи метаданных репозитория Angie.
sudo curl -o /etc/apt/trusted.gpg.d/angie-signing.gpg \
    https://angie.software/keys/angie-signing.gpg

# Читаем ID дистрибутива, его версию и кодовое имя из /etc/os-release
# и формируем строку репозитория для установленной системы.
# sudo tee записывает её с правами администратора; /dev/null скрывает вывод tee.
echo "deb https://download.angie.software/angie/$(. /etc/os-release && echo "$ID/$VERSION_ID $VERSION_CODENAME") main" \
    | sudo tee /etc/apt/sources.list.d/angie.list > /dev/null

# Повторно обновляем индекс, теперь включая пакеты из репозитория Angie.
sudo apt-get update

# angie — веб-сервер и обратный прокси для HTTP/HTTPS и TCP/UDP.
# Документация: https://angie.software/angie/docs/
sudo apt-get install -y angie

# angie-module-brotli — сжатие HTTP-ответов алгоритмом Brotli на лету
# и выдача заранее сжатых файлов .br.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/brotli/
sudo apt-get install -y angie-module-brotli

# angie-module-headers-more — добавление, изменение и удаление
# HTTP-заголовков запросов и ответов.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/headers-more/
sudo apt-get install -y angie-module-headers-more

# angie-module-zstd — сжатие HTTP-ответов алгоритмом Zstandard на лету
# и выдача заранее сжатых файлов .zst.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/zstd/
sudo apt-get install -y angie-module-zstd

# angie-module-unbrotli — распаковка ответов с Content-Encoding: br
# для клиентов, которые не поддерживают Brotli.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/unbrotli/
sudo apt-get install -y angie-module-unbrotli

# angie-module-testcookie — проверка клиентов с помощью cookie
# и механизма «запрос — ответ» для защиты от ботов.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/testcookie/
sudo apt-get install -y angie-module-testcookie

# angie-module-subs — замена строк в теле HTTP-ответа,
# в том числе с использованием регулярных выражений.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/subs/
sudo apt-get install -y angie-module-subs

# angie-module-set-misc — дополнительные директивы set_* для обработки
# переменных: кодирование, декодирование, хеширование и другие преобразования.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/set-misc/
sudo apt-get install -y angie-module-set-misc

# angie-module-unzstd — распаковка ответов с Content-Encoding: zstd
# для клиентов, которые не поддерживают Zstandard.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/unzstd/
sudo apt-get install -y angie-module-unzstd

# angie-module-upload — обработка загрузок multipart/form-data
# с возможностью возобновления передачи файлов.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/upload/
sudo apt-get install -y angie-module-upload

# angie-module-vod — подготовка видео по запросу: переупаковка MP4
# в потоковые форматы HLS, HDS, MSS и MPEG-DASH.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/vod/
sudo apt-get install -y angie-module-vod

# angie-module-vts — сбор статистики трафика виртуальных хостов,
# upstream-серверов и кэшей, включая модули мониторинга TCP/UDP.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/vts/
sudo apt-get install -y angie-module-vts

# angie-module-zip — формирование ZIP-архивов на лету
# из нескольких ресурсов, без предварительного создания архива на диске.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/zip/
sudo apt-get install -y angie-module-zip

# angie-module-postgres — выполнение запросов к PostgreSQL из Angie
# и использование базы данных как upstream для обработки HTTP-запросов.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/postgres/
sudo apt-get install -y angie-module-postgres

# angie-module-redis2 — отправка команд Redis из HTTP-обработчиков Angie
# и получение ответов по протоколу Redis.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/redis2/
sudo apt-get install -y angie-module-redis2

# angie-module-opentracing — распределённая трассировка запросов
# через OpenTracing с передачей данных в системы сбора трассировок.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/opentracing/
sudo apt-get install -y angie-module-opentracing

# angie-module-oidc — аутентификация пользователей через провайдера
# OpenID Connect, например Keycloak, с перенаправлением на страницу входа.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/oidc/
sudo apt-get install -y angie-module-oidc

# angie-module-njs — расширение обработки HTTP- и TCP/UDP-трафика
# с помощью JavaScript-скриптов на njs.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/njs/
sudo apt-get install -y angie-module-njs

# angie-module-modsecurity — подключение WAF ModSecurity к Angie
# для проверки HTTP-запросов по настроенным правилам защиты.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/modsecurity/
sudo apt-get install -y angie-module-modsecurity

# angie-module-lua — выполнение Lua-скриптов на этапах обработки
# HTTP-запросов и TCP/UDP-соединений.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/lua/
sudo apt-get install -y angie-module-lua

# angie-module-geoip2 — определение географических данных по IP-адресу
# с использованием баз MaxMind GeoIP2/GeoLite2 в формате MMDB.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/geoip2/
sudo apt-get install -y angie-module-geoip2

# angie-module-dav-ext — расширение WebDAV методами PROPFIND, OPTIONS,
# LOCK и UNLOCK для работы с файлами через HTTP.
# Документация: https://angie.software/angie/docs/configuration/modules/external-modules/dav-ext/
sudo apt-get install -y angie-module-dav-ext

# Для использования установленных динамических модулей добавьте необходимые
# директивы load_module в контекст main конфигурации Angie (вне http/stream).
# Имена файлов .so и примеры настройки приведены в документации каждого модуля.
# Документация: https://angie.software/angie/docs/installation/external-modules/
