"""One localized, secret-free operation presentation for JSON and HTML."""

TEXT = {
    "ru": {
        "pending": "В очереди",
        "running": "Выполняется",
        "succeeded": "Завершено",
        "failed": "Ошибка",
        "apply": "Применение изменений",
        "certificate.issue": "Выпуск сертификата",
        "certificate.renew": "Перевыпуск сертификата",
        "dns.test": "Проверка DNS-профиля",
        "dns.cleanup": "Удаление проверочных DNS-записей",
        "discovery.reconcile": "Синхронизация Docker",
        "cloudflare.refresh": "Обновление адресов Cloudflare",
        "geoip.update": "Обновление GeoIP",
        "ech.generate": "Создание ключа ECH",
        "ech.confirm": "Проверка DNS и активация ECH",
        "backup": "Создание резервной копии",
        "unknown": "Системная операция",
        "waiting": "Задание сохранено и ожидает свободного worker.",
        "working": "Worker выполняет операцию. Результат появится автоматически.",
        "done": "Операция выполнена успешно.",
        "applied": "Конфигурация проверена и применена; Angie подтвердил новое поколение.",
        "issued": "Сертификат установлен. Применение новой конфигурации поставлено в очередь.",
        "failure": "Не удалось завершить операцию.",
        "diagnostics": "Проверьте диагностику соответствующего сервиса и повторите действие после устранения причины.",
        "rollback_failed": "Не удалось восстановить предыдущую конфигурацию. Новые применения остановлены.",
        "rollback_help": "Проверьте Angie и локальный журнал, восстановите рабочую конфигурацию, затем выполните apm resume-applies.",
        "restored": "Изменения не активированы; предыдущая конфигурация восстановлена.",
        "validate": "Angie отклонил конфигурацию или не смог выполнить reload.",
        "validate_help": "Проверьте локальный error.log Angie, параметры ресурса и дополнительные директивы.",
        "unsupported": "В установленной сборке Angie отсутствует необходимая возможность.",
        "unsupported_help": "Отключите неподдерживаемую настройку или установите совместимый модуль Angie.",
        "certbot": "Центр сертификации не выдал сертификат. Действующий сертификат сохранён, если он был установлен.",
        "certbot_help": "Проверьте локальный журнал ACME, DNS/HTTP-проверку доменов и учётные данные провайдера.",
        "agent": "Worker не смог связаться с готовым агентом Angie.",
        "agent_help": "Проверьте запуск Angie, Unix-сокет агента и одинаковый каталог данных сервисов.",
    },
    "en": {
        "pending": "Queued",
        "running": "Running",
        "succeeded": "Completed",
        "failed": "Failed",
        "apply": "Apply configuration changes",
        "certificate.issue": "Issue certificate",
        "certificate.renew": "Reissue certificate",
        "dns.test": "Test DNS profile",
        "dns.cleanup": "Remove DNS challenge records",
        "discovery.reconcile": "Synchronize Docker",
        "cloudflare.refresh": "Refresh Cloudflare addresses",
        "geoip.update": "Update GeoIP",
        "ech.generate": "Generate ECH key",
        "ech.confirm": "Verify DNS and activate ECH",
        "backup": "Create backup",
        "unknown": "System operation",
        "waiting": "The operation is queued and waiting for an available worker.",
        "working": "The worker is processing this operation. The result will appear automatically.",
        "done": "The operation completed successfully.",
        "applied": "The configuration passed validation and was applied; Angie confirmed a new generation.",
        "issued": "The certificate was installed. Applying the new configuration is queued.",
        "failure": "The operation could not be completed.",
        "diagnostics": "Check the relevant service diagnostics and retry after resolving the cause.",
        "rollback_failed": "The previous configuration could not be restored. Further applies are stopped.",
        "rollback_help": "Check Angie and its local log, restore a working configuration, then run apm resume-applies.",
        "restored": "The changes were not activated; the previous configuration was restored.",
        "validate": "Angie rejected the configuration or could not reload it.",
        "validate_help": "Check Angie's local error.log, resource settings and custom directives.",
        "unsupported": "The installed Angie build does not support a required capability.",
        "unsupported_help": "Disable the unsupported setting or install a compatible Angie module.",
        "certbot": "The certificate authority did not issue a certificate. Previously installed material is preserved.",
        "certbot_help": "Check the local ACME log, DNS/HTTP domain validation and provider credentials.",
        "agent": "The worker could not reach a ready Angie agent.",
        "agent_help": "Check Angie, the agent Unix socket and the services' shared data directory.",
    },
}


def present(job, language="en"):
    t = TEXT.get(language, TEXT["en"])
    context = job.payload.get("_context", {})
    kind = "certificate.renew" if job.kind == "certificate.issue" and job.payload.get("force") else job.kind
    title = t.get(kind, t["unknown"])
    if context.get("name"):
        title += " «" + context["name"] + "»"
    message = t["waiting"] if job.status == "pending" else t["working"]
    next_step = None
    if job.status == "succeeded":
        message = (
            t["applied"]
            if job.kind == "apply"
            else t["issued"]
            if job.kind == "certificate.issue"
            else t["done"]
        )
    if job.status == "failed":
        error = job.error or ""
        message, next_step = t["failure"], t["diagnostics"]
        if "rollback_failed" in error:
            message, next_step = t["rollback_failed"], t["rollback_help"]
        elif "previous revision restored" in error:
            message, next_step = t["restored"], t["validate_help"]
        elif "Unsupported capability" in error:
            message, next_step = t["unsupported"], t["unsupported_help"]
        elif "Angie command failed" in error:
            message, next_step = t["validate"], t["validate_help"]
        elif job.kind == "certificate.issue":
            message, next_step = t["certbot"], t["certbot_help"]
        elif "Agent" in error or "ConnectError" in error:
            message, next_step = t["agent"], t["agent_help"]
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "error": job.error,
        "result": job.result,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "title": title,
        "status_label": t.get(job.status, job.status),
        "message": message,
        "next_step": next_step,
        "subject": context,
    }
