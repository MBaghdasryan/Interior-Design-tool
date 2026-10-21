# AI-пайплайн

Ни одна модель не отвечает за весь проект: LLM понимает ТЗ и команды, всё измеримое делает детерминированный код.

```mermaid
flowchart TD
  A[Исходники: фото, видео, PDF/JPG, DXF, DWG/RVT/IFC] --> B{Тип}
  B -- DXF --> R1[ezdxf: слои стен/помещений]
  B -- DWG/RVT/IFC --> R2[Autodesk APS: SVF2 + свойства → помещения]
  B -- растр/PDF --> R3[Vision LLM: FloorplanRecognition JSON]
  R1 & R2 & R3 --> G[BuildingGraph draft + маска уверенности]
  G --> H[Человек: правка + контрольный размер → confirm]
  H --> I[LLM: DesignBrief JSON]
  I --> N[Product Need List]
  N --> X{Источник товаров}
  X -- Внешний каталог --> D[Discovery: allowlist → коннекторы → нормализация → скоринг → Snapshot]
  X -- Собственный --> P[PIM]
  X -- Концепция --> C[concept-объекты без цен]
  D & P & C --> S[Ранжирование кандидатов по стилю/уровню/габариту]
  S --> L[Layout engine: стены, проходы, двери, окна, радиаторы]
  L --> E[Электрика, свет, отделка, камеры]
  E --> V[Rules engine: pass/warning/block]
  V --> Q[Детерминированная смета]
  Q --> O[3 варианта · версии]
  O --> CMD[LLM: ChangePlan JSON] --> L
  O --> DOC[Альбом A3, DXF, DWG(APS), XLSX, GLB]
```

## Задачи и контракты (`app/ai`)

| Задача | Схема (Pydantic → JSON Schema) | Промпт | Маршрут провайдеров |
|---|---|---|---|
| `design_brief` | `DesignBrief` | `design_brief.v1.md` | OpenAI → Anthropic → Gemini → stub |
| `change_command` | `ChangePlan` (операции: replace_product, make_compact, add_object, remove_object, lighter/darker, cheaper/premium, budget_delta, change_style…) | `change_command.v1.md` | OpenAI → Anthropic → Gemini → stub |
| `floorplan_vision` | `FloorplanRecognition` | `floorplan_vision.v1.md` | OpenAI → Gemini → Anthropic → stub (stub честно требует ручного построения) |
| `variant_copy` | `VariantCopy` | `variant_copy.v1.md` | Anthropic → OpenAI → Gemini → stub |

* Structured outputs: OpenAI `text.format=json_schema strict`, Anthropic — forced tool use, Gemini — `responseJsonSchema`.
* Каждый ответ валидируется Pydantic; ошибка → retry → следующий провайдер → stub.
* Учёт: `AIUsage` (задача, провайдер, модель, версия промпта, токены, латентность, стоимость, ошибки); кэш одинаковых запросов.
* Модель по умолчанию задаётся env (`OPENAI_MODEL`, `ANTHROPIC_MODEL=claude-opus-5-5`, `GEMINI_MODEL`).

## Запреты (product grounding)

* Объект сцены всегда ссылается на `pv:<SKU>` / `ext:<запись>` / `concept:<категория>` — путь «создать товар из текста» в коде отсутствует.
* Цены считает только `estimate/estimator.py`; «цена по запросу» не суммируется как 0.
* Изображения — гипотеза; визуализации в альбоме строятся из модели сцены.

## Оценка качества (eval)

`tests/` уже покрывают: корректность структурированного вывода (stub-парсер на примере из ТЗ), отсутствие выдуманных товаров
(все объекты имеют ссылку на каталог), соблюдение бюджета (`budget_delta`), стабильность повторной генерации (детерминированная смета).
Датасеты для распознавания комнат и геометрии — после пилота (100–300 проектов с правками дизайнеров).
