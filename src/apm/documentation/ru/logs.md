# Журналы

HTTP access log доступен всем пользователям через панель и GET /api/v1/logs/access. В runtime включите access_logs; по умолчанию он выключен. Поля записи: time, host, ip, method, path, status. Query-параметры в URI не сохраняются. mask_log_ips управляет маскированием адресов.

Ротация переименовывает файл свыше 20 МБ и просит агента reopen. Очистка использует APM_METRICS_RETENTION_DAYS. Не путайте access log, административный аудит, операции и локальный error.log Angie. Если журнал пуст, проверьте access_logs, фактическое применение и наличие запросов. [Runtime](runtime.md) · [Аудит](audit.md)

[Оглавление](index.md)
