"""Page «🔌 Подключения» — detailed walkthroughs for the two browser-side
helpers that bridge EHR.ee + Teatmik.ee to TADF without copy/paste:

  1. **Bookmarklet** — single-line JS, drag-to-bookmarks-bar install,
     1 click per lookup.
  2. **Tampermonkey userscript** — hosted under `assets/userscripts/`,
     installed via the Tampermonkey extension, 0 clicks per lookup.

Why two? Different installation friction profiles:
  - Bookmarklet wins on "I just want to try this once": no extension,
    works in any browser, take it or leave it.
  - Userscript wins long-term: zero clicks per lookup, auto-runs on the
    matched URLs, easy to update by replacing the file.

Both call the same TADF endpoints — `/api/import-ehr/{audit_id}` and
`/api/import-teatmik/{audit_id}` — using the per-audit token TADF puts
in the URL fragment.
"""

from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402

from app._state import get_current  # noqa: E402

st.title("🔌 Подключения — EHR + Teatmik без копипастов")

st.markdown(
    """
TADF не лазит сам на ehr.ee и teatmik.ee — оба сайта блокируют запросы
с серверов: EHR требует Smart-ID логина (cookies привязаны к сессии),
Teatmik защищён Cloudflare CAPTCHA с привязкой к IP.

Вместо этого — **маленький помощник в вашем браузере**: после того,
как вы залогинились (EHR) или решили CAPTCHA (Teatmik), он считывает
страницу и шлёт данные в текущий аудит TADF. **Никакого копипаста,
никаких паролей, ничего не выходит за пределы вашего браузера.**

Ниже — два варианта установки. Выберите один. Делают они одно и то же,
разница только в удобстве.
"""
)

# ---------------------------------------------------------------------------
# Status — is there an audit currently open? Without it, "Open in EHR"
# buttons elsewhere have no audit_id to bind a token to.
# ---------------------------------------------------------------------------
audit = get_current()
if audit.id is None:
    st.warning(
        "⚠️ Сейчас не открыт ни один сохранённый аудит. Импорт работает "
        "только для **сохранённых** аудитов (нужен `audit_id` для токена). "
        "Создайте или откройте аудит на странице «📝 Новый аудит» и "
        "вернитесь сюда."
    )
else:
    st.success(f"✅ Открыт аудит **#{audit.id}** — данные будут вливаться сюда.")

st.divider()

# ---------------------------------------------------------------------------
# Variant 1 — Bookmarklet
# ---------------------------------------------------------------------------
st.header("📌 Вариант 1: Bookmarklet (закладка-кнопка)")
st.caption(
    "Самый лёгкий способ. Один раз перетаскиваешь кнопку в панель закладок, "
    "потом — **1 клик** на каждой странице EHR/Teatmik."
)

st.markdown(
    """
### Что это

Закладка в браузере, в которую вместо URL зашит маленький JavaScript.
Когда вы кликаете по закладке, скрипт запускается **на текущей странице**
(EHR или Teatmik) — читает данные и отправляет их в TADF.

### Когда использовать
- Хочется попробовать «здесь и сейчас» без установки расширений.
- Работаете на нескольких компьютерах / в разных браузерах.
- Не хочется вообще ничего ставить из стороннего софта.

### Как установить (один раз, ~30 секунд)
"""
)

# The bookmarklet itself — a minified version that postsa to TADF. Token
# is read from URL fragment exactly like the userscript does.
_BOOKMARKLET_SRC = """javascript:(async()=>{const TADF='https://tadf-audit.h2oatlas.ee';const h=location.hash.replace(/^#/,'');let aid=null,tok=null;for(const p of h.split('&')){const[k,v]=p.split('=');if(k==='tadf'&&v){tok=decodeURIComponent(v);const c=tok.split(':');if(c.length===3)aid=parseInt(c[0],10);}}if(!aid){alert('TADF: открой страницу из кнопки в TADF (нет токена в URL)');return;}let payload={},path;if(location.hostname.includes('ehr.ee')){const m=location.pathname.match(/buildings\\/(\\d+)/);if(!m){alert('TADF: это не страница здания EHR');return;}const code=m[1];try{const r=await fetch('/api/building/v3/'+code,{credentials:'include'});payload=r.ok?await r.json():{ehr_code:code,_error:r.status};}catch(e){payload={ehr_code:code,_error:String(e)};}path='/api/import-ehr/';payload.ehr_code=code;}else if(location.hostname.includes('teatmik.ee')){const m=location.pathname.match(/personlegal\\/(\\d+)/);if(!m){alert('TADF: это не карточка компании');return;}const code=m[1];const name=document.querySelector('h1,h2,.company-name')?.textContent?.trim();let addr=null,status=null;document.querySelectorAll('dt,th,.label').forEach(el=>{const t=(el.textContent||'').toLowerCase();const sib=el.nextElementSibling;if(!sib)return;if((t.includes('aadress')||t.includes('адрес'))&&!addr)addr=sib.textContent.trim();if((t.includes('staatus')||t.includes('статус'))&&!status)status=sib.textContent.trim();});payload={reg_code:code,name,address:addr,status};path='/api/import-teatmik/';}else{alert('TADF: эта страница не EHR/Teatmik');return;}try{const r=await fetch(TADF+path+aid,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+tok,'X-Source-URL':location.href},body:JSON.stringify(payload),mode:'cors'});if(r.ok)alert('✅ TADF: данные отправлены в аудит #'+aid+'. Возвращайтесь во вкладку TADF.');else alert('❌ TADF: '+r.status+' '+(await r.text()).slice(0,200));}catch(e){alert('❌ TADF недоступен: '+e);}})();"""

st.markdown(
    """
1. **Откройте панель закладок в браузере.**
   - Chrome / Edge: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>B</kbd>
   - Firefox: <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>B</kbd>
   - Safari: меню *Bookmarks → Show Bookmarks Bar*
2. **Перетащите кнопку ниже на панель закладок.** Drag-and-drop, как
   обычную ссылку.
"""
)

# Streamlit can't render a raw <a href="javascript:..."> in markdown
# (it sanitises it out), so we inject a tiny HTML block. The drag target
# IS the link — drag the green button onto your bookmarks bar.
import html as _html  # noqa: E402

st.components.v1.html(
    f"""
<a href="{_html.escape(_BOOKMARKLET_SRC, quote=True)}"
   onclick="alert('Не кликай — перетащи на панель закладок!'); return false;"
   style="display:inline-block;padding:12px 22px;background:#16a34a;color:white;
          font-weight:bold;border-radius:6px;text-decoration:none;
          font-family:system-ui,sans-serif;font-size:15px;
          box-shadow:0 2px 6px rgba(0,0,0,.15);user-select:none;cursor:grab;">
   📥 TADF Connector → перетащи меня в закладки
</a>
<p style="font-size:13px;color:#666;font-family:system-ui,sans-serif;margin-top:12px;">
   👉 <b>Перетащи</b>, не кликай. Если перетащил — кнопка появится в панели закладок.
</p>
""",
    height=130,
)

st.markdown(
    """
3. **Готово.** Закладка лежит в панели и вызывается одним кликом.

### Как пользоваться

1. На странице «🏠 Здание» в TADF: кликните **«🔎 Открыть в EHR»** или
   **«🔎 Открыть в Teatmik»** — TADF откроет нужный сайт в новой вкладке
   с зашитым токеном.
2. На EHR: войдите через Smart-ID. На Teatmik: решите CAPTCHA.
   *(оба требования одноразовые — Keycloak помнит вас ~30 дней,
   Cloudflare — ~30 минут)*
3. **Кликните по закладке** «📥 TADF Connector».
4. Появится `alert('✅ TADF: данные отправлены...')` — вернитесь во
   вкладку TADF. Данные уже в аудите как превью «принять / отклонить».

### Ограничения
- Закладка не запоминается, если вы перетащили её в Incognito-окно.
- Браузеры на iOS (Safari) поддерживают bookmarklets ограниченно —
  работает, но drag-and-drop сложнее (нужно вручную создать закладку
  и вставить JS-код в URL-поле).
"""
)

with st.expander("🔍 Показать исходный код bookmarklet"):
    st.caption(
        "Это будет вшито в закладку. Открытый код, всё прозрачно — никаких "
        "сторонних серверов, никакой телеметрии, только запрос на "
        "tadf-audit.h2oatlas.ee."
    )
    st.code(_BOOKMARKLET_SRC, language="javascript")

st.divider()

# ---------------------------------------------------------------------------
# Variant 2 — Tampermonkey userscript
# ---------------------------------------------------------------------------
st.header("🐒 Вариант 2: Tampermonkey userscript")
st.caption(
    "0 кликов на lookup — скрипт запускается автоматически, как только вы "
    "открываете страницу здания в EHR или карточку компании в Teatmik."
)

st.markdown(
    """
### Что это

[Tampermonkey](https://www.tampermonkey.net/) — популярное расширение
(~10M+ установок), которое запускает на нужных сайтах ваш JavaScript.
Наш userscript автоматически срабатывает на:
- `livekluster.ehr.ee/ui/ehr/v1/buildings/*` (после Smart-ID логина)
- `www.teatmik.ee/et/personlegal/*` (после CAPTCHA)

И отправляет данные в открытый аудит TADF. Вам не надо ничего нажимать
после открытия страницы.

### Когда использовать
- Делаете несколько lookup'ов в день — закладку устаёт нажимать.
- Один основной браузер, в котором всё устроено.
- Не возражаете против установки одного известного расширения.

### Как установить (один раз, ~2 минуты)

#### Шаг 1: Установите Tampermonkey

| Браузер | Ссылка |
|---|---|
| Chrome / Edge / Brave | [chrome.google.com/webstore/.../tampermonkey](https://chromewebstore.google.com/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo) |
| Firefox | [addons.mozilla.org/.../tampermonkey](https://addons.mozilla.org/en-US/firefox/addon/tampermonkey/) |
| Safari | [tampermonkey.net/?browser=safari](https://www.tampermonkey.net/?browser=safari) |

После установки — иконка обезьяны 🐒 в правом верхнем углу.

#### Шаг 2: Установите userscript TADF Connector

Скопируйте код ниже и в Tampermonkey: **Создать новый скрипт →
вставить → Файл → Сохранить** (или `Ctrl+S`).

Альтернатива (для Tampermonkey): просто кликните по ссылке ниже —
Tampermonkey автоматически предложит установить.
"""
)

# Direct-install link — when Tampermonkey is present, clicking a `.user.js`
# file URL triggers the install dialog. We host the script at a stable
# path under the same domain.
_USERSCRIPT_URL = "/api/static/tadf-connector.user.js"
st.markdown(
    f"""
[**📥 Установить TADF Connector userscript**]({_USERSCRIPT_URL})
&nbsp;&nbsp;<small>(если Tampermonkey установлен — откроется диалог установки;
если нет — браузер просто покажет код, его можно вставить в новый скрипт вручную)</small>
"""
)

with st.expander("🔍 Показать исходный код userscript", expanded=False):
    st.caption(
        "150 строк JavaScript. Открытый код, никаких внешних зависимостей. "
        "Файл можно скачать из репо: `assets/userscripts/tadf-connector.user.js`."
    )
    userscript_path = _root / "assets" / "userscripts" / "tadf-connector.user.js"
    if userscript_path.exists():
        st.code(userscript_path.read_text(encoding="utf-8"), language="javascript")
    else:
        st.error("Файл userscript не найден в сборке.")

st.markdown(
    """
### Как пользоваться

1. На странице «🏠 Здание» в TADF: кликните **«🔎 Открыть в EHR»** или
   **«🔎 Открыть в Teatmik»**. TADF откроет нужный сайт в новой вкладке
   с зашитым токеном (`#tadf=…` в URL).
2. На EHR: войдите через Smart-ID. На Teatmik: решите CAPTCHA.
3. **Ничего больше не делайте.** Userscript сам отправит данные в TADF
   и покажет в правом нижнем углу зелёный баннер «✅ Отправлено в TADF».
4. Вернитесь во вкладку TADF — данные уже там как превью «принять / отклонить».

### Обновление

Когда мы обновляем userscript (новые поля, новый сайт):

1. Откройте Tampermonkey → **Установленные** → **TADF Connector**.
2. Нажмите **«Проверить обновления»** (или вкладка `Settings` → `Check for userscript updates`).
3. Если есть новая версия — Tampermonkey установит её сам.

Альтернативно: переустановите по той же ссылке выше.
"""
)

st.divider()

# ---------------------------------------------------------------------------
# Common section — security + privacy
# ---------------------------------------------------------------------------
st.header("🔒 Безопасность и приватность")

st.markdown(
    """
**Что отправляется в TADF:**
- При открытии страницы здания на EHR: **JSON с данными здания**
  (адрес, кадастр, габариты, год, класс огнестойкости и т.д.) и
  ссылка на исходную страницу.
- При открытии карточки компании на Teatmik: **название, рег-код,
  адрес и статус**.
- В обоих случаях — **только то, что на открытой странице**, и только
  в **открытый сейчас аудит TADF**.

**Что НЕ отправляется:**
- ❌ Cookies (ни Keycloak, ни Cloudflare, ни любые другие).
- ❌ Пароли или Smart-ID-данные.
- ❌ История браузера, другие вкладки, локальные файлы.
- ❌ Никакая телеметрия — нет внешних серверов, кроме `tadf-audit.h2oatlas.ee`.

**Авторизация:**
- TADF выдаёт **временный токен** (24 часа) для текущего аудита, когда
  вы кликаете «Открыть в EHR/Teatmik». Токен зашит в URL-фрагмент
  (после `#`) и не виден серверам EHR/Teatmik (они не получают
  фрагменты при HTTP-запросах).
- Если кто-то получит ваш токен — он сможет писать данные **только в
  один конкретный аудит**, не в другие.
- Через 24 часа токен автоматически перестаёт работать.

**Где хранятся cookies EHR/Teatmik:**
- В **вашем** браузере, как обычно. TADF их не видит.
- Smart-ID-логин на EHR → стандартный Keycloak (тот же, что для всех
  государственных порталов Эстонии).
- CAPTCHA на Teatmik → стандартный Cloudflare cookie, привязанный к
  вашему IP.
"""
)

st.divider()

# ---------------------------------------------------------------------------
# Health check — does the API endpoint respond?
# ---------------------------------------------------------------------------
st.header("🩺 Проверка соединения")
if st.button("Проверить, работает ли TADF API"):
    import httpx

    try:
        r = httpx.get("http://127.0.0.1:8001/api/health", timeout=3.0)
        if r.status_code == 200:
            st.success(f"✅ TADF API на этом инстансе работает: {r.json()}")
        else:
            st.warning(f"API ответил {r.status_code}: {r.text}")
    except Exception as e:
        st.error(
            f"❌ Не могу достучаться до API на `:8001` — {type(e).__name__}: {e}\n\n"
            "Это нормально в локальной dev-сборке без uvicorn-сайдкара. "
            "На Hetzner-деплое API запускается автоматически рядом со Streamlit."
        )
