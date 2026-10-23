# UI_IMPLEMENTATION_MAP — макеты «Interior Design tool UI» → экраны Renovara

Дата: 2026-10-23. Источник: 33 макета PNG в папке `Interior Design tool UI/` (коммит 3496a81).

## Что значат статусы

- **DONE** — экран работает на реальном API, у кнопок есть обработчики, есть RU/HY/EN, есть тест или E2E.
- **FUNCTIONAL** — функции из макета есть и подключены к API, но вёрстка ещё не подогнана под макет (сетка, графики, плотность).
- **PARTIAL** — часть функций макета есть, остальное перечислено в колонке «Изменения / чего нет».
- **NOT_IMPLEMENTED** — нужна новая предметная область, которой в продукте нет. Данные **не имитируются**, кнопок-заглушек нет.
- **BLOCKED** — нужно решение или ресурс владельца.

Общий стиль макетов уже совпадает с действующей дизайн-системой: левый сайдбар с иконками, верхняя панель, переключатель HY/RU/EN, KPI-карточки, терракотовые основные кнопки, правые выезжающие панели.

## Карта

| # | Макет | Маршрут | Роли | Что было | Изменения / чего нет | Статус |
|---|---|---|---|---|---|---|
| 01 | AI Interior Design Project Starter | `/app/new` | designer, bureau_admin | мастер нового проекта, загрузка плана, фото и видео | визуальная подгонка шагов | FUNCTIONAL |
| 02 | AI apartment design with real products | `/app/p/:pid` | designer, bureau_admin | варианты, смета, реальные SKU, статус цены | — | FUNCTIONAL |
| 03 | AI transforms a bare room into home | `/app/p/:pid/generate/:jid`, галерея рендеров | designer | конвейер генерации, рендеры «до/после» | живые рендеры заблокированы: нет кредитов Gemini | FUNCTIONAL / BLOCKED (AI-кредиты) |
| 04 | Apartment Interior Design Workspace | `/app/p/:pid/editor/:vid` | designer | 2D/3D-редактор, замена товаров, команды | — | FUNCTIONAL |
| 05 | Armenian Design Agency CRM Dashboard | — | — | нет | нужен CRM-домен: клиенты, сделки, источники лидов | NOT_IMPLEMENTED |
| 06 | Custom Kitchen RFQ Workspace | `/app/p/:pid/custom`, кабинет поставщика (входящие RFQ) | designer, manufacturer | конфигуратор, раскрой, RFQ, ставки производителя | реальные ставки — у партнёра | FUNCTIONAL / BLOCKED (производитель) |
| 07 | Enterprise role permissions dashboard | `/app/admin?tab=users` | platform_admin | роли зашиты в коде | **новое:** выдача и снятие ролей в любой организации, защита последнего администратора. Редактора матрицы прав нет: права фиксированы в коде (`security.ROLE_PERMS`) | PARTIAL |
| 08 | External catalog sources operations dashboard | `/app/admin?tab=sources` | platform_admin, platform_ops | источники, тест-скан, индекс, история, алерты | — | DONE |
| 09 | FORMA 2D/3D interior design studio | `/app/p/:pid/editor/:vid` | designer | PlanView + Scene3D, IFC | — | FUNCTIONAL |
| 10 | FORMA AI Interior Design Platform (лендинг) | `/` | все | лендинг hy/ru/en | — | DONE |
| 11 | FORMA AI Studio interior design workspace | `/app/p/:pid` | designer | результаты, варианты, команды AI | — | FUNCTIONAL |
| 12 | FORMA AI interior project wizard | `/app/new` | designer | мастер | визуальная подгонка | FUNCTIONAL |
| 13 | FORMA Armenian Product Marketplace | `/app/catalog`; корзина в `/app/p/:pid/procurement` | все; правка — platform, supplier | поиск (ключевой, умный, по фото), аналоги | **новое:** «Добавить товар», «Изменить» на карточке, редактор с вариантами. Корзина привязана к проекту, общей корзины нет | PARTIAL |
| 14 | FORMA CRM funnel and task center | — | — | нет | нужны воронка, задачи, исполнители | NOT_IMPLEMENTED |
| 15 | FORMA Design Bureau Dashboard | `/app/bureau` | bureau_admin, designer, platform_admin | KPI, расход AI, штамп | **новое:** админ платформы выбирает любое бюро (`?org=`); блок «Команда» с приглашением, сменой роли и исключением; штамп сохраняется для выбранного бюро и пишется в аудит. Графиков из макета нет | FUNCTIONAL |
| 16 | FORMA Interior Project Approval Screens (мобильный) | `/client/:token` | client | портал клиента: комментарии, решение | мобильная вёрстка по макету | FUNCTIONAL |
| 17 | FORMA Luna pendant light PIM | редактор товара (каталог, кабинет поставщика) | platform_admin, platform_ops, supplier_admin, supplier_catalog | только импорт прайса CSV/XLSX | **новое:** создание и редактирование товара вручную: RU/HY/EN-название, категория, бренд, класс, единица, тип, стили, описание; варианты (SKU, цена, валюта, габариты, цвет, материал, наличие, срок, ссылки). История цен с источником `manual`, архив вместо удаления. Медиа и 3D — в карточке «Ассеты» кабинета поставщика, а не в редакторе | PARTIAL |
| 18 | FORMA N99 documents and export hub | `/app/p/:pid/documents` | designer | альбом PDF, XLSX, DXF, IFC | — | FUNCTIONAL |
| 19 | FORMA analytics dashboard for Yerevan | — | — | есть только выручка по ledger (Финансы) и расход AI | нужны маржинальность и аналитика по рынку | NOT_IMPLEMENTED |
| 20 | FORMA interior project dashboard | `/app` | designer | дашборд проектов | — | FUNCTIONAL |
| 21 | FORMA inventory and pricing dashboard | `/app/supplier` | supplier_admin, supplier_catalog | фид, guard цен, наличие | **новое:** ручная правка цены и наличия по SKU. Остатков по складам в штуках нет: в модели только статус наличия | PARTIAL |
| 22 | FORMA luxury interior project portal (мобильный) | `/client/:token` | client | портал клиента | визуальная подгонка | FUNCTIONAL |
| 23 | FORMA partner portal dashboard | — | — | онбординг поставщика и договор | партнёрская программа (уровни, бонусы) — ждём условия и тарифы от владельца | NOT_IMPLEMENTED / BLOCKED |
| 24 | FORMA procurement workspace dashboard | `/app/p/:pid/procurement` | designer, bureau_admin | корзина по поставщикам, перепроверка цен, заказы | — | FUNCTIONAL |
| 25 | FORMA security operations dashboard | `/app/admin?tab=audit` и `quarantine`, `/app/account` | platform_admin | аудит, карантин ClamAV, MFA, сессии | **новое:** админ завершает сеансы и сбрасывает MFA пользователя, приостанавливает аккаунт или организацию. Нет SIEM-графиков | PARTIAL |
| 26 | FORMA supplier portal for Ardoma Lighting | `/app/supplier` | supplier_admin, supplier_catalog, platform_admin | KPI, качество данных, RFQ, заказы, ассеты, фид | **новое:** таблица товаров с добавлением, правкой и архивом; админ платформы выбирает поставщика (`?supplier=`) и работает в его кабинете: ассеты, склады, доставка, фид, заказы, ставки — всё через `supplier_id`. Договор и отправку на проверку оставили только поставщику (юридическое действие). Есть блок «Команда» | FUNCTIONAL |
| 27 | FORMA team workload dashboard | `/app/bureau` (Команда) | bureau_admin | только список участников | **новое:** руководитель бюро добавляет сотрудников по e-mail (приглашение на 72 ч), меняет роль, исключает. Загрузки, отпусков и часов нет — нужен домен задач и учёта времени | PARTIAL |
| 28 | Finance, commissions, and settlements dashboard | `/app/admin?tab=finance` | platform_admin | ledger, сверка, комиссии, выплаты, CSV/XLSX | онлайн-оплата: нет договора с Ameriabank | FUNCTIONAL / BLOCKED (vPOS) |
| 29 | Forma admin dashboard overview | `/app/admin` | platform_admin | KPI платформы | **новое:** вкладки «Пользователи», «Организации», «Поставщики» первыми; вкладка в URL (`?tab=`) | FUNCTIONAL |
| 30 | Forma organizations and users admin dashboard | `/app/admin?tab=users`, `?tab=orgs` | platform_admin | нет | **новое:** поиск, фильтр по статусу со счётчиками; добавление пользователя с письмом-приглашением; панель пользователя: роли, сброс пароля, завершение сеансов, сброс MFA, приостановка, удаление через процедуру ПДн. Организации: создание, переименование, приостановка, «Открыть кабинет», команда | DONE |
| 31 | Forma project messaging and notifications center | колокольчик уведомлений | все | уведомления hy/ru/en, настройки, дайджест | чата и переписки по проекту нет | PARTIAL |
| 32 | Orders, delivery, and installation dashboard | `/app/p/:pid/procurement`, кабинет поставщика → «Заказы» | designer, supplier | статусы заказа до монтажа | общего реестра заказов по всем проектам нет | PARTIAL |
| 33 | Organization localization and white-label settings | `/app/bureau` (штамп), `/app/glossary` | bureau_admin, linguist | штамп альбома, глоссарий HY | своих цветов и логотипа организации в интерфейсе нет | PARTIAL |

## Управление: сделано в этой итерации (запрос владельца)

| Требование | Где | API | Проверка |
|---|---|---|---|
| Полное управление пользователями в админке | Платформа → Пользователи | `GET/POST /admin/users`, `PATCH/DELETE /admin/users/{id}`, `/memberships`, `/reset-password`, `/revoke-sessions`, `/reset-mfa` | `tests/test_manage.py`, `e2e/management_e2e.py` |
| Кабинеты бюро и поставщика не пустые для админа | `/app/bureau?org=…`, `/app/supplier?supplier=…`; кнопки «Открыть кабинет» в «Организациях» и «Поставщиках» | `org_id` / `supplier_id` у всех эндпоинтов кабинетов | тесты и E2E |
| Полное управление поставщиками | Платформа → Поставщики | `GET /admin/suppliers/all`, `POST/PATCH/DELETE /admin/suppliers` (удаление запрещено при заказах) | тесты |
| Товары в каталоге: добавить, удалить (архив), править вручную | Каталог, кабинет поставщика | `POST/PATCH/DELETE /catalog/products`, `/variants`, `GET /catalog/variants/{id}/product` | тесты и E2E |
| Руководитель бюро добавляет сотрудников | Кабинет бюро → Команда | `GET /team`, `POST /team/invite`, `PATCH/DELETE /team/{mid}` | тесты и E2E |
| Поставщик управляет товарами не только файлом | Кабинет поставщика → Товары | то же, только свои товары (403 для чужих) | тесты и E2E |

Попутно закрыта уязвимость: импорт прайса (`/catalog/import/commit`) находил поставщика по имени без проверки владельца. Сотрудник одного поставщика мог перезаписать цены другого. Теперь можно передать явный `supplier_id`, права на запись проверяются в обоих случаях, есть тест.

## Что осталось по макетам

1. Визуальный проход по экранам со статусом FUNCTIONAL (01, 02, 04, 09, 11, 12, 15, 16, 20, 22, 24, 26): графики в KPI-карточках, плотность таблиц, мобильная вёрстка портала клиента. Функции уже работают.
2. Новые домены — только после решения владельца, без имитации данных:
   - CRM (05, 14);
   - аналитика рынка (19);
   - загрузка команды и отпуска (27);
   - партнёрская программа (23);
   - чат по проекту (31);
   - white-label-тема (33);
   - редактор матрицы прав (07);
   - остатки по складам в штуках (21).
