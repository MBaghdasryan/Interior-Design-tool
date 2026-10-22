# EVAL_REPORT — оценка качества AI (2026-10-22 15:12 UTC)

Набор: `apps/api/evals` (команды — `datasets/commands.json`, планы — `evals/plans.py`, синтетические с точной разметкой).
Каждый провайдер вызывается напрямую, без подмены детерминированной заглушкой. Ошибки (квота, кредиты, невалидный JSON) учитываются как провалы.
Стоимость — оценка по числу токенов × `AI_PRICES`, не счёт провайдера.

> **Примечания к этому прогону (читать до таблиц)**
> - **Планы, Gemini: результат недостоверен.** 29 из 30 ответов не разобраны как JSON. Причина найдена после прогона: Gemini 3 отдаёт JSON несколькими частями (`parts`, иногда после части-«мысли»), а провайдер брал только первую часть. Исправлено в `app/ai/providers.py` (склейка частей, явная ошибка при `MAX_TOKENS`, тест `test_gemini_joins_multipart_json_and_reports_truncation`). Метрики планов ниже посчитаны по **одному** валидному ответу и не отражают качество распознавания. Повторный прогон **заблокирован**: во время этого прогона закончились предоплаченные кредиты Gemini (HTTP 402).
> - **Реальные листы альбома (6 шт.) не оценивались (n=0):** харнесс искал только `plan_*.json`, а реальные листы называются `real_*.json`. Исправлено в `evals/run.py`; повторный прогон тоже ждёт пополнения кредитов Gemini.
> - **Фото, Gemini:** 1 вызов из 3 вернул обрезанный JSON — вероятно, та же причина с несколькими частями.
> - **OpenAI:** все вызовы вернули 429 «no credits remaining». **Anthropic:** ключ не задан. Оба `BLOCKED_BY_EXTERNAL_DEPENDENCY`.
> - **Команды, Gemini** — единственный полностью валидный набор этого прогона: 32/32 валидных ответа.

> **Повтор 2026-10-23 после пополнения (частичный — предоплата снова исчерпана посреди прогона, HTTP 402):**
> - Найдена настоящая причина обрыва JSON на планах: Gemini 3 тратит лимит `maxOutputTokens` на рассуждения. Исправлено: лимит по задачам (планы — 32k) и `thinkingLevel=low` для распознавания планов. Сравнение на 3 синтетических планах: **low** — 3/3 валидны, 9 с, 0,07 $; **high** — 2/3 (таймаут), 99 с, 0,38 $; точность одинаковая (комнаты 100 %, площади точно). Токены рассуждений теперь учитываются в стоимости.
> - **Команды:** 32/32 валидны, recall/precision операций 1.0, помещение 83 %, стабильность 94 %, 0 выдуманных SKU.
> - **Реальные листы альбома (5 из 6 ответили):** валидно 83 %, точное число помещений 40 %, тип помещения 12 %, ошибка площадей ~80 %, масштаб из размерной строки 80 %. Плотные рабочие чертежи распознаются плохо — это главный открытый риск распознавания; синтетические планы этого не показывают.
> - Синтетические планы (30) и фото (8) в этом повторе не прошли — 402. Полный повтор — после следующего пополнения.

## gemini
### AI-команды изменения (hy/ru/en)

| Метрика | Значение |
|---|---|
| Валидный structured output | 100% (32 команд) |
| Полнота операций (recall) | 100% |
| Точность операций (precision) | 100% |
| Категория предмета | 100% |
| Помещение | 83% |
| Стабильность (2 прогона → те же операции) | 94% |
| Выдуманные SKU после применения | 0 |
| Соблюдение бюджета (команды «сократи бюджет») | 4/4 |
| Полнота по языкам hy / ru / en | 100% / 100% / 100% |
| Задержка, мс (среднее) | 3941.062 |
| Стоимость прогона, USD | 0.0176 |

### Распознавание синтетических планов (30, 6 режимов качества)

| Метрика | Значение |
|---|---|
| Валидный structured output | 3% (30 планов) |
| Точное число помещений | 100% |
| Тип помещения | 67% |
| Ошибка площади помещений (MAPE) | 0% |
| Ошибка общей площади | 0% |
| Ошибка числа дверей / окон (шт., среднее) | 1.0 / 0.0 |
| Масштаб взят из размерной строки | 100% |
| Задержка, мс | 14156.0 |
| Стоимость прогона, USD | 0.0325 |

| Режим качества | Тип помещения | Ошибка площади |
|---|---|---|
| clean | — | — |
| low_res | 67% | 0% |
| no_area_labels | — | — |
| noisy_blur | — | — |
| photo_skew | — | — |
| rotated | — | — |

Ошибки: plan_01: JSONDecodeError: Expecting value: line 25 column 9 (char 368); plan_02: JSONDecodeError: Expecting ',' delimiter: line 16 column 22 (char 319); plan_03: JSONDecodeError: Expecting ',' delimiter: line 25 column 10 (char 358); plan_04: JSONDecodeError: Expecting ',' delimiter: line 26 column 13 (char 364); plan_05: JSONDecodeError: Expecting value: line 16 column 20 (char 316)

### Реальные планы (6 листов одной реальной квартиры, эталон — экспликация альбома)

Таблица экспликации и штамп вырезаны из изображения; эталон: 5 помещений, 58,13 м².

| Лист | Помещений (эталон 5) | Тип помещения | Ошибка площади | Общая площадь |
|---|---|---|---|---|

Среднее: тип —, ошибка площади —, общая площадь —, точное число помещений —.

### Фото квартиры «до ремонта» (8 СИНТЕТИЧЕСКИХ снимков Gemini Image с разметкой)

| Метрика | Значение |
|---|---|
| Тип комнаты (строго / с близкими типами) | 75% / 88% |
| Сопоставление ракурсов одной комнаты (precision / recall по парам) | 100% / 100% |
| Найдено комнат / в разметке | 6 / 6 |
| Окна найдены там, где они есть | — |
| Оценка глубины | модель не подключена (DepthProvider) — метрика не измеряется |
| Стоимость, USD | 0.0421 |

Ответы по фото: p01 living→living, p02 living→living, p03 bedroom→bedroom, p04 bedroom→hallway, p05 kitchen→kitchen, p06 bathroom→bathroom, p07 hallway→hallway, p08 kids→bedroom

Ошибки: JSONDecodeError: Unterminated string starting at: line 112 column 7 (char 3717)

## stub
### AI-команды изменения (hy/ru/en)

| Метрика | Значение |
|---|---|
| Валидный structured output | 100% (32 команд) |
| Полнота операций (recall) | 25% |
| Точность операций (precision) | 25% |
| Категория предмета | 21% |
| Помещение | 33% |
| Стабильность (2 прогона → те же операции) | 100% |
| Выдуманные SKU после применения | 0 |
| Соблюдение бюджета (команды «сократи бюджет») | 4/4 |
| Полнота по языкам hy / ru / en | 0% / 67% / 0% |
| Задержка, мс (среднее) | 0.031 |
| Стоимость прогона, USD | 0.0 |

### Распознавание синтетических планов (30, 6 режимов качества)

| Метрика | Значение |
|---|---|
| Валидный structured output | 100% (30 планов) |
| Точное число помещений | 0% |
| Тип помещения | 0% |
| Ошибка площади помещений (MAPE) | 100% |
| Ошибка общей площади | 100% |
| Ошибка числа дверей / окон (шт., среднее) | 4.0 / 2.667 |
| Масштаб взят из размерной строки | 0% |
| Задержка, мс | 0.0 |
| Стоимость прогона, USD | 0.0 |

| Режим качества | Тип помещения | Ошибка площади |
|---|---|---|
| clean | 0% | 100% |
| low_res | 0% | 100% |
| no_area_labels | 0% | 100% |
| noisy_blur | 0% | 100% |
| photo_skew | 0% | 100% |
| rotated | 0% | 100% |

## openai
### AI-команды изменения (hy/ru/en)

| Метрика | Значение |
|---|---|
| Валидный structured output | 0% (32 команд) |
| Полнота операций (recall) | — |
| Точность операций (precision) | — |
| Категория предмета | — |
| Помещение | — |
| Стабильность (2 прогона → те же операции) | — |
| Выдуманные SKU после применения | 0 |
| Соблюдение бюджета (команды «сократи бюджет») | 0/0 |
| Полнота по языкам hy / ru / en | — / — / — |
| Задержка, мс (среднее) | None |
| Стоимость прогона, USD | 0.0 |

Ошибки: cmd01: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; cmd02: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; cmd03: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; cmd04: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; cmd05: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza

### Распознавание синтетических планов (30, 6 режимов качества)

| Метрика | Значение |
|---|---|
| Валидный structured output | 0% (30 планов) |
| Точное число помещений | — |
| Тип помещения | — |
| Ошибка площади помещений (MAPE) | — |
| Ошибка общей площади | — |
| Ошибка числа дверей / окон (шт., среднее) | None / None |
| Масштаб взят из размерной строки | — |
| Задержка, мс | None |
| Стоимость прогона, USD | 0.0 |

| Режим качества | Тип помещения | Ошибка площади |
|---|---|---|
| clean | — | — |
| low_res | — | — |
| no_area_labels | — | — |
| noisy_blur | — | — |
| photo_skew | — | — |
| rotated | — | — |

Ошибки: plan_01: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; plan_02: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; plan_03: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; plan_04: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; plan_05: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza

### Реальные планы (6 листов одной реальной квартиры, эталон — экспликация альбома)

Таблица экспликации и штамп вырезаны из изображения; эталон: 5 помещений, 58,13 м².

| Лист | Помещений (эталон 5) | Тип помещения | Ошибка площади | Общая площадь |
|---|---|---|---|---|

Среднее: тип —, ошибка площади —, общая площадь —, точное число помещений —.

### Фото квартиры «до ремонта» (8 СИНТЕТИЧЕСКИХ снимков Gemini Image с разметкой)

| Метрика | Значение |
|---|---|
| Тип комнаты (строго / с близкими типами) | — / — |
| Сопоставление ракурсов одной комнаты (precision / recall по парам) | — / — |
| Найдено комнат / в разметке | — / — |
| Окна найдены там, где они есть | — |
| Оценка глубины | модель не подключена (DepthProvider) — метрика не измеряется |
| Стоимость, USD | 0.0 |

Ошибки: ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza; ProviderError: openai 429: {
  "error": {
    "message": "You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organiza

## anthropic
**Недоступен:** нет ключа API

## Как воспроизвести

```bash
docker compose exec api python -m evals.run --providers gemini,stub --suite all
```

Синтетические планы проверяют чтение чертежа (стены, подписи, размеры); реальные сканы и фото квартир (N99) — отдельный набор, когда будут материалы.
