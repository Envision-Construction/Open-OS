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
  var POPUP_DELAY_MS = 1500;

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

      /* Connected badge */
      '.eo-badge{display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;font-size:12.5px;font-weight:550;background:rgba(16,185,129,.12);color:#10b981;border:1px solid rgba(16,185,129,.2);letter-spacing:-.1px}',

      /* Auto-connected (muted) */
      '.eo-auto{display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:8px;font-size:12.5px;font-weight:550;background:rgba(255,255,255,.05);color:rgba(255,255,255,.35);border:1px solid rgba(255,255,255,.06)}',

      /* Divider */
      '.eo-divider{height:1px;background:rgba(255,255,255,.06);margin:6px 16px}',

      /* Footer */
      '.eo-footer{text-align:center;margin-top:28px;padding-top:20px;border-top:1px solid rgba(255,255,255,.06)}',
      '.eo-skip{background:none;border:none;color:rgba(255,255,255,.3);font-size:13px;font-weight:450;cursor:pointer;padding:8px 20px;border-radius:8px;transition:all .15s ease;letter-spacing:-.1px}',
      '.eo-skip:hover{color:rgba(255,255,255,.55);background:rgba(255,255,255,.04)}',

      /* Responsive */
      '@media(max-width:480px){.eo-modal{padding:28px 20px 24px}.eo-row{padding:12px 10px;gap:10px}.eo-desc{display:none}.eo-connect,.eo-badge{padding:7px 14px;font-size:12px}}',
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
        html += '<span class="eo-badge">' + CHECK_SVG + ' Connected</span>';
      } else {
        html += '<button class="eo-connect" id="eo-btn-' + intg.id + '">Connect</button>';
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
      if (btn) {
        btn.addEventListener('click', function () {
          startOAuth(intg, btn, overlay);
        });
      }
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
    btn.textContent = 'Connecting...';
    btn.classList.add('eo-waiting');
    btn.disabled = true;

    var sep = intg.oauthPath.indexOf('?') === -1 ? '?' : '&';
    var url = intg.oauthPath + sep + 'user_id=' + encodeURIComponent(userId);
    var popup = window.open(url, 'envision_' + intg.id + '_oauth', 'width=600,height=700,menubar=no,toolbar=no');

    var poll = setInterval(function () {
      if (!popup || popup.closed) {
        clearInterval(poll);
        verifyOAuth(intg, btn, overlay, origText);
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
        // Replace button with connected badge
        var badge = document.createElement('span');
        badge.className = 'eo-badge';
        badge.innerHTML = CHECK_SVG + ' Connected';
        btn.replaceWith(badge);
      })
      .catch(function () {
        btn.textContent = origText;
        btn.classList.remove('eo-waiting');
        btn.disabled = false;
      });
  }

  // ── Check backend status before rendering ────────────────────────────
  function checkBackendStatus(callback) {
    var userId = getUserId();
    if (!userId) { callback(); return; }

    var pending = INTEGRATIONS.length;
    function done() { pending--; if (pending === 0) callback(); }

    INTEGRATIONS.forEach(function (intg) {
      var url = intg.verifyPath + encodeURIComponent(userId);
      if (intg.verifyParam) url += '?' + intg.verifyParam;
      fetch(url)
        .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (data) {
          if (data && data.connected) localStorage.setItem(intg.lsKey, 'true');
          done();
        })
        .catch(function () { done(); });
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

  // ── Toggle detection ─────────────────────────────────────────────────
  // When the user toggles "Connect All" on in the tools panel, fire popup
  document.addEventListener('click', function (e) {
    var el = e.target;
    // Walk up to 8 ancestors looking for a container with "Connect All" text
    for (var i = 0; i < 8 && el && el !== document.body; i++) {
      var text = el.textContent || '';
      if (text.indexOf('Connect All') !== -1 && text.length < 200) {
        // Confirm the click was on a toggle-like element
        var clicked = e.target;
        var isToggle = clicked.tagName === 'BUTTON' ||
          clicked.type === 'checkbox' ||
          clicked.closest('button') ||
          clicked.closest('[role="switch"]') ||
          clicked.closest('[role="checkbox"]') ||
          clicked.closest('label');
        if (isToggle) {
          setTimeout(showOnboarding, 200);
          return;
        }
      }
      el = el.parentElement;
    }
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
