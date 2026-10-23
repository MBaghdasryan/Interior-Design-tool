"""Stable API error codes. The response body is
`{"code": "...", "params": {...}, "detail": "<ru fallback>"}` — clients translate by
`code`; `detail` is kept only as a human-readable fallback for logs and old clients."""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# code → Russian fallback text (the web client ships hy/ru/en translations for every code)
MESSAGES: dict[str, str] = {
    "auth.required": "Требуется авторизация",
    "auth.invalid_session": "Сессия недействительна",
    "auth.bad_credentials": "Неверный email или пароль",
    "auth.forbidden": "Недостаточно прав",
    "auth.no_org": "Нет организации для создания проекта",
    "auth.production_level_requires_verifier": "Уровень Production Ready устанавливает только обмерщик/специалист",
    "not_found": "Не найдено",
    "project.not_found": "Проект не найден",
    "variant.not_found": "Вариант не найден",
    "product.not_found": "Товар не найден в каталоге",
    "wall.not_found": "Стена не найдена",
    "share.invalid": "Ссылка недействительна",
    "file.link_expired": "Ссылка недействительна или истекла",
    "file.too_large": "Файл больше 500 МБ",
    "file.unsupported": "Неподдерживаемый или несоответствующий содержимому формат",
    "file.malware": "Файл отклонён антивирусной проверкой",
    "file.empty": "Пустой файл",
    "geometry.missing": "Нет геометрии",
    "geometry.no_rooms": "Нет помещений — добавьте хотя бы одно помещение",
    "geometry.required_for_generation": "Загрузите план или постройте геометрию перед генерацией",
    "catalog.own_empty": "Собственный каталог пуст — доступен после загрузки каталога поставщиков",
    "catalog.same_category_only": "Замена возможна только товаром той же категории",
    "catalog.import_price_guard": "Импорт остановлен: слишком много резких изменений цен",
    "job.retry_only_failed": "Повтор возможен только для упавшей задачи",
    "variant.approved_immutable": "Вариант утверждён — изменения создаются после снятия утверждения",
    "variant.blocking_issues": "Нельзя утвердить: есть блокирующие замечания правил",
    "cart.requires_approval": "Корзина формируется из утверждённого варианта",
    "order.made_to_measure_requires_production": "Изделия по размерам: требуется верификация обмеров (Production Ready)",
    "order.demo_supplier": "DEMO-поставщик: заказ не может быть отправлен",
    "catalog.live_disabled": "Внешняя загрузка выключена (EXTERNAL_FETCH_LIVE=false)",
    "bim.ifc_unreadable": "IFC-файл не удалось прочитать",
    "bim.no_walls": "В файле не найдено стен",
    "roomplan.not_json": "Это не JSON-экспорт RoomPlan",
    "roomplan.no_walls": "В скане нет стен",
    "roomplan.bad_surface": "Повреждённая поверхность в скане",
    "custom.ordered_locked": "Конфигурация уже заказана — создайте копию для изменений",
    "custom.invalid": "Конфигурация не прошла проверку производственных ограничений",
    "custom.not_priced": "Нет цены производителя: выберите производителя со ставками или запросите расчёт",
    "search.off": "Семантический поиск выключен (SEARCH_EMBEDDINGS=off)",
    "supplier.onboarding_incomplete": "Онбординг не завершён: {steps}",
    "asset.kind": "Неизвестный тип ассета",
    "asset.extension": "Формат файла не подходит для этого типа",
    "asset.empty": "Пустой файл",
    "asset.too_large": "Файл больше допустимого размера",
    "asset.not_glb": "Это не бинарный glTF (GLB)",
    "asset.gltf_version": "Нужен glTF 2.0",
    "asset.glb_truncated": "GLB-файл повреждён (длина не совпадает)",
    "asset.glb_no_json": "В GLB нет JSON-описания сцены",
    "asset.gltf_no_mesh": "В модели нет геометрии (meshes)",
    "asset.not_gltf": "Это не glTF JSON",
    "asset.not_image": "Изображение не читается",
    "asset.image_too_big": "Текстура больше 8192 px",
    "asset.not_pdf": "Это не PDF",
    "asset.not_ifc": "Это не IFC (ISO-10303-21)",
    "asset.not_dwg": "Это не DWG",
    "asset.not_dxf": "Это не DXF",
    "asset.not_rvt": "Это не файл Revit",
    "cart.orders_in_progress": "Заказы по этому проекту уже отправлены — новая корзина продублирует их",
    "cart.not_found": "Корзина не найдена — сформируйте её из утверждённого варианта",
    "order.recheck_required": "Перед заказом перепроверьте цены и наличие",
    "order.items_unavailable": "Часть позиций недоступна ({n}) — замените их перед заказом",
    "order.bad_transition": "Переход статуса недопустим: {frm} → {to}",
    "order.paid_needs_refund": "Заказ оплачен — сначала оформите возврат",
    "order.not_confirmed": "Поставщик ещё не подтвердил заказ",
    "order.nothing_to_refund": "Нет оплаты для возврата",
    "payment.integration_pending": "Онлайн-оплата не подключена (Integration pending) — заказ оплачивается по счёту поставщика",
    "payment.already_paid": "Заказ уже оплачен",
    "payment.provider_error": "Платёжный провайдер вернул ошибку",
    "payment.bad_signature": "Подпись webhook не прошла проверку",
    "payment.stale_signature": "Подпись webhook устарела",
    "payment.amount_mismatch": "Сумма платежа не совпадает с заказом",
    "payout.exceeds_balance": "Выплата больше задолженности перед поставщиком ({owed} ֏)",
    "plan.project_limit": "Лимит тарифа «{plan}»: не более {limit} активных проектов",
    "rfq.demo_supplier": "DEMO-поставщик: RFQ не отправляется реальному магазину",
    "aps.disabled": "Autodesk APS не подключён",
    "aps.error": "Ошибка Autodesk APS",
    "ai.unavailable": "AI-провайдер недоступен",
    "supplier.not_linked": "Организация поставщика не привязана к каталогу",
    "bureau.not_found": "Нет бюро",
    "trust.requirements_missing": "Не выполнены требования для перехода на уровень",
    "validation": "Ошибка проверки данных",
    "payments.integration_pending": "Платёжная интеграция не подключена",
    "auth.email_taken": "Этот e-mail уже зарегистрирован",
    "auth.weak_password": "Пароль слишком простой",
    "auth.token_invalid": "Ссылка недействительна или уже использована",
    "auth.token_expired": "Срок действия ссылки истёк",
    "auth.terms_required": "Нужно принять условия использования",
    "auth.csrf": "Запрос отклонён защитой CSRF — обновите страницу",
    "auth.demo_disabled": "Демо-доступ отключён",
    "auth.account_disabled": "Учётная запись отключена",
    "rate_limited": "Слишком много запросов — повторите позже",
    "ai.quota_exceeded": "Исчерпан бюджет AI организации",
    "auth.mfa_invalid": "Неверный код подтверждения",
    "auth.mfa_required": "Нужен код из приложения-аутентификатора",
    "auth.mfa_enrollment_required": "Для вашей роли нужно включить двухфакторную аутентификацию",
    "auth.mfa_not_started": "Сначала начните настройку двухфакторной аутентификации",
    "auth.deletion_pending": "Аккаунт помечен на удаление",
    "file.scan_unavailable": "Антивирусная проверка недоступна — повторите позже",
}

_BY_TEXT = {v: k for k, v in MESSAGES.items()}


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, **params):
        self.code = code
        self.params = params
        headers = {"Retry-After": str(params["retry_after"])} if "retry_after" in params else None
        super().__init__(status_code=status_code, detail=MESSAGES.get(code, code), headers=headers)


def _code_for(exc: HTTPException) -> tuple[str, dict]:
    if isinstance(exc, ApiError):
        return exc.code, exc.params
    if isinstance(exc.detail, str):
        text = exc.detail
        if text in _BY_TEXT:
            return _BY_TEXT[text], {}
        for k, v in MESSAGES.items():
            if text.startswith(v):
                return k, {"info": text[len(v):].strip(" :—-")}
    return {401: "auth.required", 403: "auth.forbidden", 404: "not_found"}.get(exc.status_code, f"http.{exc.status_code}"), {}


async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    code, params = _code_for(exc)
    detail = exc.detail if isinstance(exc.detail, str) else MESSAGES.get(code, code)
    return JSONResponse(status_code=exc.status_code, content={"code": code, "params": params, "detail": detail}, headers=getattr(exc, "headers", None))


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"code": "validation", "params": {"fields": fields}, "detail": MESSAGES["validation"]})
