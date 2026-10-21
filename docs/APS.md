# Autodesk Platform Services (APS)

Интеграция обязательна для профессионального контура: импорт исходников бюро и выпуск DWG.
Код: `apps/api/app/aps/client.py`, задачи `jobs/documents.py` (`aps_dwg`, `aps_translate`), UI — `ApsViewer.tsx`,
вкладка «Autodesk APS» в админке, кнопка «DWG через Autodesk APS» на экране документов.

## Что используется

| Сервис APS | Для чего | Эндпоинты |
|---|---|---|
| Authentication v2 (2-legged) | серверный токен; браузеру — только `viewables:read` | `POST /authentication/v2/token` |
| OSS (Object Storage) | хранение исходников и результатов | `POST /oss/v2/buckets`, `GET/POST …/signeds3upload`, `GET …/signeds3download` |
| Model Derivative | DWG/DXF/RVT/IFC → SVF2 для APS Viewer; свойства модели → помещения/площади | `POST /modelderivative/v2/designdata/job`, `GET …/manifest`, `…/metadata`, `…/metadata/{guid}/properties` |
| Design Automation for AutoCAD | DXF (наш экспорт) → нативный DWG | `POST /da/us-east/v3/workitems`, Activity `FormaDxfToDwg+prod` |
| APS Viewer v7 | просмотр исходника и выпущенного DWG в браузере | `viewer3D.min.js` |

## Настройка

1. Создайте приложение на <https://aps.autodesk.com/myapps> (Server-to-Server) с API: Data Management, Model Derivative, Design Automation.
2. В `.env`:
   ```env
   APS_CLIENT_ID=…
   APS_CLIENT_SECRET=…
   APS_BUCKET_KEY=forma-projects-<уникально>   # необязательно
   ```
3. Перезапустите API. В «Платформа → Autodesk APS» нажмите **«Проверить OAuth и bucket»**, затем
   **«Создать/обновить Activity (DXF→DWG)»** (идемпотентно: создаёт Activity или новую версию и переводит alias `prod`).
4. Для никнейма Design Automation (если задан в аккаунте) укажите `APS_DA_NICKNAME`.

## Потоки

**Импорт (DWG/RVT/IFC):** загрузка в проект → `aps_translate`: OSS upload → translate SVF2 → manifest → properties →
`extract_rooms()` (Revit Rooms / IfcSpace / Spaces: имя, номер, площадь, уровень) → помещения доступны на экране
проверки геометрии, исходник открывается во вкладке «Исходник (Autodesk APS)».

**Выпуск DWG:** версия варианта → наш DXF (слои AIA: `A-WALL`, `A-WALL-DEMO`, `A-WALL-NEW`, `A-DOOR`, `A-GLAZ`, `A-AREA`, `I-FURN`,
`E-POWR`, `E-LITE`, `P-PLMB`, `M-HVAC`) → OSS → WorkItem (`accoreconsole /i input.dxf /s script` → `SAVEAS 2018 result.dwg`)
→ complete upload → SVF2 для просмотра → `Document(kind=dwg)`.

## Возможности по статусам

| Возможность | Метка | Доказательство |
|---|---|---|
| DXF → DWG (Design Automation for AutoCAD) | **Export supported** (DWG), VERIFIED live | WorkItem `success`, `samples/demo_aps.dwg` (AC1032) |
| Просмотр DWG/DXF/RVT/IFC в APS Viewer (SVF2) | **View/translate supported** | manifest `success` для выпущенного DWG; RVT/IFC — mock-тесты |
| Помещения и площади из RVT/IFC (Rooms / IfcSpace) | **Metadata extraction supported** (не проверено на живом файле) | `test_aps.py` (mock) |
| Редактируемый семантический импорт стен/проёмов из RVT/IFC | **Editable semantic import pending** | — |
| IFC / RVT экспорт | **Export pending** | — |

## Честные ограничения

* Без ключей APS кнопки DWG и импорт RVT/IFC **отключены с объяснением** (HTTP 409), фиктивные файлы не создаются.
* Скрипт Activity проверен по документации AutoCAD Core Console; первый реальный WorkItem проверьте через `reportUrl` в ошибке задачи.
* Геометрия стен из RVT/IFC в MVP не перестраивается автоматически: импортируются помещения и площади, стены — по DXF-экспорту
  бюро или вручную по подложке APS Viewer (следующий шаг — IfcOpenShell для IFC и Revit Design Automation для RVT).

Тесты: `tests/test_aps.py` (mock-транспорт: токен кэшируется, upload/translate/workitem, кодирование URN, извлечение помещений).
