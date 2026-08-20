# awe-tuning-parsing

Асинхронний скрапер каталогу [awe-tuning.com](https://www.awe-tuning.com) (Shopify).
Результат — `data/products.xlsx` (по одному рядку на кожен варіант товару) та
`data/products.jsonl` (ті самі дані у "сирому" вигляді, по одному JSON-об'єкту на рядок).

## Швидкий старт

```powershell
# один раз: додати uv в PATH (якщо ще не зроблено)
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Users\SerhiiKhyzhniak\AppData\Roaming\Python\Python310\Scripts", "User")
# перевідкрити термінал, далі:

uv sync              # встановити залежності в .venv
uv run pytest -q     # прогнати тести (17 тестів)
uv run main.py       # повний збір каталогу -> data/products.jsonl + data/products.xlsx
```

Інші корисні команди:

```bash
uv run main.py -c audi -c bmw       # тільки вказані категорії (handle колекції)
uv run main.py -v                   # детальне (debug) логування
uv run main.py --skip-details       # швидко, без сторінок товару й таблиці сумісності
                                     # (tabs/description/auto будуть порожні) — для швидкої перевірки
```

## Як це працює: 3 етапи

### Етап 1. Категорії (`categories.py`)

Завантажується головна сторінка сайту, з неї парситься `nav.header__inline-menu` —
реальне навігаційне меню (а не якась окрема "мапа сайту"). Звідти беруться:
- **бренди авто** з випадайки "Vehicles" (Audi, BMW, Porsche, ...) — 20+ колекцій;
- **типи товарів**: Exhausts, Intakes, Intercoolers, Foiler Wind Diffusers.

Категорія `gear-accessories` (мерч, футболки) навмисно виключена зі збору
(`Settings.excluded_categories`) — можна змінити через `.env`.

### Етап 2. Товари по категоріях (`products.py`, `pipeline.run()`)

Для кожної категорії пагінується офіційний Shopify-ендпоінт
`/collections/{handle}/products.json` (без парсингу HTML — сайт сам віддає
структурований JSON: ціни, варіанти, картинки, теги). Товар, знайдений одразу в
кількох категоріях (наприклад, вихлоп під Audi ще й під Exhausts), не дублюється —
його категорії просто мерджаться в один запис (`Product.categories`,
`Product.vehicle_brands`).

Додатково є "gap-fill" прохід по глобальному `/products.json` — кілька товарів
на сайті не прив'язані до жодної категорії в меню (зняті з продажу позиції,
службові записи типу `awe-shipping-insurance`), і без цього проходу вони б
тихо загубились.

### Етап 3. Збагачення й розбивка на варіанти (`pipeline.enrich_and_explode()`)

Це найважча частина: частина даних (вкладки з описом, "This fits..." таблиця
сумісності) не існує в Shopify JSON — вона рендериться на сторінці товару.
Тому на кожен унікальний товар додатково робиться:

- **Fetch сторінки товару** (`product_page.py`) — HTML-сторінка
  `/products/{handle}`. З неї витягується:
  - **Вкладки** (`#custom-product-tabs`) — сам контейнер порожній (заповнюється
    JS), але на сторінці є вбудований `<script>const data = {"tabs":[...]}</script>`
    з готовим списком `{title, content}` — це і парситься напряму, без браузера.
    Кожна вкладка ("Performance Specs", "180 Technology", ...) стає окремою
    Excel-колонкою з HTML-вмістом.
  - **Installation Instructions** — окремий випадок: замість HTML береться
    список посилань (PDF), відфільтрований від службового лінка на
    `/pages/prop65`. Якщо посилань кілька — колонки `Instruction 1`,
    `Instruction 2`, ...
  - **Опис** (`.halo-productView-right.productView-details.clearfix`) —
    зберігається як форматований текст (переноси рядків, списки), не HTML.
  - **Important Fitment Notes** — параграф з таким текстом всередині опису
    виноситься в окрему колонку. Якщо це лише заголовок-мітка, а сам текст
    йде списком нижче (`<ul>`) — підхоплюється і він.
  - **HTML-блоки варіантів** (`section.product-variants__variant`) — назва,
    SKU, ціна, головне фото для кожного варіанта. Присутні тільки в товарів з
    кількома варіантами (порівняльна таблиця на сторінці); для товарів з одним
    варіантом ці поля беруться напряму з Shopify JSON.
  - **Галерея фото** (`.productView-images .productView-image-portrait.fit-cover`)
    — це загальна галерея товару, де фото ВСІХ варіантів змішані разом (кожен
    файл має SKU в назві, напр. `3020-32429_1.jpg`). Для кожного варіанта вона
    фільтрується по SKU: головне фото лишається `Image 1`, решта знайдених для
    цього SKU фото — `Image 2`, `Image 3`, ... Якщо варіант один — фільтр не
    потрібен, береться вся галерея.

- **Fetch таблиці сумісності** (`compatibility.py`) — таблиця "This fits..."
  теж не в статичному HTML: вона підвантажується JS через AJAX-виклик до
  стороннього сервісу `ymmshopify.capacitywebservices.com` (JSONP), один запит
  на товар, повертає сумісність одразу для всіх його варіантів (рядки з полем
  SKU). З цього рахуються:
  - **`auto`** — тільки `Year||Make||Model`, з розгорткою діапазону років
    (`2019-2024` → 2019,2020,...,2024), у форматі `{2019||BMW||330i,...}`;
  - **`Submodel` / `Engine` / `Body Type` / `Bed Length`** — групування по
    Make: унікальні значення в межах бренду, `N/A` ігнорується, формат
    `Audi: {Base, Avant}, Volkswagen: {GLS, GLX}`; колонка лишається порожньою,
    якщо для всієї таблиці там суцільний `N/A`;
  - **`variant_fits_html`** — та сама таблиця сумісності як HTML, відфільтрована
    під SKU конкретного варіанта.

- **Explode**: кожен `Variant` товару (з Shopify JSON) стає окремим рядком
  результату (`ProductRow`). Спільні для товару поля (опис, категорії, вкладки,
  сумісність) дублюються в кожному рядку; унікальні для варіанта — назва, SKU,
  ціна, фото — беруться з HTML-блоку варіанта (якщо є) або з JSON.

## Колонки в Excel

| Група | Колонки |
|---|---|
| Товар | `product_id`, `variant_id`, `sku`, `title`, `url`, `vendor`, `product_type`, `categories`, `vehicle_brands`, `tags` |
| Ціна/наявність | `price`, `compare_at_price`, `currency`, `in_stock` |
| Фото (динамічні) | `Image 1`, `Image 2`, ... — стільки, скільки максимум фото знайдено для одного варіанта; `Image 1` завжди головне фото цього варіанта |
| Опис | `description` (з Shopify JSON), `details_text` (з HTML-блоку сторінки), `important_fitment_notes` |
| Вкладки (динамічні) | одна колонка на кожну унікальну назву вкладки, знайдену хоч в одному товарі (напр. `Performance Specs`, `180 Technology`, `Lifetime Warranty`, ...) |
| Інструкції (динамічні) | `Instruction 1`, `Instruction 2`, ... — стільки, скільки максимум лінків знайдено в одного товару |
| Сумісність | `auto`, `Submodel`, `Engine`, `Body Type`, `Bed Length`, `variant_fits_html` |
| Дати | `created_at`, `updated_at` |

Динамічні колонки (вкладки/інструкції) обчислюються з фактичних даних кожного
прогону — якщо на сайті з'явиться нова вкладка, вона просто з'явиться новою
колонкою наступного разу.

## Стійкість до збоїв і rate-limit (WAF)

Сайт має захист (WAF), який під час активного скрапінгу почав банити конкретні
TLS/JA3-відбитки браузера (спершу generic `chrome`, потім `chrome131`,
`chrome120` — усі Chrome-варіанти з часом заблокувались; Safari/Firefox/Edge
лишались чистими). Тому `http_client.py`:

- на **кожен** запит (і кожен ретрай) обирає випадковий fingerprint з
  `Settings.impersonate_pool` (`safari18_0`, `safari17_0`, `firefox133`,
  `firefox135`, `edge101` — Chrome навмисно виключений);
- при HTTP 429/5xx автоматично повторює запит (до `AWE_MAX_RETRIES` разів,
  експоненційна пауза з джиттером через `tenacity`);
- у `pipeline.py` збій **однієї** категорії чи товару (навіть після всіх
  ретраїв) не валить весь прогін — пишеться warning у лог, і скрипт іде далі
  з рештою.

Якщо весь пул fingerprint'ів колись теж забанять — перевірити наживо, який
відповідає 200:
```powershell
uv run python -c "from curl_cffi.requests import Session; print(Session(impersonate='firefox133').get('https://www.awe-tuning.com/').status_code)"
```
і додати робочий варіант у `AWE_IMPERSONATE_POOL` (`.env`).

## Налаштування (`.env`, копія `.env.example`)

| Змінна | За замовчуванням | Опис |
|---|---|---|
| `AWE_CONCURRENCY` | 2 | скільки запитів одночасно в польоті |
| `AWE_REQUEST_DELAY` | 0.6 | пауза перед кожним запитом (сек) |
| `AWE_MAX_RETRIES` | 6 | спроб на запит при 429/5xx |
| `AWE_IMPERSONATE_POOL` | `["safari18_0",...]` | JSON-масив fingerprint'ів для ротації |
| `AWE_EXCLUDED_CATEGORIES` | `["gear-accessories"]` | JSON-масив категорій, які пропускаються |
| `AWE_TIMEOUT` | 20.0 | таймаут запиту (сек) |

Значення підібрані обережно (низька конкурентність, велика пауза) саме через
WAF — якщо сайт довго не банить, можна обережно підняти `AWE_CONCURRENCY`.

## Структура проєкту

```
main.py                          # `uv run main.py` — точка входу
src/awe_tuning_parsing/
  config.py                      # Settings (.env, префікс AWE_)
  http_client.py                 # curl_cffi + ротація fingerprint + семафор + retry
  models.py                      # Category / Product / Variant / Image / ProductRow (pydantic)
  categories.py                  # header__inline-menu -> категорії
  products.py                    # пагінація collections/*/products.json -> Product
  description.py                 # body_html -> текст (selectolax)
  product_page.py                # HTML сторінки товару -> tabs, опис, fitment notes, HTML-варіанти
  compatibility.py               # AJAX-таблиця сумісності -> auto + групування по Make
  pipeline.py                    # оркестрація: категорії -> товари -> enrich -> explode
  storage.py                     # запис/читання JSONL + Excel (динамічні колонки)
  cli.py                         # typer CLI
tests/                           # pytest, 17 тестів (фікстури — реальні HTML/JSON з сайту)
```

Кожен модуль відповідає за одну річ — можна міняти, наприклад, розкладку
Excel-колонок (`storage.py`) не чіпаючи логіку скрапінгу.

## Тести

```bash
uv run pytest -q
```
