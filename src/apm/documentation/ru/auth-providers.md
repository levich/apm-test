# Внешняя авторизация

Внешние сервисы auth_request. Сначала разверните совместимый сервис, задайте origin и signin URL, затем подключите профиль к хосту/пути. APM не устанавливает сам сервис авторизации. Администратор управляет профилями.

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

### `provider`

<!-- setting:provider -->
Тип сервиса auth_request. APM выбирает endpoint и допустимые заголовки для Authelia, Authentik, OAuth2 Proxy, TinyAuth, VoidAuth или Anubis.

Формат: `string`. По умолчанию: `обязательно`. Ограничения: authelia / authentik / oauth2proxy / tinyauth / voidauth / anubis.

Пример: `"authelia"`.

### `url`

<!-- setting:url -->
HTTP(S)-origin сервиса внешней авторизации без query и пути. APM добавляет endpoint выбранного провайдера; сервис должен быть доступен Angie.

Формат: `string`. По умолчанию: `обязательно`.

Пример: `"https://auth.example.com"`.

### `signin_url`

<!-- setting:signin_url -->
Полный адрес страницы входа внешнего провайдера. Используется как цель перенаправления для неавторизованного клиента.

Формат: `string`. По умолчанию: `обязательно`.

Пример: `"https://auth.example.com/login"`.

### `redirect_login`

<!-- setting:redirect_login -->
Перенаправлять ответ auth_request 401 на signin_url. Отключите для API, где клиент должен получить код отказа без страницы входа.

Формат: `boolean`. По умолчанию: `true`.

Пример: `true`.

### `identity_headers`

<!-- setting:identity_headers -->
Разрешённые заголовки идентичности из ответа сервиса авторизации. Остальные известные identity-заголовки очищаются, чтобы клиент не мог выдать себя за другого пользователя.

Формат: `array`. По умолчанию: `["Remote-User", "Remote-Email", "Remote-Groups"]`. Ограничения: Remote-User / Remote-Email / Remote-Groups / X-Auth-Request-User / X-Auth-Request-Email / X-Authentik-Username / X-Authentik-Email / X-Authentik-Groups.

Пример: `["Remote-User", "Remote-Email", "Remote-Groups"]`.

## Пример работы

Создайте ресурс с понятным названием, заполните обязательные поля и сохраните. Проверьте завершение apply в «Операциях». При ошибке angie -t исправьте параметры или зависимости; прежняя рабочая конфигурация сохраняется. Observer читает данные, admin удаляет ресурсы, которые больше не используются.

[Операции](operations.md) · [Системные настройки](environment.md) · [Оглавление](index.md)
