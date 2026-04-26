# Автоматизация аудиторских отчётов TADF — план для разработчика

## Контекст

**TADF** — компания одного человека, занимающаяся строительным надзором в Эстонии (стройнадзор / *ehitusjärelevalve*). Владелец — **Фёдор Соколов** (kutsetunnistus 148515). Сегодня каждый аудиторский отчёт о здании (*ehitise auditi aruanne*) — это документ Word/PDF на 16–60 страниц, который собирается вручную около 1–2 рабочих дней: титульный лист, кадастровые данные, протокол осмотра, технические выводы, проверка пожарной безопасности, фотографии, ссылки на законы, подписи. В папке `/home/anton/projects/tadf/audit/` лежит 12 исторических отчётов в форматах `.docx`, устаревший `.doc`, `.pdf` и подписанные контейнеры `.asice`.

Анализ корпуса и девяти эстонских правовых актов (Ehitusseadustik 105032015001, Ehitise auditi tegemise kord 120102020004, Ehitise dokumendid 118022020009, Nõuded ehitusprojektile 118072015007, Korteriomandiseadus 12742145, Ehitise tehniliste andmete loetelu 110062015008, EhSRS, Tuleohutuse seadus 13314859, Ehitisregistrile esitamise kord 12939670) показал: **примерно 60 % каждого отчёта — это шаблонный текст** (структура разделов, методология, правовая база, подписи, стандартные формулировки) и **40 % — переменная часть** (идентификация объекта, наблюдения, фотографии, выводы, заключения). Закон жёстко регулирует **содержание** (§5 Ehitise auditi tegemise kord перечисляет обязательные поля), но гибок к **форме представления** — это ровно та задача, для которой подходит шаблонизация + структурированный ввод.

**Цель:** превратить 1–2 дня ручной работы над одним отчётом в ≈1 час структурированного ввода + проверки + подписи, оставаясь в правовом поле и сохраняя за Фёдором (юридически подписывающим лицом) полный редакторский контроль над каждым словом отчёта.

**Решения, подтверждённые пользователем:**
- Сначала запускаем локально на ноутбуке; разворачивание на Hetzner — отдельная фаза.
- MVP = шаблон + форма, без LLM, без EHR. Полный пайплайн (LLM, подписание, EHR через X-tee) описан как последующие фазы.
- Загрузка в EHR остаётся ручной до тех пор, пока объём не оправдает членство в X-tee; путь автоматизации задокументирован.
- LLM на фазе 2 закрывает все четыре сценария: черновик повествования, подписи к фото, предложение правовых ссылок, эстонский language-polish.

## Архитектура (целевое состояние, наращивается поэтапно)

```
                            +-------------------+
   выезд на объект (фото) ->| Capture (PWA L8)  |--+
                            +-------------------+  |
                                                   v
   ручной ввод формы ----->+-------------------+  +--> [SQLite/Postgres]
                            | Streamlit UI (L1) |--+        |
                            +-------------------+           |
                                       |                    v
                                       |          [Pydantic context builder]
                                       |                    |
   read-only справочники -> EHR / Maa-amet / Kutsekoda      |
                                       |                    |
                                       v                    v
                            +-----------------------------------+
                            | docxtpl render -> draft.docx (L1) |
                            +-----------------------------------+
                                       |
                            (опционально) LLM-черновики и polish (L2)
                                       |
                                       v
                            +-----------------------------------+
                            | LibreOffice -> PDF -> ASiC-E (L3) |
                            +-----------------------------------+
                                       |
                            +-----------------------------------+
                            | Smart-ID / ID-card подпись (L3)   |
                            +-----------------------------------+
                                       |
                            +-----------------------------------+
                            | EHR upload: ручной L1 -> X-tee L4 |
                            +-----------------------------------+
```

L1 = MVP, L2 = LLM-фаза, L3 = подписание, L4 = автоматический EHR + мобильный сбор данных. Сначала локальный ноутбук; та же кодовая база позже едет в Docker-контейнер на Hetzner — без изменений в архитектуре, только SQLite → Postgres и диск → S3-совместимое хранилище объектов.

## Технологический стек (выбран под одного разработчика)

- **Язык:** Python 3.12. Один язык для всего стека.
- **UI:** `streamlit` — один процесс, запуск на ноутбуке через `streamlit run app/TADF_Ehitus.py`, никакого JS-инструментария. На фазе 5 (Hetzner) тот же UI работает за HTTPS reverse-proxy.
- **Бэкенд:** обычные Python-модули; `fastapi` появляется только когда мобильный сбор (фаза 4) потребует HTTP API.
- **Данные:** `sqlite` + `sqlalchemy` 2.x + миграции `alembic`. Postgres — только при переезде на Hetzner.
- **Валидация/модели:** `pydantic` v2 для in-memory сущностей и контекста шаблона.
- **Шаблонизация:** `docxtpl` (Jinja2 поверх настоящего `.docx`) — сохраняет эстонское форматирование, заголовки, таблицы, разрывы страниц. `python-docx` для вставки изображений и пост-обработки.
- **Рендеринг PDF:** headless `libreoffice --convert-to pdf` (максимальная точность для `.docx`).
- **Подпись (фаза 3):** `pyasice` (обёртка над `libdigidocpp`) для сборки ASiC-E + Smart-ID/Mobile-ID/ID-card; `SiVa` для валидации подписи.
- **LLM (фаза 2):** Python SDK `anthropic` — Sonnet 4.x для черновиков и polish, Haiku 4.5 для подписей к фото и классификации находок. Prompt caching на префиксе boilerplate и фрагментах корпуса.
- **Парсинг корпуса (одноразовый инструмент):** `python-docx` (.docx); `libreoffice --convert-to docx` для миграции legacy `.doc`; `pdfplumber` + `pytesseract` (`est` traineddata) для `.pdf`; стандартный `zipfile` для `.asice`.
- **Внешние клиенты:** `httpx` + `tenacity` для запросов к EHR/Maa-amet/Kutsekoda.
- **Инструменты разработчика:** `uv` для окружения и lockfile, `ruff` для lint/format, `pytest` для тестов, `pre-commit` для хуков. Один `pyproject.toml`.
- **Дистрибуция:** `uv run`-скрипт на ноутбуке Фёдора (фаза 1); `docker compose` на Hetzner (фаза 5).

## Структура проекта

```
tadf/
  pyproject.toml
  README.md
  .env.example                # ANTHROPIC_API_KEY, smartid creds (поздние фазы)
  app/
    main.py                   # streamlit entrypoint + sidebar
    pages/
      1_New_Audit.py          # создание + редактирование метаданных аудита
      2_Building.py           # кадастровые / EHR данные
      3_Capture.py            # фото + наблюдения по разделам
      4_Findings.py           # список находок + правовые ссылки
      5_Review.py             # превью рендера, accept/reject diff
      6_Sign_Submit.py        # PDF + ASiC-E + EHR (фаза 3+)
  src/tadf/
    config.py                 # пути, env vars, feature flags
    models/
      audit.py                # SQLAlchemy + Pydantic
      building.py
      auditor.py
      photo.py
      finding.py
      legal_ref.py
      template_clause.py
    db/
      session.py
      migrations/             # alembic
    intake/
      form_schema.py
      photo_ingest.py         # EXIF, GPS, дедупликация
    corpus/                   # одноразовый разбор архива
      parse_docx.py
      parse_doc.py            # через libreoffice
      parse_pdf.py            # pdfplumber + OCR fallback
      parse_asice.py
      extract_sections.py     # сплиттер по заголовкам
    templates/
      ea_kasutuseelne.docx    # одна мастер-форма на каждый подтип
      ea_korraline.docx
      ea_erakorraline.docx
      partials/
        legal_refs.j2
        methodology.j2
        signatures.j2
      boilerplate.yaml        # версионированные стандартные клаузы
    render/
      context_builder.py      # сущности -> валидированный контекст шаблона
      docx_render.py          # docxtpl + вставка фото
      pdf_convert.py          # headless libreoffice
    legal/
      checklist.py            # покрытие § 5 Ehitise auditi tegemise kord
      validators.py           # межактовые условные правила
      references.yaml         # канонические EhS / EVS / постановления
    llm/                      # фаза 2
      client.py               # обёртка anthropic + JSON-кеш
      prompts/                # *.md шаблоны промптов
      drafters/
        section_arhitektuur.py
        section_tehnosysteemid.py
        section_ulevaatus.py
      classifiers.py          # severity находки + ranked refs
      polish.py               # эстонская корректура + diff
    sign/                     # фаза 3
      asice_builder.py
      smartid_flow.py
      siva_validate.py
    external/                 # фаза 3+
      ehr_client.py           # сначала read-only; X-tee write — фаза 6
      maaamet_client.py
      kutsekoda_client.py
    submit/
      manual_export.py        # фаза 1: открыть final.asice + ehitisregister.ee
      ehr_upload.py           # фаза 6: X-tee POST
  data/                       # gitignored
    audits/<audit_id>/
      photos/
      draft.docx
      final.pdf
      final.asice
      context.json            # полный контекст для воспроизводимости
    corpus/                   # разобранные исторические отчёты как JSON
    cache/llm/                # кеш ответов по hash промпта
  scripts/
    ingest_corpus.py          # /home/anton/projects/tadf/audit/* -> data/corpus
    new_audit.py              # CLI shortcut
    seed_legal_refs.py        # references.yaml -> DB
  tests/
    fixtures/                 # симлинки на /home/anton/projects/tadf/audit/*
    test_render_snapshot.py
    test_legal_checklist.py
    test_corpus_parse.py
    test_template_compile.py
  docker/                     # фаза 5
    Dockerfile
    docker-compose.yml
    caddy/Caddyfile
```

## Модель данных

```
Auditor
  id, full_name, kutsetunnistus_no, qualification (AA-1-01|AA-1-03|AR-3-01|...),
  independence_declaration_text, signature_image_path, id_code, default_role

Audit
  id, seq_no, year, type (EA|EP|TJ|TP|AU), subtype (kasutuseelne|korraline|erakorraline),
  purpose, scope, methodology_version, visit_date, status (draft|review|signed|submitted),
  auditor_id -> Auditor, building_id -> Building, client_id -> Client, created_at, updated_at

Building
  id, address, kataster_no, ehr_code, construction_year, designer, builder,
  footprint_m2, height_m, volume_m3, storeys,
  fire_class (TP-1|TP-2|TP-3), pre_2003 (bool), substitute_docs_note,
  use_purpose, last_renovation_year

Client
  id, name, reg_code, contact_email, contact_phone, address

Photo
  id, audit_id, path, taken_at, gps_lat, gps_lon, hash,
  caption_auditor, caption_llm_draft, section_ref, accepted (bool)

Finding
  id, audit_id, section_ref, severity (info|nonconf_minor|nonconf_major|hazard),
  observation_raw, observation_polished, recommendation,
  legal_ref_ids[], photo_ids[], status (open|resolved)

LegalReference
  id, code (например "EhS § 12", "EVS 812-7"), title_et, url, section_keys[],
  effective_from, superseded_by_id (nullable)

TemplateClause
  id, section_key, audit_type, version, body_md, effective_from

SignedArtifact
  id, audit_id, asice_path, signer_id_code, signed_at,
  validation_ok, ehr_submission_ref (nullable)
```

Декодированные коды из имён файлов корпуса: **EA** = Ehitise Audit, **EP** = Ehitusprojekti audit, **TJ** = Tehniline järelevalve, **TP** = Tehniline projekt, **AU** = аудит институциональных объектов. Лицензионные коды **AA-1-01** / **AA-1-03** / **AR-3-01** соответствуют уровням квалификации аудитора и хранятся в `Auditor.qualification`. Парсер корпуса заполняет lookup-таблицу, которую форма нового аудита использует для автодополнения.

## Структура отчёта -> карта шаблона

16 разделов скелета, извлечённого из корпуса, отображаются 1:1 на docxtpl-шаблон. Каждый раздел — либо чистый boilerplate (B), либо чистая переменная часть (V), либо boilerplate-со-слотами (BS).

| # | Раздел (эстонский) | Тип | Источник содержимого |
|---|---|---|---|
| 1 | Tiitelleht | BS | Сущности Audit + Building + Auditor |
| 2 | Sisukord | B | Word-поле, обновляется при открытии |
| 3 | Üldosa (eesmärk, audiitor, ulatus) | BS | `boilerplate.yaml` + поля Audit |
| 4 | Auditi objekt ja kirjeldus | BS | Building + Audit.purpose + LLM-черновик L2 |
| 5 | Kinnistu asukoht ja planeering | V | Building.kataster_no -> Maa-amet auto-fill (L3) |
| 6 | Hoone ülevaatus | V | Findings + Photos; LLM narrative (L2) |
| 7 | Arhitektuuri- ja ehituslik osa | V | Findings по подразделам (vundament, seinad, vahelaed, katus, viimistlus, aknad/uksed); LLM narrative (L2) |
| 8 | Tehnosüsteemid | V | Findings по подсистемам (vesi, kanal, elekter, küte, vent); LLM narrative (L2) |
| 9 | Tulekaitse | BS | Building.fire_class определяет partial; условный по типу использования (Tuleohutuse seadus) |
| 10 | Tehnilised näitajad | V | Building.footprint_m2 / volume_m3 / storeys (по RT 110062015008) |
| 11 | Kokkuvõte | V | **Только аудитор.** LLM polish тоже отключён |
| 12 | Õiguslikud alused | B | `legal/references.yaml` отфильтровано по audit_type + effective_from |
| 13 | Metoodika | B | `boilerplate.yaml`, поле methodology_version |
| 14 | Lõpphinnang | V | **Только аудитор.** Без LLM, без шаблона. Свободный текст за §5 checklist |
| 15 | Allkirjad | BS | Сущность Auditor; изображение подписи; подписывается на шаге sign (L3) |
| 16 | Fotod | V | Галерея с подписями, сгруппированы по section_ref |

Разделы 11 и 14 — юридически нагруженные оценки, по дизайну только человеческие.

## Интеграция LLM (фаза 2)

Claude используется там, где экономит набор текста, и никогда — там, где лежит юридическая ответственность. Любой вывод LLM рендерится как **diff против ввода аудитора** с явным accept/reject; ничего не попадает в финальный DOCX без клика.

**Сценарии (включены все четыре, по решению пользователя):**

1. **Черновик повествования** (разделы 4, 6, 7, 8): аудитор вводит маркированные наблюдения и помеченные фото -> Claude Sonnet раскрывает в формальную эстонскую прозу с few-shot примерами из исторического корпуса. Системный промпт фиксирует регистр, терминологию и структуру конкретного раздела.
2. **Подписи к фото + предложение раздела:** каждое новое фото проходит через Claude Haiku — вход: изображение + краткая заметка аудитора; выход: эстонская подпись + предлагаемый `section_ref`. Аудитор подтверждает в галерее.
3. **Предложение правовых ссылок:** `observation_raw` каждой Finding идёт в classifier-промпт, который возвращает ranked-кандидатов из таблицы `LegalReference` (модель никогда не *генерирует* цитаты — только ранжирует существующие). Аудитор выбирает.
4. **Эстонский polish:** опциональный финальный проход по тексту аудитора для грамматики, терминологии, формальности. Показывается diff.

**Кеширование:** Anthropic prompt caching на длинном стабильном префиксе (system instructions + фрагменты корпуса + boilerplate + канонический список цитат); per-request suffix — небольшой переменный ввод. Постоянный JSON-кеш в `data/cache/llm/` по ключу `sha256(model + prompt + section_key)` устраняет повторы при ре-рендере одного аудита.

**Границы ответственности:** разделы 11 (Kokkuvõte) и 14 (Lõpphinnang), а также декларация независимости — пишутся только аудитором; никакого LLM-черновика, никакого polish. Блок методологии (раздел 13) фиксирует, что LLM-помощь была использована и что весь сгенерированный текст был просмотрен и одобрен подписывающим аудитором.

**Будущие точки улучшения через LLM (по запросу пользователя — задокументировано):**
- *Голос-в-тезисы на объекте* (Whisper API): надиктовать наблюдения в микрофон, получить структурированные тезисы, готовые к narrative-черновику.
- *Кластеризация мульти-фото для одной находки*: схожие фото объединяются в одну Finding с несколькими photo_ref.
- *Кросс-аудитное обучение паттернам*: «такая же проблема была в аудите X в прошлом месяце» — для согласованности.
- *Автоматическая кросс-ссылка между разделами*: добавлена Finding в раздел 7 — предложить соответствующую строку в раздел 11.
- *Compliance pre-check перед рендером*: dry-run §5 checklist и условных правил Tuleohutuse seadus с объяснением, чего не хватает.
- *Помощь по русско-эстонской терминологии*: полезно для клиентских резюме, поскольку многие клиенты русскоязычные.
- *Детектор изменений в законодательстве*: ежемесячная Claude-задача делает diff URL-ов riigiteataja и сигнализирует об изменениях, которые касаются `legal/references.yaml`.

## Пайплайн вывода

1. **Валидация** — `legal/checklist.py` запускает проверку покрытия по § 5 Ehitise auditi tegemise kord на Pydantic-контексте. Отсутствующие обязательные поля блокируют рендер со списком, ведущим обратно на страницы формы.
2. **Рендер** — `render/docx_render.py` вызывает `docxtpl` против мастер-шаблона подтипа аудита, встраивает фото через `python-docx`, пишет `data/audits/<id>/draft.docx`. Sisukord (TOC) — это Word-поле, обновляется при первом открытии.
3. **Проверка** — аудитор открывает DOCX в Word/LibreOffice для финальных правок формулировок, которые форма не покрывает; сохраняет в тот же путь.
4. **PDF-конвертация** — `render/pdf_convert.py` запускает headless LibreOffice против финального DOCX -> `final.pdf`.
5. **Подпись** (фаза 3) — `sign/asice_builder.py` собирает `final.pdf` (и манифест оригиналов фото при желании) в ASiC-E контейнер; `sign/smartid_flow.py` ведёт аудитора по подписи Smart-ID/ID-card; `sign/siva_validate.py` подтверждает валидность.
6. **Подача** — фаза 1: `submit/manual_export.py` открывает `final.asice` в файловом менеджере и ehitisregister.ee в браузере; аудитор загружает. Фаза 6: `submit/ehr_upload.py` POST по X-tee.

Каждый артефакт (`context.json`, `draft.docx`, `final.pdf`, `final.asice`, квитанция о подписи) живёт в `data/audits/<id>/` все 7 лет обязательного хранения. Опциональный ночной скрипт rsync копирует в шифрованное off-site хранилище.

## Поэтапная дорожная карта

### Фаза 1 — Локальный MVP (5–7 рабочих дней)
**Цель:** экономия времени уже на следующем реальном аудите.
- Скелет проекта, `pyproject.toml`, `uv` env, ruff/pytest, инициализация Alembic.
- Парсер корпуса: разобрать 12 исторических отчётов из `/home/anton/projects/tadf/audit/` в `data/corpus/*.json`. Использовать корпус чтобы (a) зафиксировать таксономию разделов, (b) извлечь реальные boilerplate-строки, (c) засеять `legal/references.yaml` цитатами, которые Фёдор реально использует.
- Один docxtpl мастер-шаблон: **`ea_kasutuseelne.docx`** (наиболее частый подтип по корпусу).
- Streamlit UI страницы 1–5 (без Sign/Submit пока); SQLite + Pydantic модели для Audit, Building, Auditor, Photo, Finding.
- `legal/checklist.py` enforcing обязательные поля §5.
- Render -> DOCX. Ручная PDF-конвертация через LibreOffice. Ручная подпись + загрузка.
- README с инструкциями по установке/запуску с ноутбука + 1-страничная how-to для Фёдора на русском.
- **Верификация:** ре-рендер 3 отчётов из корпуса по извлечённому контексту; Фёдор сравнивает side-by-side.
- **Результат:** ≈70 % сокращение набора текста; всё остальное — как сегодня.

### Фаза 2 — LLM-помощник (4–6 дней)
**Цель:** дополнительно сократить набор текста в narrative-разделах.
- `llm/client.py` с постоянным JSON-кешем + Anthropic prompt caching.
- Drafters для разделов 4, 6, 7, 8 с few-shot примерами из корпуса.
- Подписи к фото (Haiku) + предложение section-placement в галерее.
- Classifier находок, возвращающий ranked правовые ссылки из курируемой таблицы.
- Эстонский polish с side-by-side diff.
- «AI-assist toggle» по каждому разделу — Фёдор может отключить в любой момент.
- **Верификация:** оценка качества на 3 отчётах из корпуса — генерируем из «голых» тезисов, оцениваем эстонскую грамматику/терминологию против оригинала. Фёдор подписывает регистр.

### Фаза 3 — Пайплайн подписания (5–8 дней)
**Цель:** перестать выходить из приложения для финальной выдачи.
- `sign/asice_builder.py` через `pyasice`/`libdigidocpp`.
- `sign/smartid_flow.py` для Smart-ID (наиболее частый); ID-card и Mobile-ID как альтернативы.
- `sign/siva_validate.py` подтверждает подписанный контейнер.
- Страница «Sign & Submit» экспортирует валидированный `.asice`, открывает ehitisregister.ee для **ручной** загрузки (по решению пользователя — оставляем ручной до X-tee).
- **Верификация:** подписать тестовыми сертификатами против SiVa demo; round-trip реального `.asice` из исторического аудита и подтвердить, что валидация совпадает.

### Фаза 4 — Мобильный сбор данных (5–10 дней)
**Цель:** фото + наблюдения вводятся на объекте, а не после.
- Тонкий FastAPI слой с `/upload-photo`, `/add-observation`, `/list-audits` и token-auth, ограниченным одним аудитом.
- Минимальный PWA (HTML + немного Alpine/htmx, без React) — чек-лист зеркалит список разделов, нативное фотографирование.
- Фото попадают в `data/audits/<id>/photos/` с EXIF; наблюдения цепляются к черновой Finding.
- Опциональный Whisper voice-to-bullet для hands-free.
- **Верификация:** полевой тест с Фёдором на реальном выезде.

### Фаза 5 — Развёртывание на Hetzner (3–5 дней)
**Цель:** доступ откуда угодно, автоматические бэкапы.
- Hetzner CX22 (или CAX11 ARM, ~€4/мес) в Helsinki/Falkenstein (EU = проще GDPR).
- `docker compose`: app-контейнер + Postgres + Caddy reverse-proxy с auto-TLS.
- Объектное хранилище: Hetzner Storage Box (дёшево) или Cloudflare R2 для фото; SQLite мигрирует в Postgres через Alembic.
- Auth: `streamlit-authenticator` (один пользователь) или Caddy `forward_auth` к Authelia, если когда-нибудь понадобится мульти-юзер.
- Ежедневный шифрованный off-site backup (`restic` во второй Storage Box) для 7-летнего хранения.
- Домен: `audit.tadf.ee` или похожий; HTTPS везде.
- **Верификация:** dry-run с тестовым (не настоящим) аудитом; учения по восстановлению из бэкапа.

### Фаза 6 — Автоматизация EHR через X-tee (переменная длительность; зависит от RIA)
**Цель:** убрать последний ручной шаг.
- Подать заявку на членство в X-tee для TADF (процесс RIA — недели или месяцы для частного предпринимателя).
- Реализовать `submit/ehr_upload.py` против соответствующих `KIRA` сервисов для загрузки `ehitise auditi aruanne`.
- VCR-recorded тесты против тестового окружения X-tee перед любым production POST.
- Оставить ручную загрузку как fallback при недоступности X-tee.
- **Верификация:** подать один реальный аудит через X-tee с параллельной ручной загрузкой как safety net в первые ≈3 месяца.

### Фаза 7 — Удобство и кросс-аудитная аналитика (постоянно)
- Voice-to-bullet (Whisper) на объекте.
- Кросс-аудитный паттерн-серфинг («похожая проблема в прошлом месяце на X»).
- Автоматическая кросс-ссылка между разделами.
- Помощь по русско-эстонской терминологии для русскоязычных клиентов.
- Ежемесячная задача детектора изменений в `legal/references.yaml` против riigiteataja.
- Поддержка нескольких шаблонов: `ea_korraline`, `ea_erakorraline`, `tj_*`, `tp_*`, `au_*` по частоте подтипов в корпусе.
- Инструмент миграции legacy `.doc` для исторического архива (просмотр + переиспользование старых находок как шаблонов).

## План верификации

End-to-end проверки на каждой фазе:

- **Точность шаблона:** snapshot-тест рендерит fixture-аудит и `xml-diff`-ит против закоммиченного `expected.docx`. Ловит случайные регрессии шаблона.
- **Покрытие закона:** `legal/checklist.py` запускается в CI на каждом fixture-аудите; падение означает, что обязательное поле §5 пропущено в контексте.
- **Регрессия по корпусу:** для каждого из 12 исторических отчётов — ingest -> восстановить контекст -> ре-рендер -> Фёдор подписывает side-by-side, что регенерированный DOCX был бы приемлем. Это главный gate «полезна ли система?» перед стартом фазы 1.
- **Качество LLM (фаза 2):** генерируем разделы 4/6/7/8 из «голых» тезисов, извлечённых из 3 исторических аудитов; Фёдор оценивает эстонский регистр и техническую точность; сохраняем eval-набор в `tests/llm_eval/` для регрессии при каждом изменении промпта.
- **Подписание (фаза 3):** SiVa валидирует произведённый ASiC-E в CI с тестовыми сертификатами; round-trip ASiC-E из одного из 3 исторических `.asice` файлов и подтверждение совпадения структуры.
- **EHR (фазы 4/6):** никаких production-вызовов до одобрения RIA; `vcrpy`-recorded ответы против тестового X-tee; первые 3 месяца ручная загрузка идёт параллельно как safety net.
- **Backup/restore drill (фаза 5):** ежемесячное автоматическое восстановление прошлоночного бэкапа в throwaway VM; подтверждает реальность 7-летнего хранения.

Локальный запуск: `uv run pytest`, `uv run streamlit run app/TADF_Ehitus.py`, `uv run python scripts/ingest_corpus.py`.

## Риски и открытые вопросы

- **Юридическая ответственность за AI-сгенерированный текст.** Митигация: разделы 11 (Kokkuvõte) и 14 (Lõpphinnang) — только аудитор. Любой LLM-вывод diff-ится и явно принимается до рендера. Блок методологии фиксирует, что AI-помощь использовалась и проверялась. Подтвердить с Фёдором, что это удовлетворяет его страховщика профессиональной ответственности.
- **UX подписи отца.** Нужно подтвердить, что он использует — ID-card, Mobile-ID или Smart-ID. Определяет, какой `pyasice` flow реализуется первым в фазе 3.
- **Членство в X-tee для частного предпринимателя (TADF).** Сроки одобрения RIA неизвестны; может заблокировать фазу 6 на неопределённый срок. Ручная загрузка остаётся запасным вариантом. Открытый вопрос: TADF — это OÜ или FIE? Влияет на eligibility в X-tee.
- **Качество эстонского у Claude.** Валидируем на корпусе из 12 отчётов перед использованием на живых аудитах. Если качество пограничное — ограничиваем LLM раскрытием тезисов (меньше риска чем free-form drafting) и сильнее опираемся на polish-only режим.
- **Точность парсинга legacy `.doc`.** Метаданные 1995 года в корпусе намекают, что эти файлы прошли через много версий Word. Используем LibreOffice-конвертацию для ингеста; не доверяем распарсенному тексту как авторитетному — это только справочный материал.
- **Рост хранилища фото.** ≈30 аудитов/мес × ≈50 фото × ≈5 MB ≈ 7.5 GB/мес. Локальный диск ноутбука хватит на годы; Hetzner Storage Box (фаза 5) обрабатывает это за копейки.
- **GDPR / резидентство данных.** Данные владельца здания — персональные данные. Local-only (фаза 1) обходит вопрос; Hetzner EU regions (фаза 5) держит их в EU. Документируем расписание хранения (7 лет аудиты, 5 лет fire-safety) и процедуру удаления для клиентов после истечения срока.
- **Покрытие кодов в именах файлов.** Наблюдаемых пять префиксов типов (EA/EP/TJ/TP/AU) и три кода лицензии (AA-1-01/AA-1-03/AR-3-01). Возможно, понадобятся подтипы после разговора с Фёдором — оставляем `Audit.type` и `Auditor.qualification` как free-text-with-suggestions, не enum, чтобы избежать миграций.
- **Тяжёлые `.docx` с фото.** Некоторые исторические отчёты — 10–20 MB DOCX со встроенными фото. Render pipeline уже обрабатывает это через `python-docx` image embed; просто планируем диск и следим за производительностью самого Word.

## Файлы, которые будут созданы (критические)

- `/home/anton/projects/tadf/pyproject.toml`
- `/home/anton/projects/tadf/app/TADF_Ehitus.py`
- `/home/anton/projects/tadf/src/tadf/models/audit.py`
- `/home/anton/projects/tadf/src/tadf/templates/ea_kasutuseelne.docx`
- `/home/anton/projects/tadf/src/tadf/templates/boilerplate.yaml`
- `/home/anton/projects/tadf/src/tadf/legal/checklist.py`
- `/home/anton/projects/tadf/src/tadf/legal/references.yaml`
- `/home/anton/projects/tadf/src/tadf/render/context_builder.py`
- `/home/anton/projects/tadf/src/tadf/render/docx_render.py`
- `/home/anton/projects/tadf/src/tadf/corpus/parse_docx.py`
- `/home/anton/projects/tadf/scripts/ingest_corpus.py`
- `/home/anton/projects/tadf/tests/test_legal_checklist.py`
- `/home/anton/projects/tadf/tests/test_render_snapshot.py`

## Справочные файлы (read-only, исходный корпус)

- `/home/anton/projects/tadf/audit/012026_EP_AA1-01_Energeetik2AÜ74Narva-Jõesuu_Audit_2026-01-20.docx` — современный .docx, идеальная первая цель для парсера.
- `/home/anton/projects/tadf/audit/100825_TJ_AA-1-01_Auga_8_Narva-Joesuu_Audit_2025-08-10.pdf` — PDF-эталон для валидации OCR.
- `/home/anton/projects/tadf/audit/J. V. Jannseni tn 29aAUDIT.asice` — подписанный контейнер для интеграции с `pyasice`.
- Все 12 файлов вместе образуют eval-корпус для верификации фазы 1 и few-shot пул для фазы 2.
