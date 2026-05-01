/* OMEGA-3 AI floating chat widget — инжектится nginx-ом во все HTML-ответы OM.
 * Кнопка появляется только после авторизации пользователя в OpenMetadata. */
(function () {
  if (window.__omega3AiWidget) return;
  window.__omega3AiWidget = true;

  var STYLE = '\
    #omega3-ai-fab{position:fixed!important;right:24px!important;bottom:24px!important;\
      width:56px;height:56px;border-radius:50%;background:#7147e8;color:#fff;border:0;\
      cursor:pointer;box-shadow:0 6px 18px rgba(113,71,232,.35);z-index:2147483647;\
      display:flex;align-items:center;justify-content:center;\
      font:600 14px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;\
      transition:transform .15s ease, box-shadow .15s ease;}\
    #omega3-ai-fab:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(113,71,232,.45);}\
    #omega3-ai-fab .omega3-ai-fab-text{letter-spacing:.5px;}\
    #omega3-ai-panel{position:fixed!important;right:24px!important;bottom:96px!important;\
      width:420px;height:640px;background:#fff;border-radius:14px;\
      box-shadow:0 16px 50px rgba(20,20,40,.28);display:none;z-index:2147483647;\
      overflow:hidden;border:1px solid #e5e5ec;}\
    #omega3-ai-panel.open{display:flex;flex-direction:column;}\
    #omega3-ai-panel iframe{width:100%;height:100%;border:0;flex:1;}\
    #omega3-ai-close{position:absolute;top:8px;right:10px;background:transparent;\
      border:0;font-size:18px;cursor:pointer;color:#888;z-index:2;}\
    #omega3-ai-close:hover{color:#222;}\
    @media (max-width:560px){\
      #omega3-ai-panel{right:8px!important;left:8px!important;bottom:88px!important;\
        width:auto;height:75vh;}\
    }';

  // Маршруты OM, на которых пользователь ещё не залогинен.
  var UNAUTH_PATH_RE = /^\/(signin|signup|forgot-password|reset-password|account|saml|callback)(\/|$)/;

  function ensureStyle() {
    if (document.querySelector('style[data-omega3-ai]')) return;
    var s = document.createElement('style');
    s.setAttribute('data-omega3-ai', '1');
    s.textContent = STYLE;
    (document.head || document.documentElement).appendChild(s);
  }

  // Читает access token напрямую из IndexedDB, в которую OM service worker
  // пишет app_state. Тот же путь, которым пользуется сам SPA (см. app-worker.js
  // → DB_NAME='AppDataStore', STORE_NAME='keyValueStore', key='app_state').
  function readOmAccessToken() {
    return new Promise(function (resolve) {
      if (!('indexedDB' in window)) return resolve(null);
      var openReq;
      try {
        openReq = indexedDB.open('AppDataStore', 1);
      } catch (e) { return resolve(null); }
      openReq.onerror = function () { resolve(null); };
      openReq.onblocked = function () { resolve(null); };
      openReq.onsuccess = function () {
        var db = openReq.result;
        try {
          if (!db.objectStoreNames.contains('keyValueStore')) {
            db.close();
            return resolve(null);
          }
          var tx = db.transaction(['keyValueStore'], 'readonly');
          var store = tx.objectStore('keyValueStore');
          var getReq = store.get('app_state');
          getReq.onerror = function () { try { db.close(); } catch (e) {} resolve(null); };
          getReq.onsuccess = function () {
            var raw = getReq.result;
            try { db.close(); } catch (e) {}
            if (!raw) return resolve(null);
            try {
              var parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
              resolve(parsed && parsed.primary ? parsed.primary : null);
            } catch (e) { resolve(null); }
          };
        } catch (e) {
          try { db.close(); } catch (e2) {}
          resolve(null);
        }
      };
    });
  }

  function isAuthRoute() {
    return !UNAUTH_PATH_RE.test(location.pathname);
  }

  function isAuthed() {
    if (!isAuthRoute()) return Promise.resolve(false);
    return readOmAccessToken().then(function (t) { return !!t; });
  }

  function removeWidget() {
    var fab = document.getElementById('omega3-ai-fab');
    var panel = document.getElementById('omega3-ai-panel');
    if (fab) fab.remove();
    if (panel) panel.remove();
  }

  function build() {
    if (!document.body) return false;
    ensureStyle();
    if (document.getElementById('omega3-ai-fab')) return true;

    var fab = document.createElement('button');
    fab.id = 'omega3-ai-fab';
    fab.title = 'AI помощник по каталогу';
    fab.setAttribute('aria-label', 'Открыть AI чат');
    fab.innerHTML = '<span class="omega3-ai-fab-text">AI</span>';

    var panel = document.createElement('div');
    panel.id = 'omega3-ai-panel';
    panel.innerHTML =
      '<button id="omega3-ai-close" aria-label="Закрыть">×</button>' +
      '<iframe src="/omega3-ai/" title="OMEGA-3 AI Chat" loading="lazy"></iframe>';

    fab.addEventListener('click', function () {
      panel.classList.toggle('open');
    });
    panel.querySelector('#omega3-ai-close').addEventListener('click', function () {
      panel.classList.remove('open');
    });

    document.body.appendChild(fab);
    document.body.appendChild(panel);
    return true;
  }

  function syncVisibility() {
    isAuthed().then(function (authed) {
      if (authed) build();
      else removeWidget();
    });
  }

  // Hook history API, чтобы реагировать на SPA-навигацию (push/replace State
  // не генерируют событий по умолчанию — патчим, генерируем CustomEvent).
  function patchHistory() {
    if (window.__omega3HistoryPatched) return;
    window.__omega3HistoryPatched = true;
    ['pushState', 'replaceState'].forEach(function (m) {
      var orig = history[m];
      history[m] = function () {
        var r = orig.apply(this, arguments);
        window.dispatchEvent(new Event('omega3:locationchange'));
        return r;
      };
    });
    window.addEventListener('popstate', function () {
      window.dispatchEvent(new Event('omega3:locationchange'));
    });
  }

  function start() {
    patchHistory();
    syncVisibility();

    // Реакция на SPA-навигацию.
    window.addEventListener('omega3:locationchange', syncVisibility);

    // Реакция на login/logout: периодический re-check + storage event на случай,
    // если другая вкладка залогинилась/вышла. IndexedDB-события не пробрасываются,
    // поэтому без поллинга не обойтись, но интервал большой.
    setInterval(syncVisibility, 5000);

    // Если SPA очистит body при роутинге — восстанавливаем виджет (если залогинен).
    if (document.body) {
      var observer = new MutationObserver(function () {
        if (!document.getElementById('omega3-ai-fab')) {
          syncVisibility();
        }
      });
      observer.observe(document.body, { childList: true, subtree: false });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
