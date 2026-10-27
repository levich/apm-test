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
Для Authentik адрес начала входа создаётся автоматически по authentik_mode; ручной /login не используется. Для остальных провайдеров задайте полный адрес страницы входа — он обязателен, если включён redirect_login.

Формат: `string`. По умолчанию: пустая строка; для Authentik вычисляется автоматически.

Пример для другого провайдера: `"https://auth.example.com/"`.

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


Переменные identity используют короткие уникальные имена, совместимые со стандартным variables_hash_bucket_size=64 на Linux. Увеличивать глобальный hash только для включения внешней авторизации не требуется. Для HTTPS-сервиса auth_request передаётся SNI его hostname.


### `authentik_mode`

<!-- setting:authentik_mode -->
Режим должен совпадать с Proxy Provider в Authentik: single_application (по умолчанию) либо domain_level. В single_application APM автоматически создаёт вход на домене приложения `/outpost.goauthentik.io/start`, открытый маршрут `/outpost.goauthentik.io/*` для start/callback и передачу cookie outpost. В domain_level вход начинается на origin Authentik. Исходный адрес приложения передаётся в rd. Для Authentik signin_url вычисляется автоматически и скрыт в форме; ручной `/login` не используется. Для остальных провайдеров signin_url по-прежнему нужен при включённом redirect_login.

Ранее сохранённые профили Authentik без режима используют single_application. Сам портал Authentik не защищайте его собственным forward-auth; APM отклоняет такую конфигурацию до активации. На один виртуальный хост допускается один origin и режим Authentik. Префикс `/outpost.goauthentik.io` зарезервирован под маршруты протокола и не должен задаваться в дополнительных locations. Проверяйте весь цикл входа, включая возврат на приложение, а не только ответ 302.
