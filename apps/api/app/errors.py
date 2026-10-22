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
