/**
 * Envision OS — Rebranding
 * Strips "(Open WebUI)" from all visible text and the page title.
 */
(function () {
  'use strict';
  var RE = / *\(Open WebUI\)/g;

  function clean(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while ((node = walker.nextNode())) {
      if (RE.test(node.textContent)) {
        node.textContent = node.textContent.replace(RE, '');
      }
    }
    if (RE.test(document.title)) {
      document.title = document.title.replace(RE, '');
    }
  }

  clean(document.documentElement);
  new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType === 1) clean(n);
        if (n.nodeType === 3 && RE.test(n.textContent)) {
          n.textContent = n.textContent.replace(RE, '');
        }
      });
    });
    if (RE.test(document.title)) {
      document.title = document.title.replace(RE, '');
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();

/**
 * Envision OS — Onboarding Popup v2
 * Injected via ConfigMap as /static/onboarding.js
 *
 * Shows a professional "Connect your tools" modal on first login.
 * All integrations use OAuth popup flows — no manual token entry.
 * Gated by: not on /auth, token exists, version flag not set.
 */
(function () {
  'use strict';

  var ONBOARDING_VERSION = '2';
  var POPUP_DELAY_MS = 400;
  var STATUS_FETCH_TIMEOUT_MS = 3000;
  var STATUS_TOTAL_TIMEOUT_MS = 5000;

  // ── Gate checks ──────────────────────────────────────────────────────
  function shouldShow() {
    if (window.location.pathname.startsWith('/auth')) return false;
    if (!localStorage.getItem('token')) return false;
    if (localStorage.getItem('envision_onboarding_version') === ONBOARDING_VERSION) return false;
    return true;
  }

  // ── JWT helper ───────────────────────────────────────────────────────
  function getUserId() {
    try {
      var token = localStorage.getItem('token');
      if (!token) return null;
      var payload = JSON.parse(atob(token.split('.')[1]));
      return payload.id || payload.sub || null;
    } catch (_) {
      return null;
    }
  }

  // ── Integration definitions ──────────────────────────────────────────
  var INTEGRATIONS = [
    {
      id: 'google',
      name: 'Google Workspace',
      desc: 'Gmail, Calendar, and Drive',
      icon: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.96 10.96 0 001 12c0 1.77.42 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>',
      color: '#4285F4',
      oauthPath: '/oauth/start',
      verifyPath: '/oauth/tokens/',
      lsKey: 'envision_google_connected',
    },
    {
      id: 'slack',
      name: 'Slack',
      desc: 'Messaging and channels',
      icon: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none"><path d="M5.04 15.17a2.53 2.53 0 01-2.52 2.52A2.53 2.53 0 010 15.17a2.53 2.53 0 012.52-2.52h2.52v2.52zm1.27 0a2.53 2.53 0 012.52-2.52 2.53 2.53 0 012.52 2.52v6.31A2.53 2.53 0 018.83 24a2.53 2.53 0 01-2.52-2.52v-6.31z" fill="#E01E5A"/><path d="M8.83 5.04a2.53 2.53 0 01-2.52-2.52A2.53 2.53 0 018.83 0a2.53 2.53 0 012.52 2.52v2.52H8.83zm0 1.27a2.53 2.53 0 012.52 2.52 2.53 2.53 0 01-2.52 2.52H2.52A2.53 2.53 0 010 8.83a2.53 2.53 0 012.52-2.52h6.31z" fill="#36C5F0"/><path d="M18.96 8.83a2.53 2.53 0 012.52-2.52A2.53 2.53 0 0124 8.83a2.53 2.53 0 01-2.52 2.52h-2.52V8.83zm-1.27 0a2.53 2.53 0 01-2.52 2.52 2.53 2.53 0 01-2.52-2.52V2.52A2.53 2.53 0 0115.17 0a2.53 2.53 0 012.52 2.52v6.31z" fill="#2EB67D"/><path d="M15.17 18.96a2.53 2.53 0 012.52 2.52A2.53 2.53 0 0115.17 24a2.53 2.53 0 01-2.52-2.52v-2.52h2.52zm0-1.27a2.53 2.53 0 01-2.52-2.52 2.53 2.53 0 012.52-2.52h6.31A2.53 2.53 0 0124 15.17a2.53 2.53 0 01-2.52 2.52h-6.31z" fill="#ECB22E"/></svg>',
      color: '#611f69',
      oauthPath: '/oauth/start?provider=slack',
      verifyPath: '/oauth/tokens/',
      verifyParam: 'provider=slack',
      lsKey: 'envision_slack_connected',
    },
    {
      id: 'whatsapp',
      name: 'WhatsApp',
      desc: 'Contacts, messages, and history',
      icon: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none"><path d="M17.47 14.38c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.16-.17.2-.35.22-.64.07-.3-.15-1.26-.46-2.39-1.47-.88-.79-1.48-1.76-1.65-2.06-.17-.3-.02-.46.13-.6.13-.14.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.03-.52-.07-.15-.67-1.61-.92-2.21-.24-.58-.49-.5-.67-.51-.17-.01-.37-.01-.57-.01-.2 0-.52.07-.79.37s-1.04 1.02-1.04 2.48 1.07 2.88 1.21 3.07c.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.69.63.71.22 1.36.19 1.87.12.57-.09 1.76-.72 2.01-1.41.25-.7.25-1.29.17-1.41-.07-.13-.27-.2-.57-.35m-5.42 7.4h-.01a9.87 9.87 0 01-5.03-1.38l-.36-.21-3.74.98 1-3.65-.24-.37a9.86 9.86 0 01-1.51-5.26c0-5.45 4.44-9.88 9.89-9.88 2.64 0 5.12 1.03 6.99 2.9a9.83 9.83 0 012.89 6.99c0 5.45-4.44 9.88-9.89 9.88m8.41-18.3A11.82 11.82 0 0012.05 0C5.5 0 .16 5.34.16 11.89c0 2.1.55 4.14 1.59 5.95L.06 24l6.3-1.65a11.88 11.88 0 005.68 1.45h.01c6.55 0 11.89-5.34 11.89-11.89 0-3.18-1.24-6.16-3.48-8.41z" fill="#25D366"/></svg>',
      color: '#25D366',
      oauthPath: '/oauth/start?provider=whatsapp',
      verifyPath: '/oauth/tokens/',
      verifyParam: 'provider=whatsapp',
      lsKey: 'envision_whatsapp_connected',
    },
  ];

  // ── Inject styles ────────────────────────────────────────────────────
  function injectStyles() {
    var css = [
      /* Overlay */
      '.eo-overlay{position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.7);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .35s cubic-bezier(.4,0,.2,1)}',
      '.eo-overlay.eo-visible{opacity:1}',

      /* Modal */
      '.eo-modal{background:#111;border:1px solid rgba(255,255,255,.08);border-radius:20px;width:92%;max-width:540px;max-height:90vh;overflow-y:auto;padding:40px 36px 32px;color:#eee;font-family:-apple-system,"system-ui",Inter,ui-sans-serif,"Segoe UI",Roboto,sans-serif;box-shadow:0 32px 64px rgba(0,0,0,.6),0 0 0 1px rgba(255,255,255,.04);transform:translateY(16px) scale(.98);transition:transform .35s cubic-bezier(.4,0,.2,1)}',
      '.eo-overlay.eo-visible .eo-modal{transform:translateY(0) scale(1)}',
      '.eo-modal::-webkit-scrollbar{width:6px}',
      '.eo-modal::-webkit-scrollbar-track{background:transparent}',
      '.eo-modal::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:3px}',

      /* Header */
      '.eo-header{text-align:center;margin-bottom:32px}',
      '.eo-logo{width:48px;height:48px;margin:0 auto 16px;background:#10b981;border-radius:14px;display:flex;align-items:center;justify-content:center}',
      '.eo-header h2{font-size:22px;font-weight:600;margin:0 0 8px;color:#fff;letter-spacing:-.3px}',
      '.eo-header p{font-size:14px;color:rgba(255,255,255,.45);margin:0;line-height:1.5}',

      /* Integration list */
      '.eo-list{display:flex;flex-direction:column;gap:2px}',
      '.eo-row{display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:12px;transition:background .15s ease}',
      '.eo-row:hover{background:rgba(255,255,255,.04)}',

      /* Icon */
      '.eo-icon{width:42px;height:42px;border-radius:11px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.06)}',

      /* Text */
      '.eo-info{flex:1;min-width:0}',
      '.eo-name{font-size:14px;font-weight:550;color:#fff;margin:0 0 2px}',
      '.eo-desc{font-size:12.5px;color:rgba(255,255,255,.4);margin:0}',

      /* Buttons */
      '.eo-connect{border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:8px 18px;font-size:13px;font-weight:550;cursor:pointer;white-space:nowrap;transition:all .15s ease;color:#fff;letter-spacing:-.1px;background:rgba(255,255,255,.08)}',
      '.eo-connect:hover{background:rgba(255,255,255,.14);border-color:rgba(255,255,255,.2)}',
      '.eo-connect:active{transform:scale(.97)}',
      '.eo-connect:disabled{cursor:default;filter:none}',
      '.eo-connect:disabled:active{transform:none}',
      '.eo-connect.eo-waiting{opacity:.7;cursor:wait}',
      '.eo-connect.eo-disconnect{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.34);color:#fca5a5}',
      '.eo-connect.eo-disconnect:hover{background:rgba(239,68,68,.2);border-color:rgba(239,68,68,.5)}',

      /* Auto-connected (muted) */
      '.eo-auto{display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;font-size:12.5px;font-weight:550;background:rgba(255,255,255,.05);color:rgba(255,255,255,.35);border:1px solid rgba(255,255,255,.06)}',

      /* Divider */
      '.eo-divider{height:1px;background:rgba(255,255,255,.06);margin:6px 16px}',

      /* Footer */
      '.eo-footer{text-align:center;margin-top:28px;padding-top:20px;border-top:1px solid rgba(255,255,255,.06)}',
      '.eo-skip{background:none;border:none;color:rgba(255,255,255,.3);font-size:13px;font-weight:450;cursor:pointer;padding:8px 20px;border-radius:8px;transition:all .15s ease;letter-spacing:-.1px}',
      '.eo-skip:hover{color:rgba(255,255,255,.55);background:rgba(255,255,255,.04)}',

      /* Responsive */
      '@media(max-width:480px){.eo-modal{padding:28px 20px 24px}.eo-row{padding:12px 10px;gap:10px}.eo-desc{display:none}.eo-connect{padding:7px 14px;font-size:12px}}',
    ].join('\n');

    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ── SVG icons ────────────────────────────────────────────────────────
  var CHECK_SVG = '<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>';
  var ENVISION_LOGO = '<svg viewBox="0 0 24 24" width="26" height="26" fill="#fff"><path d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.18L19.83 8 12 11.82 4.17 8 12 4.18zM4 9.64l7 3.5V19.5l-7-3.5V9.64zm16 0v6.36l-7 3.5v-6.36l7-3.5z"/></svg>';
  var ENVISION_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="rgba(255,255,255,.45)"><path d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.18L19.83 8 12 11.82 4.17 8 12 4.18zM4 9.64l7 3.5V19.5l-7-3.5V9.64zm16 0v6.36l-7 3.5v-6.36l7-3.5z"/></svg>';

  // ── Build UI ─────────────────────────────────────────────────────────
  function buildPopup() {
    var overlay = document.createElement('div');
    overlay.className = 'eo-overlay';

    var html = '<div class="eo-modal">';
    html += '<div class="eo-header">';
    html += '<div class="eo-logo">' + ENVISION_LOGO + '</div>';
    html += '<h2>Connect your tools</h2>';
    html += '<p>Link your accounts to unlock the full power of Envision OS</p>';
    html += '</div>';
    html += '<div class="eo-list">';

    INTEGRATIONS.forEach(function (intg, i) {
      var connected = localStorage.getItem(intg.lsKey) === 'true';
      html += '<div class="eo-row" id="eo-row-' + intg.id + '">';
      html += '<div class="eo-icon">' + intg.icon + '</div>';
      html += '<div class="eo-info"><p class="eo-name">' + intg.name + '</p><p class="eo-desc">' + intg.desc + '</p></div>';
      if (connected) {
        html += '<button class="eo-connect eo-disconnect" id="eo-btn-' + intg.id + '" data-state="connected">' + CHECK_SVG + ' Disconnect</button>';
      } else {
        html += '<button class="eo-connect" id="eo-btn-' + intg.id + '" data-state="connect">Connect</button>';
      }
      html += '</div>';
      if (i < INTEGRATIONS.length - 1) html += '<div class="eo-divider"></div>';
    });

    // Envision MCP row (always connected)
    html += '<div class="eo-divider"></div>';
    html += '<div class="eo-row">';
    html += '<div class="eo-icon">' + ENVISION_ICON + '</div>';
    html += '<div class="eo-info"><p class="eo-name" style="color:rgba(255,255,255,.5)">Envision Construction</p><p class="eo-desc">390+ tools via MCP Gateway</p></div>';
    html += '<span class="eo-auto">' + CHECK_SVG + ' Included</span>';
    html += '</div>';

    html += '</div>'; // .eo-list
    html += '<div class="eo-footer"><button class="eo-skip" id="eo-skip">I\'ll do this later</button></div>';
    html += '</div>'; // .eo-modal

    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    requestAnimationFrame(function () { overlay.classList.add('eo-visible'); });

    // Bind OAuth buttons
    INTEGRATIONS.forEach(function (intg) {
      var btn = overlay.querySelector('#eo-btn-' + intg.id);
      if (!btn) return;
      btn.addEventListener('click', function () {
        if (btn.getAttribute('data-state') === 'connected') {
          disconnectIntegration(intg, btn);
          return;
        }
        startOAuth(intg, btn, overlay);
      });
    });

    // Dismiss
    overlay.querySelector('#eo-skip').addEventListener('click', function () { dismiss(overlay); });
    overlay.addEventListener('click', function (e) { if (e.target === overlay) dismiss(overlay); });
  }

  function dismiss(overlay) {
    localStorage.setItem('envision_onboarding_version', ONBOARDING_VERSION);
    overlay.classList.remove('eo-visible');
    setTimeout(function () { overlay.remove(); }, 350);
  }

  // ── OAuth flow (shared for all providers) ────────────────────────────
  function startOAuth(intg, btn, overlay) {
    var userId = getUserId();
    if (!userId) return;

    var origText = btn.textContent;
    localStorage.removeItem(intg.lsKey);
    btn.setAttribute('data-state', 'connect');
    btn.classList.remove('eo-disconnect');
    btn.textContent = 'Connecting...';
    btn.classList.add('eo-waiting');
    btn.disabled = true;

    var sep = intg.oauthPath.indexOf('?') === -1 ? '?' : '&';
    var rawUrl = intg.oauthPath + sep + 'user_id=' + encodeURIComponent(userId);
    var absUrl = rawUrl;
    try {
      absUrl = new URL(rawUrl, window.location.origin).toString();
    } catch (_) {}
    // Cache-bust to avoid stale OAuth pages and blank popup edge-cases.
    var joiner = absUrl.indexOf('?') === -1 ? '?' : '&';
    var url = absUrl + joiner + '_ts=' + Date.now();

    // Open placeholder first so user never sees a blank popup.
    var popup = window.open('about:blank', 'envision_' + intg.id + '_oauth', 'width=600,height=700,menubar=no,toolbar=no');
    if (!popup) {
      // Popup blocked: keep user on current page and ask for popup permission.
      btn.textContent = 'Enable Popups';
      btn.classList.remove('eo-waiting');
      btn.disabled = false;
      setTimeout(function () { btn.textContent = origText; }, 1600);
      return;
    }
    try {
      popup.document.open();
      popup.document.write(
        '<!doctype html><html><head><title>Connecting…</title>' +
        '<style>body{margin:0;font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;align-items:center;justify-content:center;height:100vh} .card{padding:24px 28px;border:1px solid rgba(255,255,255,.14);border-radius:14px;background:rgba(255,255,255,.04);text-align:center;min-width:260px} .spinner{width:24px;height:24px;border:3px solid rgba(255,255,255,.2);border-top-color:#22c55e;border-radius:50%;margin:0 auto 12px;animation:spin .9s linear infinite}@keyframes spin{to{transform:rotate(360deg)}} h2{margin:0 0 8px;font-size:17px} p{margin:0;font-size:13px;color:#94a3b8}</style></head><body><div class=\"card\"><div class=\"spinner\"></div><h2>Connecting ' + intg.name + '</h2><p>Loading secure sign-in…</p></div></body></html>'
      );
      popup.document.close();
      popup.focus();
      popup.location.replace(url);
    } catch (_) {
      // ignore
    }

    // Some browsers can leave popups on about:blank briefly. Retry popup navigation only.
    var nudgeCount = 0;
    var nudge = setInterval(function () {
      nudgeCount++;
      if (!popup || popup.closed || nudgeCount > 6) {
        clearInterval(nudge);
        return;
      }
      try {
        if (popup.location && popup.location.href === 'about:blank') {
          popup.location.replace(url);
          return;
        }
        clearInterval(nudge);
      } catch (_) {
        // Cross-origin or already navigated.
        clearInterval(nudge);
      }
    }, 350);

    var poll = setInterval(function () {
      if (!popup || popup.closed) {
        clearInterval(poll);
        verifyOAuthWithRetry(intg, btn, overlay, origText, 0);
      }
    }, 500);
  }

  function verifyOAuth(intg, btn, overlay, origText) {
    var userId = getUserId();
    var verifyUrl = intg.verifyPath + encodeURIComponent(userId);
    if (intg.verifyParam) verifyUrl += '?' + intg.verifyParam;

    fetch(verifyUrl)
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function () {
        localStorage.setItem(intg.lsKey, 'true');
        btn.disabled = false;
        btn.classList.remove('eo-waiting');
        btn.classList.add('eo-disconnect');
        btn.setAttribute('data-state', 'connected');
        btn.innerHTML = CHECK_SVG + ' Disconnect';
      })
      .catch(function () {
        localStorage.removeItem(intg.lsKey);
        btn.setAttribute('data-state', 'connect');
        btn.classList.remove('eo-disconnect');
        btn.textContent = origText;
        btn.classList.remove('eo-waiting');
        btn.disabled = false;
      });
  }

  function verifyOAuthWithRetry(intg, btn, overlay, origText, attempt) {
    verifyOAuth(intg, btn, overlay, origText);
    setTimeout(function () {
      if (btn.getAttribute('data-state') === 'connected') return;
      if (attempt >= 20) return;
      verifyOAuthWithRetry(intg, btn, overlay, origText, attempt + 1);
    }, 750);
  }

  function disconnectIntegration(intg, btn) {
    var userId = getUserId();
    if (!userId) return;

    var origHtml = btn.innerHTML;
    btn.innerHTML = 'Disconnecting...';
    btn.classList.add('eo-waiting');
    btn.disabled = true;

    var disconnectUrl = intg.verifyPath + encodeURIComponent(userId);
    if (intg.verifyParam) disconnectUrl += '?' + intg.verifyParam;

    fetch(disconnectUrl, { method: 'DELETE' })
      .then(function (r) {
        if (!r.ok && r.status !== 404) return Promise.reject();
        return r.text();
      })
      .then(function () {
        localStorage.removeItem(intg.lsKey);
        btn.disabled = false;
        btn.classList.remove('eo-waiting');
        btn.classList.remove('eo-disconnect');
        btn.setAttribute('data-state', 'connect');
        btn.textContent = 'Connect';
      })
      .catch(function () {
        btn.innerHTML = origHtml;
        btn.classList.remove('eo-waiting');
        btn.disabled = false;
      });
  }

  // ── Check backend status before rendering ────────────────────────────
  function fetchWithTimeout(url, options, timeoutMs) {
    if (typeof AbortController === 'undefined') return fetch(url, options || {});
    var controller = new AbortController();
    var t = setTimeout(function () { controller.abort(); }, timeoutMs);
    var opts = options ? Object.assign({}, options) : {};
    opts.signal = controller.signal;
    return fetch(url, opts).finally(function () { clearTimeout(t); });
  }

  function checkBackendStatus(callback) {
    var userId = getUserId();
    if (!userId) { callback(); return; }

    var pending = INTEGRATIONS.length;
    var finished = false;
    var hardTimeout = setTimeout(function () {
      if (finished) return;
      finished = true;
      callback();
    }, STATUS_TOTAL_TIMEOUT_MS);

    function done() {
      pending--;
      if (pending === 0 && !finished) {
        finished = true;
        clearTimeout(hardTimeout);
        callback();
      }
    }

    INTEGRATIONS.forEach(function (intg) {
      var url = intg.verifyPath + encodeURIComponent(userId);
      if (intg.verifyParam) url += '?' + intg.verifyParam;
      fetchWithTimeout(url, {}, STATUS_FETCH_TIMEOUT_MS)
        .then(function (r) {
          if (r.status === 404) return { connected: false };
          if (!r.ok) return Promise.reject();
          return r.json();
        })
        .then(function (data) {
          if (data && data.connected) {
            localStorage.setItem(intg.lsKey, 'true');
          } else {
            localStorage.removeItem(intg.lsKey);
          }
          done();
        })
        .catch(function () {
          // Fail closed so we do not show stale "connected" state.
          localStorage.removeItem(intg.lsKey);
          done();
        });
    });
  }

  // ── Re-trigger support ────────────────────────────────────────────────
  var stylesInjected = false;

  function showOnboarding() {
    // Remove existing overlay if present
    var existing = document.querySelector('.eo-overlay');
    if (existing) existing.remove();

    if (!stylesInjected) { injectStyles(); stylesInjected = true; }
    checkBackendStatus(buildPopup);
  }

  // Global function for programmatic access
  window.__envisionShowOnboarding = showOnboarding;

  // Hash-based trigger: navigate to #connect to open the popup
  function checkHash() {
    if (window.location.hash === '#connect') {
      history.replaceState(null, '', window.location.pathname + window.location.search);
      showOnboarding();
    }
  }
  window.addEventListener('hashchange', checkHash);

  // Custom event trigger: dispatch 'envision-connect' on window
  window.addEventListener('envision-connect', showOnboarding);

  // ── Toggle detection (manual only) ──────────────────────────────────
  // Re-open onboarding when a human explicitly enables Envision OS / Connect All.
  var LAST_USER_INTERACTION_MS = 0;
  var INTERACTION_WINDOW_MS = 1800;
  var TOOL_LABELS = ['connect all', 'envision os', 'envision construction'];

  function markUserInteraction() { LAST_USER_INTERACTION_MS = Date.now(); }
  function hasRecentUserInteraction() {
    return Date.now() - LAST_USER_INTERACTION_MS < INTERACTION_WINDOW_MS;
  }

  document.addEventListener('pointerdown', markUserInteraction, true);
  document.addEventListener('keydown', markUserInteraction, true);

  function findLabeledContainer(startEl) {
    var el = startEl;
    for (var i = 0; i < 10 && el && el !== document.body; i++) {
      var text = ((el.textContent || '') + '').toLowerCase();
      if (text.length > 0 && text.length < 400) {
        for (var j = 0; j < TOOL_LABELS.length; j++) {
          if (text.indexOf(TOOL_LABELS[j]) !== -1) return el;
        }
      }
      el = el.parentElement;
    }
    return null;
  }

  function resolveToggleElement(target) {
    if (!target) return null;
    if (target.matches && (
      target.matches('input[type="checkbox"]') ||
      target.matches('[role="switch"]') ||
      target.matches('[role="checkbox"]') ||
      target.matches('button')
    )) return target;
    if (target.closest) return target.closest('input[type="checkbox"], [role="switch"], [role="checkbox"], button');
    return null;
  }

  function isToggleOn(toggleEl) {
    if (!toggleEl) return null;
    if (toggleEl.matches && toggleEl.matches('input[type="checkbox"]')) {
      return !!toggleEl.checked;
    }
    var ariaChecked = toggleEl.getAttribute && toggleEl.getAttribute('aria-checked');
    if (ariaChecked === 'true') return true;
    if (ariaChecked === 'false') return false;
    var ariaPressed = toggleEl.getAttribute && toggleEl.getAttribute('aria-pressed');
    if (ariaPressed === 'true') return true;
    if (ariaPressed === 'false') return false;
    return null;
  }

  function maybeOpenFromManualToggle(target) {
    if (!hasRecentUserInteraction()) return;
    var container = findLabeledContainer(target);
    if (!container) return;

    var toggleEl = resolveToggleElement(target);
    if (!toggleEl) return;

    // Let the UI update toggle state first.
    setTimeout(function () {
      var on = isToggleOn(toggleEl);
      if (on === false) return;
      showOnboarding();
    }, 250);
  }

  document.addEventListener('click', function (e) {
    maybeOpenFromManualToggle(e.target);
  }, true);

  document.addEventListener('change', function (e) {
    maybeOpenFromManualToggle(e.target);
  }, true);

  // ── Init ─────────────────────────────────────────────────────────────
  // Check hash on load (for direct links)
  if (window.location.hash === '#connect') {
    history.replaceState(null, '', window.location.pathname + window.location.search);
    stylesInjected = true;
    injectStyles();
    setTimeout(function () { checkBackendStatus(buildPopup); }, POPUP_DELAY_MS);
  } else if (shouldShow()) {
    stylesInjected = true;
    injectStyles();
    setTimeout(function () { checkBackendStatus(buildPopup); }, POPUP_DELAY_MS);
  }
})();

/**
 * Envision OS — Tool Auto-Binding
 * Ensure the Envision tool is available for chat completions even if UI tool chips
 * are not manually selected in the current conversation.
 */
(function () {
  'use strict';

  if (window.__envisionFetchPatched) return;
  window.__envisionFetchPatched = true;
  window.__envisionPatchHistory = window.__envisionPatchHistory || [];
  window.__envisionPatchSeq = window.__envisionPatchSeq || 0;
  window.__envisionLastPayloadPatch = window.__envisionLastPayloadPatch || null;
  window.__envisionPatchStats = {
    ts: Date.now(),
    patched: true,
    transport: 'init',
    touched: false,
    reason: 'initialized',
  };

  var RE_GOOGLE_ACCOUNT_QUERY = /\b(which|whose|what)\b[\s\S]{0,60}\bgoogle\b[\s\S]{0,60}\b(account|workspace)\b[\s\S]{0,60}\b(connected|connect)\b/i;
  var RE_SLACK_ACCOUNT_QUERY = /\b(which|whose|what)\b[\s\S]{0,60}\bslack\b[\s\S]{0,60}\b(account|workspace)\b[\s\S]{0,60}\b(connected|connect)\b/i;
  var RE_LAST_SLACK_MESSAGE_QUERY = /\b(last|latest|recent|newest|most\s+recent)\b[\s\S]{0,160}\b(message|messages|dm|direct|chat|response|reply|text)\b[\s\S]{0,160}\bslack\b/i;
  var RE_LAST_SLACK_MESSAGE_QUERY_ALT = /\b(last|latest|recent|newest|most\s+recent)\b[\s\S]{0,160}\bslack\b[\s\S]{0,160}\b(message|messages|dm|direct|chat|response|reply|text)\b/i;
  var RE_SLACK_ACTIVITY_QUERY = /\b(slack)\b[\s\S]{0,220}\b(sent|received|who did i slack last|who slacked me last|last .*sent|last .*received)\b/i;
  var RE_SLACK_FOLLOWUP_QUERY = /\b(who sent (that|this|it)( message)?|who was that from|what time was that sent|was that a dm|was that direct|which channel was that)\b/i;
  var RE_SLACK_SUMMARY_QUERY = /\b(summary|summarize|overview)\b[\s\S]{0,80}\b(recent|latest|today|new)\b[\s\S]{0,120}\bslack\b[\s\S]{0,120}\b(messages?|dms?|chats?)\b/i;
  var RE_SLACK_SEND_QUERY = /\b(send|dm|direct\s+message|message)\b[\s\S]{0,100}\bto\b[\s\S]{0,120}\b(slack|dm|direct|channel|#|@)\b/i;
  var RE_EMAIL_QUERY = /\b(email|gmail|inbox|message)\b/i;
  var RE_LAST_EMAIL_QUERY = /\b(last|latest|recent|newest|most\s+recent)\b[\s\S]{0,80}\b(email|gmail|inbox|message)\b/i;
  var GOOGLE_EMAIL_CACHE_KEY = 'envision_google_connected_email';
  var ENVSN_TOOL_ID = 'envision_os';
  var GOOGLE_ACCOUNT_FUNCTION = 'get_connected_google_account';
  var SLACK_ACCOUNT_FUNCTION = 'get_connected_slack_account';
  var SLACK_LATEST_FUNCTION = 'get_latest_slack_messages';
  var SLACK_ACTIVITY_FUNCTION = 'get_last_slack_sent_and_received';
  var SLACK_SEND_FUNCTION = 'send_slack_message';
  var EMAIL_SEARCH_FUNCTION = 'search_emails';

  function setStats(next) {
    var base = {
      ts: Date.now(),
      patched: true,
      touched: false,
      reason: 'noop',
      url: '',
      method: '',
      transport: '',
    };
    try {
      var evt = Object.assign(base, next || {});
      evt.seq = (++window.__envisionPatchSeq);
      window.__envisionPatchStats = evt;
      window.__envisionPatchHistory.push(evt);
      if (window.__envisionPatchHistory.length > 200) {
        window.__envisionPatchHistory.splice(0, window.__envisionPatchHistory.length - 200);
      }
      if (evt.reason === 'payload-patched') {
        window.__envisionLastPayloadPatch = evt;
      }
    } catch (_) {
      // no-op
    }
  }

  function getUserIdFromToken() {
    try {
      var token = localStorage.getItem('token');
      if (!token) return '';
      var payload = JSON.parse(atob(token.split('.')[1]));
      return (payload.id || payload.sub || '').toString();
    } catch (_) {
      return '';
    }
  }

  async function resolveConnectedGoogleEmail() {
    try {
      var cached = sessionStorage.getItem(GOOGLE_EMAIL_CACHE_KEY);
      if (cached) return cached;

      var userId = getUserIdFromToken();
      if (!userId) return '';

      var refreshResp = await originalFetch('/oauth/refresh/' + encodeURIComponent(userId));
      if (!refreshResp.ok) return '';
      var refreshData = await refreshResp.json();
      var accessToken = refreshData && refreshData.access_token ? refreshData.access_token : '';
      if (!accessToken) return '';

      var profileResp = await originalFetch('https://www.googleapis.com/oauth2/v2/userinfo', {
        method: 'GET',
        headers: { Authorization: 'Bearer ' + accessToken },
      });
      if (!profileResp.ok) return '';
      var profileData = await profileResp.json();
      var email = profileData && profileData.email ? String(profileData.email) : '';
      if (email) sessionStorage.setItem(GOOGLE_EMAIL_CACHE_KEY, email);
      return email;
    } catch (_) {
      return '';
    }
  }

  function getLastUserText(messages) {
    if (!Array.isArray(messages)) return '';
    for (var i = messages.length - 1; i >= 0; i--) {
      var m = messages[i];
      if (!m || m.role !== 'user') continue;
      if (typeof m.content === 'string') return m.content;
      if (Array.isArray(m.content)) {
        var parts = [];
        for (var j = 0; j < m.content.length; j++) {
          var part = m.content[j];
          if (part && part.type === 'text' && typeof part.text === 'string') {
            parts.push(part.text);
          }
        }
        return parts.join(' ');
      }
    }
    return '';
  }

  function getMessageText(message) {
    if (!message || typeof message !== 'object') return '';
    var content = message.content;
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
      var parts = [];
      for (var j = 0; j < content.length; j++) {
        var part = content[j];
        if (part && part.type === 'text' && typeof part.text === 'string') {
          parts.push(part.text);
        }
      }
      return parts.join(' ');
    }
    return '';
  }

  function hasRecentSlackContext(messages) {
    if (!Array.isArray(messages)) return false;
    var maxLookback = 8;
    for (var i = messages.length - 1; i >= 0 && maxLookback > 0; i--, maxLookback--) {
      var text = getMessageText(messages[i]).toLowerCase();
      if (!text) continue;
      if (
        /\bslack\b/.test(text) ||
        /\bdm:/.test(text) ||
        /\blatest slack\b/.test(text) ||
        /\blast (sent|received)\b/.test(text)
      ) {
        return true;
      }
    }
    return false;
  }

  function isRequestObject(value) {
    return typeof Request !== 'undefined' && value instanceof Request;
  }

  function looksLikeJson(text) {
    if (!text || typeof text !== 'string') return false;
    var t = text.trim();
    return t[0] === '{' || t[0] === '[';
  }

  function parseJsonSafe(text) {
    try {
      return JSON.parse(text);
    } catch (_) {
      return null;
    }
  }

  function normalizeUrl(url) {
    try {
      return new URL(url, window.location.origin).toString();
    } catch (_) {
      return url || '';
    }
  }

  function isLikelyChatEndpoint(url) {
    if (!url) return false;
    var u = normalizeUrl(url);
    var lower = u.toLowerCase();
    return (
      lower.indexOf('/chat/completions') !== -1 ||
      lower.indexOf('/api/chat/completions') !== -1 ||
      lower.indexOf('/openai/chat/completions') !== -1 ||
      lower.indexOf('/v1/chat/completions') !== -1 ||
      lower.indexOf('/responses') !== -1
    );
  }

  function getEnvelope(payload) {
    if (!payload || typeof payload !== 'object') return null;
    var candidates = [
      payload,
      payload.body,
      payload.data,
      payload.payload,
      payload.request,
      payload.chat,
      payload.input,
    ];
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i];
      if (!c || typeof c !== 'object') continue;
      if (Array.isArray(c.messages)) {
        return {
          root: c,
          getMessages: function () { return c.messages; },
          setMessages: function (next) { c.messages = next; },
        };
      }
    }
    return null;
  }

  function ensureToolBinding(root) {
    if (!root || typeof root !== 'object') return;

    var hasToolIds = Array.isArray(root.tool_ids) && root.tool_ids.length > 0;
    var hasToolIdsCamel = Array.isArray(root.toolIds) && root.toolIds.length > 0;

    // OpenAI/LiteLLM reject `toolIds` (camelCase). Normalize to `tool_ids` only.
    if (!hasToolIds && hasToolIdsCamel) {
      root.tool_ids = root.toolIds.slice(0);
      hasToolIds = root.tool_ids.length > 0;
    }
    if (Object.prototype.hasOwnProperty.call(root, 'toolIds')) {
      delete root.toolIds;
    }

    if (!hasToolIds) {
      root.tool_ids = [ENVSN_TOOL_ID];
    }
  }

  function ensureNativeFunctionCalling(root) {
    if (!root || typeof root !== 'object') return false;
    if (!root.params || typeof root.params !== 'object') {
      root.params = {};
    }
    if (root.params.function_calling === 'native') return false;
    root.params.function_calling = 'native';
    return true;
  }

  function hasFunctionTool(root, fnName) {
    if (!root || typeof root !== 'object') return false;
    var tools = root.tools;
    if (!Array.isArray(tools)) return false;
    for (var i = 0; i < tools.length; i++) {
      var t = tools[i];
      if (!t || typeof t !== 'object') continue;
      var f = t.function;
      if (f && typeof f === 'object' && f.name === fnName) return true;
      if (t.name === fnName) return true;
    }
    return false;
  }

  function maybeSetToolChoice(root, userText, messages) {
    if (!root || typeof root !== 'object' || !userText) return '';
    var recentSlackContext = hasRecentSlackContext(messages || []);
    var asksSlackLatest =
      (RE_LAST_SLACK_MESSAGE_QUERY.test(userText) || RE_LAST_SLACK_MESSAGE_QUERY_ALT.test(userText)) ||
      (
        /\b(direct messages?|dms?)\b/i.test(userText) &&
        /\b(read|access|latest|last|recent|received)\b/i.test(userText) &&
        /\bslack\b/i.test(userText)
      );

    if (RE_GOOGLE_ACCOUNT_QUERY.test(userText) && hasFunctionTool(root, GOOGLE_ACCOUNT_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: GOOGLE_ACCOUNT_FUNCTION },
      };
      return GOOGLE_ACCOUNT_FUNCTION;
    }
    if (RE_SLACK_ACCOUNT_QUERY.test(userText) && hasFunctionTool(root, SLACK_ACCOUNT_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: SLACK_ACCOUNT_FUNCTION },
      };
      return SLACK_ACCOUNT_FUNCTION;
    }
    if (RE_SLACK_ACTIVITY_QUERY.test(userText) && hasFunctionTool(root, SLACK_ACTIVITY_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: SLACK_ACTIVITY_FUNCTION },
      };
      return SLACK_ACTIVITY_FUNCTION;
    }
    if (recentSlackContext && RE_SLACK_FOLLOWUP_QUERY.test(userText) && hasFunctionTool(root, SLACK_ACTIVITY_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: SLACK_ACTIVITY_FUNCTION },
      };
      return SLACK_ACTIVITY_FUNCTION;
    }
    if (asksSlackLatest && hasFunctionTool(root, SLACK_LATEST_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: SLACK_LATEST_FUNCTION },
      };
      return SLACK_LATEST_FUNCTION;
    }
    if (RE_SLACK_SUMMARY_QUERY.test(userText) && hasFunctionTool(root, SLACK_LATEST_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: SLACK_LATEST_FUNCTION },
      };
      return SLACK_LATEST_FUNCTION;
    }
    if (RE_SLACK_SEND_QUERY.test(userText) && hasFunctionTool(root, SLACK_SEND_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: SLACK_SEND_FUNCTION },
      };
      return SLACK_SEND_FUNCTION;
    }
    if ((RE_LAST_EMAIL_QUERY.test(userText) || RE_EMAIL_QUERY.test(userText)) && hasFunctionTool(root, EMAIL_SEARCH_FUNCTION)) {
      root.tool_choice = {
        type: 'function',
        function: { name: EMAIL_SEARCH_FUNCTION },
      };
      return EMAIL_SEARCH_FUNCTION;
    }
    return '';
  }

  function injectEmailSearchHint(envelope, userText) {
    if (!envelope || !userText) return false;
    if (!RE_LAST_EMAIL_QUERY.test(userText)) return false;
    var hint = {
      role: 'system',
      content:
        'If the user asks for the latest/last email, call search_emails with query "in:inbox" and max_results 5, then summarize the most recent result.',
    };
    var messages = envelope.getMessages();
    if (!Array.isArray(messages)) return false;
    envelope.setMessages([hint].concat(messages));
    return true;
  }

  function injectSlackIdentityHint(envelope, userText) {
    if (!envelope || !userText) return false;
    var asksSlack =
      RE_LAST_SLACK_MESSAGE_QUERY.test(userText) ||
      RE_LAST_SLACK_MESSAGE_QUERY_ALT.test(userText) ||
      RE_SLACK_ACTIVITY_QUERY.test(userText);
    if (!asksSlack) return false;
    var hint = {
      role: 'system',
      content:
        'For Slack answers, always include exact sender/recipient names and whether the message was a DM or channel message. Never use generic labels like "a colleague".',
    };
    var messages = envelope.getMessages();
    if (!Array.isArray(messages)) return false;
    envelope.setMessages([hint].concat(messages));
    return true;
  }

  function injectNoRedactionHint(envelope, userText) {
    if (!envelope || !userText) return false;
    var asksData =
      /\b(email|emails|gmail|inbox|meeting|meetings|calendar|event|events|slack|message|dm|direct)\b/i.test(userText);
    if (!asksData) return false;
    var hint = {
      role: 'system',
      content:
        'Use exact names, emails, and subjects from tool outputs. Never redact, mask, anonymize, or replace values with placeholders like [REDACTED], "a colleague", or generic labels unless the user explicitly asks.',
    };
    var messages = envelope.getMessages();
    if (!Array.isArray(messages)) return false;
    envelope.setMessages([hint].concat(messages));
    return true;
  }

  function injectConnectedEmail(envelope, email) {
    if (!envelope || !email) return false;
    var injected = {
      role: 'system',
      content:
        'The connected Google account email for this user is: ' +
        email +
        '. When asked whose or which Google account is connected, answer with this email directly.',
    };
    var messages = envelope.getMessages();
    if (!Array.isArray(messages)) return false;
    envelope.setMessages([injected].concat(messages));
    return true;
  }

  async function extractBodyText(input, init) {
    if (init && typeof init.body === 'string') return init.body;
    if (isRequestObject(input)) {
      try {
        return await input.clone().text();
      } catch (_) {
        return '';
      }
    }
    return '';
  }

  function buildPatchedRequest(input, payload) {
    if (!isRequestObject(input)) return input;
    var headers = new Headers(input.headers || {});
    headers.set('content-type', 'application/json');
    return new Request(input, {
      method: input.method,
      headers: headers,
      body: JSON.stringify(payload),
      credentials: input.credentials,
      mode: input.mode,
      cache: input.cache,
      redirect: input.redirect,
      referrer: input.referrer,
      referrerPolicy: input.referrerPolicy,
      integrity: input.integrity,
      keepalive: input.keepalive,
      signal: input.signal,
    });
  }

  var originalFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) ? input.url : '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    try {
      var isChatUrl = isLikelyChatEndpoint(url);
      var shouldInspectBody = method !== 'GET' && method !== 'HEAD';
      var bodyText = shouldInspectBody ? await extractBodyText(input, init) : '';
      var bodyDetected = !!bodyText && looksLikeJson(bodyText);
      if (isChatUrl || method !== 'GET') {
        setStats({
          transport: 'fetch',
          url: url || '(request-object)',
          method: method,
          touched: true,
          reason: isChatUrl ? 'chat-url' : 'request-seen',
          bodyDetected: bodyDetected,
        });
      }

      if (!isChatUrl && !bodyDetected) {
        return originalFetch(input, init);
      }

      if (!bodyDetected) {
        setStats({
          transport: 'fetch',
          url: url || '(request-object)',
          method: method,
          touched: true,
          reason: 'no-json-body',
        });
        return originalFetch(input, init);
      }

      var payload = parseJsonSafe(bodyText);
      if (!payload || typeof payload !== 'object') {
        setStats({
          transport: 'fetch',
          url: url || '(request-object)',
          method: method,
          touched: true,
          reason: 'json-parse-failed',
        });
        return originalFetch(input, init);
      }

      var envelope = getEnvelope(payload);
      if (!envelope) {
        setStats({
          transport: 'fetch',
          url: url || '(request-object)',
          method: method,
          touched: true,
          reason: 'not-chat-payload',
          payloadKeys: Object.keys(payload).slice(0, 20),
        });
        return originalFetch(input, init);
      }

      ensureToolBinding(envelope.root);
      var forcedNativeFunctionCalling = ensureNativeFunctionCalling(envelope.root);
      var lastUser = getLastUserText(envelope.getMessages() || []);
      var messages = envelope.getMessages() || [];
      var forcedTool = maybeSetToolChoice(envelope.root, lastUser, messages);
      var injectedEmailHint = injectEmailSearchHint(envelope, lastUser);
      var injectedSlackHint = injectSlackIdentityHint(envelope, lastUser);
      var injectedNoRedactionHint = injectNoRedactionHint(envelope, lastUser);

      var injectedEmail = '';
      if (lastUser && RE_GOOGLE_ACCOUNT_QUERY.test(lastUser)) {
        injectedEmail = await resolveConnectedGoogleEmail();
        if (injectedEmail) injectConnectedEmail(envelope, injectedEmail);
      }

      if (init) {
        init.body = JSON.stringify(payload);
      } else if (isRequestObject(input)) {
        input = buildPatchedRequest(input, payload);
      }

      setStats({
        transport: 'fetch',
        url: url || '(request-object)',
        method: method,
        touched: true,
        reason: 'payload-patched',
        hasToolIds: !!((envelope.root.tool_ids && envelope.root.tool_ids.length) || (envelope.root.toolIds && envelope.root.toolIds.length)),
        toolCount: Array.isArray(envelope.root.tools) ? envelope.root.tools.length : 0,
        forcedNativeFunctionCalling: !!forcedNativeFunctionCalling,
        forcedTool: forcedTool,
        injectedEmailHint: !!injectedEmailHint,
        injectedSlackHint: !!injectedSlackHint,
        injectedNoRedactionHint: !!injectedNoRedactionHint,
        injectedEmail: injectedEmail || '',
      });
    } catch (err) {
      setStats({
        transport: 'fetch',
        url: url || '(request-object)',
        method: method,
        touched: true,
        reason: 'fetch-patch-error',
        error: (err && err.message) ? err.message : 'unknown',
      });
      // Non-blocking: fall back to original fetch behavior.
    }
    return originalFetch(input, init);
  };

  if (!window.__envisionXHRPatched && typeof XMLHttpRequest !== 'undefined') {
    window.__envisionXHRPatched = true;
    var originalOpen = XMLHttpRequest.prototype.open;
    var originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (methodArg, urlArg) {
      this.__envisionMethod = (methodArg || 'GET').toUpperCase();
      this.__envisionUrl = urlArg || '';
      return originalOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function (body) {
      try {
        var methodArg = this.__envisionMethod || 'GET';
        var urlArg = this.__envisionUrl || '';
        var canPatch = methodArg !== 'GET' && methodArg !== 'HEAD';
        var isChatUrl = isLikelyChatEndpoint(urlArg);
        var bodyDetected = typeof body === 'string' && looksLikeJson(body);
        if (canPatch && (isChatUrl || bodyDetected)) {
          var payload = parseJsonSafe(body);
          var envelope = getEnvelope(payload);
          if (envelope) {
            ensureToolBinding(envelope.root);
            var forcedNative = ensureNativeFunctionCalling(envelope.root);
            var lastUser = getLastUserText(envelope.getMessages() || []);
            var messages = envelope.getMessages() || [];
            var forced = maybeSetToolChoice(envelope.root, lastUser, messages);
            var injectedEmailHint = injectEmailSearchHint(envelope, lastUser);
            var injectedSlackHint = injectSlackIdentityHint(envelope, lastUser);
            var injectedNoRedactionHint = injectNoRedactionHint(envelope, lastUser);
            body = JSON.stringify(payload);
            setStats({
              transport: 'xhr',
              url: urlArg,
              method: methodArg,
              touched: true,
              reason: 'payload-patched',
              toolCount: Array.isArray(envelope.root.tools) ? envelope.root.tools.length : 0,
              forcedNativeFunctionCalling: !!forcedNative,
              forcedTool: forced || '',
              injectedEmailHint: !!injectedEmailHint,
              injectedSlackHint: !!injectedSlackHint,
              injectedNoRedactionHint: !!injectedNoRedactionHint,
            });
          } else {
            setStats({
              transport: 'xhr',
              url: urlArg,
              method: methodArg,
              touched: true,
              reason: 'not-chat-payload',
              payloadKeys: payload && typeof payload === 'object' ? Object.keys(payload).slice(0, 20) : [],
            });
          }
        }
      } catch (_) {
        // no-op
      }
      return originalSend.call(this, body);
    };
  }
})();
