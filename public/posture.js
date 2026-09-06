/*
 * Live security-posture panel.
 *
 * The point of this file: every claim on the platform about trackers, cookies and
 * headers is, until now, just copy. Copy is what every competitor also writes.
 * This measures the page the visitor is actually looking at, in their own browser,
 * and prints what it finds — including when what it finds is bad.
 *
 * Loaded with defer, so it is exempt from the head-script render-contract that caused
 * the 2026-07-27 outage. It must stay that way: this file queries the DOM immediately.
 *
 * Progressive enhancement is not optional here. The markup ships with the honest
 * static values already in place; this script only ever *upgrades* a row to "measured".
 * If it never runs, the panel still reads correctly — it just says "stated" rather
 * than "measured", which is the truth in that case.
 */
(function () {
  'use strict';

  var STATE_OK = 'ok', STATE_BAD = 'bad';

  function setRow(name, value, state, note) {
    var row = document.querySelector('[data-posture="' + name + '"]');
    if (!row) return;
    var v = row.querySelector('.posture-value');
    var n = row.querySelector('.posture-note');
    if (v) v.textContent = value;
    if (n && note) n.textContent = note;
    row.classList.add('posture-measured');
    row.classList.toggle('posture-fail', state === STATE_BAD);
  }

  /* Distinct non-same-origin hosts the browser actually fetched for this page.
     Resource Timing sees every subresource regardless of how it was requested,
     which is why this cannot be faked by the markup. */
  function thirdPartyOrigins() {
    if (!window.performance || !performance.getEntriesByType) return null;
    var here = location.origin, seen = {};
    performance.getEntriesByType('resource').forEach(function (e) {
      try {
        var o = new URL(e.name).origin;
        if (o !== here) seen[o] = true;
      } catch (err) { /* opaque or malformed entry — ignore, it cannot be attributed */ }
    });
    return Object.keys(seen);
  }

  /* Code we did not write, served from OUR OWN origin.
   *
   * Measured 2026-09-04: counting by origin alone reported "0 third-party" while
   * Cloudflare's Email Obfuscation was injecting
   * /cdn-cgi/scripts/<hash>/cloudflare-static/email-decode.min.js into every page
   * of all nine origins. It is same-origin, so the check above excludes it by
   * construction, and script-src 'self' permits it for the same reason. The panel
   * was therefore reporting a true number under a false note ("no CDN on any page").
   *
   * The honest fix is not to hide it. This file's whole promise is that it prints
   * what it finds "including when what it finds is bad" — so it counts platform
   * injection separately and names it. /cdn-cgi/ is Cloudflare's reserved path and
   * cannot be produced by this repository's own build. */
  function injectedSameOrigin() {
    if (!window.performance || !performance.getEntriesByType) return null;
    var here = location.origin, hits = [];
    performance.getEntriesByType('resource').forEach(function (e) {
      try {
        var u = new URL(e.name);
        if (u.origin === here && u.pathname.indexOf('/cdn-cgi/') === 0) {
          hits.push(u.pathname.split('/').pop());
        }
      } catch (err) { /* unattributable — ignore */ }
    });
    return hits;
  }

  function storageCount() {
    var n = 0;
    try { n += window.localStorage.length; } catch (e) { /* blocked by the browser, not by us */ }
    try { n += window.sessionStorage.length; } catch (e) { /* same */ }
    return n;
  }

  function boot() {
    var third = thirdPartyOrigins();
    var inj   = injectedSameOrigin();
    if (third !== null) {
      var note;
      if (third.length === 0 && (!inj || inj.length === 0)) {
        note = 'Measured in your browser — nothing was loaded from another host, ' +
               'and no code was injected into this page by the CDN';
      } else if (third.length === 0) {
        /* The number stays honest: 0 OTHER HOSTS were contacted. But the panel must
           not let that read as "no third-party code", which is a wider claim than
           this row measures. */
        note = 'Measured in your browser — no other host was contacted, but our CDN ' +
               'injected ' + inj.length + ' script' + (inj.length === 1 ? '' : 's') +
               ' into this page: ' + inj.join(', ');
      } else {
        note = 'Measured in your browser: ' + third.join(', ');
      }
      setRow('third-party',
             String(third.length),
             (third.length === 0 && (!inj || inj.length === 0)) ? STATE_OK : STATE_BAD,
             note);
    }

    var cookies = document.cookie ? document.cookie.split(';').filter(Boolean).length : 0;
    setRow('cookies', String(cookies), cookies === 0 ? STATE_OK : STATE_BAD,
           cookies === 0 ? 'Read from document.cookie on this page load' : 'Read from document.cookie');

    var stored = storageCount();
    setRow('storage', String(stored), stored === 0 ? STATE_OK : STATE_BAD,
           stored === 0 ? 'localStorage and sessionStorage are both empty' : 'Entries found in browser storage');

    /* Same-origin request, so every response header is readable. connect-src 'self'
       permits it; a cross-origin equivalent would be blocked and would also hide
       the headers behind CORS. */
    if (window.fetch) {
      fetch(location.pathname, { method: 'HEAD', cache: 'no-store' })
        .then(function (res) {
          var csp = res.headers.get('content-security-policy');
          if (csp) {
            var strict = csp.indexOf("default-src 'self'") !== -1 &&
                         csp.indexOf('unsafe-inline') === -1 &&
                         csp.indexOf('unsafe-eval') === -1;
            setRow('csp', strict ? "default-src 'self'" : 'weakened',
                   strict ? STATE_OK : STATE_BAD,
                   strict ? 'Live response header — no unsafe-inline, no unsafe-eval'
                          : 'Live response header — contains an unsafe directive');
          }
          var hsts = res.headers.get('strict-transport-security');
          if (hsts) {
            var m = /max-age=(\d+)/.exec(hsts);
            var years = m ? Math.round(parseInt(m[1], 10) / 31536000) : 0;
            setRow('hsts', years ? years + '-year' : 'on', STATE_OK,
                   'Live response header — ' + hsts);
          }
          var pp = res.headers.get('permissions-policy');
          if (pp) {
            var denied = (pp.match(/=\(\)/g) || []).length;
            setRow('permissions', String(denied), STATE_OK,
                   'Live response header — ' + denied + ' browser capabilities denied outright');
          }
        })
        .catch(function () {
          /* Offline, or the request was blocked. The static values stay as shipped —
             they are still true, they are simply no longer independently measured. */
        });
    }

    var stamp = document.querySelector('[data-posture-time]');
    if (stamp) {
      stamp.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
