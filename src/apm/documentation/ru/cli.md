# Локальный CLI

Команды выполняются на сервере APM с теми же APM_* и каталогом данных. Требуются локальные права владельца установки. Пароли вводятся интерактивно. Для справки используйте apm COMMAND --help.

## `apm serve`

<!-- command:serve -->
Запуск manager; --host по умолчанию 0.0.0.0, --port 8181. Публикуйте backend только на loopback/закрытой сети.

<!-- option:serve.host -->
<!-- option:serve.port -->

## `apm worker`

<!-- command:worker -->
Запуск очереди, обслуживания и мониторинга backend. --once обрабатывает одно задание без постоянного мониторинга.

<!-- option:worker.once -->

## `apm agent`

<!-- command:agent -->
Запуск локального Unix-агента в сети Angie. Требуются права проверки и reload Angie.


## `apm bootstrap-agent`

<!-- command:bootstrap-agent -->
Подготовить bootstrap TLS и начальные include. В existing не заменяет основной конфиг Angie.


## `apm pre-run`

<!-- command:pre-run -->
Выполнить локальные deployment hooks из APM_PRE_RUN_DIR. HTTP API не создаёт hooks.


## `apm setup-token`

<!-- command:setup-token -->
Показать одноразовый setup token локально. После создания первого admin токен недоступен.


## `apm migrate`

<!-- command:migrate -->
Применить миграции текущей схемы. Перед изменением существующей версии предусмотрена резервная копия.


## `apm backup-password`

<!-- command:backup-password -->
Интерактивно сохранить пароль архива длиной от 16 символов. Пароль в аргументы команды не передаётся.


## `apm backup`

<!-- command:backup -->
Создать зашифрованную копию при остановленных manager и worker. Нужен ранее заданный пароль архива.


## `apm restore`

<!-- command:restore -->
Аргумент ARCHIVE — путь .apm; пароль вводится скрыто. Выполнять при остановленных manager и worker; прежний каталог сохраняется.

<!-- option:restore.archive -->

## `apm reset-password`

<!-- command:reset-password -->
Аргумент EMAIL, новый пароль от 12 символов вводится скрыто. --reset-mfa также сбрасывает TOTP/recovery. Все сессии отзываются.

<!-- option:reset-password.email -->
<!-- option:reset-password.reset_mfa -->

## `apm resume-applies`

<!-- command:resume-applies -->
Разрешить apply после локального устранения ошибки отката. Нельзя использовать, пока существует неразрешённый apply-journal.json.


## `apm export-npm`

<!-- command:export-npm -->
Аргумент OUTPUT — новый файл snapshot. Выберите ровно один источник: --sqlite PATH или --postgres (DSN вводится скрыто). --certificates PATH добавляет PEM из каталога live/npm-ID. Экспорт read-only.

<!-- option:export-npm.output -->
<!-- option:export-npm.sqlite -->
<!-- option:export-npm.postgres -->
<!-- option:export-npm.certificates -->

## `apm gateway`

<!-- command:gateway -->
Read-only Docker gateway; --host 0.0.0.0, --port 2375. Разрешены только необходимые discovery запросы чтения; не публикуйте порт в интернет.

<!-- option:gateway.host -->
<!-- option:gateway.port -->

