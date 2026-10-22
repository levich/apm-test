# API и вычисляемые статусы

API требует входа по cookie. Изменения требуют X-CSRF-Token, обновление/удаление ресурса — If-Match с текущей version. Роли проверяются сервером. Ответ сохранения содержит operation_id/revision_id: дождитесь завершения операции. Полная OpenAPI-схема доступна admin в /api/docs.

GET /api/v1/resources/proxy-hosts добавляет health (status, checked_at, checks), ssl (configured, usable), certificate_info и active_operation. GET списка сертификатов добавляет certificate_info и active_operation. Поля вычисляемые, не входят в data и приватные snapshot. health.status: up/partial/down/unknown/disabled. certificate_info.status: valid/expiring/expired/not_yet_valid/key_mismatch/domain_mismatch/invalid_files/missing/disabled. Сроки — Unix UTC seconds; remaining_days округляется вверх. active_operation содержит id/status либо null.

POST /api/v1/resources/certificates/{id}/renew доступен admin: 202 и operation_id при постановке, 409 при текущем выпуске, 422 для custom/disabled или незаполненных условий. GET /api/v1/operations[/{id}] сохраняет kind/status/error/result и добавляет title/status_label/message/next_step/subject, локализованные по языку UI. Запросы мониторинга идут только через Unix-агент, не через браузер.
