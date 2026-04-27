// ==UserScript==
// @name         TADF Connector (Teatmik)
// @namespace    https://github.com/sapsan14/tadf-audit
// @version      0.5.0
// @description  Шлёт данные из Teatmik.ee в открытый аудит TADF (без копипастов).
// @author       Anton Sokolov / Fjodor Sokolov
// @homepageURL  https://tadf-audit.h2oatlas.ee/Подключения
// @supportURL   https://github.com/sapsan14/tadf-audit/issues
// @updateURL    https://tadf-audit.h2oatlas.ee/api/static/tadf-connector.user.js
// @downloadURL  https://tadf-audit.h2oatlas.ee/api/static/tadf-connector.user.js
// @match        https://www.teatmik.ee/*
// @match        https://teatmik.ee/*
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @connect      tadf-audit.h2oatlas.ee
// @run-at       document-idle
// ==/UserScript==

/* TADF Connector — bridges the auditor's Teatmik tab to the open TADF audit.
 *
 * Why only Teatmik now: ehr.ee exposes a public `/api/building/v3/buildingData`
 * endpoint that TADF on Hetzner calls directly — no browser helper needed
 * for EHR. Teatmik's data is behind Cloudflare CAPTCHA tied to user IP, so
 * the only legitimate path is "auditor solves CAPTCHA, helper reads the
 * already-rendered page from inside the browser session."
 *
 * Auth model: TADF generates a per-audit HMAC token when the auditor clicks
 * "🔎 Найти в Teatmik" and embeds it in the URL fragment
 * (#tadf=<audit_id>:<expiry>:<sig>). The token survives in-site navigation
 * (search → personlegal page) via origin-scoped localStorage with 24h TTL.
 *
 * No cookies leave the browser. Only the page's parsed DOM is sent, plus
 * the bearer token for auth.
 */

(function () {
    'use strict';

    if (!window.location.hostname.includes('teatmik.ee')) return;

    const TADF_BASE = 'https://tadf-audit.h2oatlas.ee';
    const HASH_KEY = 'tadf';
    const LS_KEY = 'tadf_connector_token';
    const LS_TTL_MS = 24 * 3600 * 1000;

    function readTokenFromHash() {
        const hash = (window.location.hash || '').replace(/^#/, '');
        for (const part of hash.split('&')) {
            const [k, v] = part.split('=');
            if (k === HASH_KEY && v) {
                const decoded = decodeURIComponent(v);
                const colons = decoded.split(':');
                if (colons.length === 3) {
                    return { auditId: parseInt(colons[0], 10), token: decoded };
                }
            }
        }
        return null;
    }

    function saveToken(ctx) {
        try {
            localStorage.setItem(LS_KEY, JSON.stringify({ ...ctx, savedAt: Date.now() }));
        } catch (e) {
            console.warn('[TADF] could not save token:', e);
        }
    }

    function readTokenFromStorage() {
        try {
            const raw = localStorage.getItem(LS_KEY);
            if (!raw) return null;
            const data = JSON.parse(raw);
            if (!data.savedAt || Date.now() - data.savedAt > LS_TTL_MS) {
                localStorage.removeItem(LS_KEY);
                return null;
            }
            return { auditId: data.auditId, token: data.token };
        } catch (e) {
            return null;
        }
    }

    function getToken() {
        const fromHash = readTokenFromHash();
        if (fromHash) {
            saveToken(fromHash);
            return fromHash;
        }
        return readTokenFromStorage();
    }

    // Always capture the token on first arrival.
    const incomingToken = readTokenFromHash();
    if (incomingToken) saveToken(incomingToken);

    function showOverlay(text, kind) {
        const old = document.getElementById('tadf-connector-overlay');
        if (old) old.remove();
        const div = document.createElement('div');
        div.id = 'tadf-connector-overlay';
        div.textContent = text;
        Object.assign(div.style, {
            position: 'fixed', bottom: '20px', right: '20px', zIndex: '999999',
            padding: '12px 18px', borderRadius: '6px', fontSize: '14px',
            fontFamily: 'system-ui, sans-serif', color: 'white',
            backgroundColor: kind === 'success' ? '#16a34a' : kind === 'info' ? '#2563eb' : '#dc2626',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)', cursor: 'pointer',
            maxWidth: '360px', lineHeight: '1.4',
        });
        div.addEventListener('click', () => div.remove());
        document.body.appendChild(div);
        if (kind === 'success' || kind === 'info') setTimeout(() => div.remove(), 6000);
    }

    function postToTadf(payload) {
        const ctx = getToken();
        if (!ctx) {
            showOverlay('⚠️ TADF token не найден. Открой Teatmik из кнопки в TADF.', 'error');
            return;
        }
        GM_xmlhttpRequest({
            method: 'POST',
            url: TADF_BASE + '/api/import-teatmik/' + ctx.auditId,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + ctx.token,
                'X-Source-URL': window.location.href,
            },
            data: JSON.stringify(payload),
            timeout: 15000,
            onload: function (resp) {
                if (resp.status >= 200 && resp.status < 300) {
                    showOverlay(`✅ Отправлено в TADF (аудит #${ctx.auditId})`, 'success');
                    if (typeof GM_notification === 'function') {
                        GM_notification({
                            text: 'Данные отправлены в TADF — переключись на вкладку.',
                            title: 'TADF Connector', timeout: 4000,
                        });
                    }
                } else if (resp.status === 401) {
                    showOverlay('❌ TADF токен истёк — открой Teatmik из TADF заново', 'error');
                } else {
                    showOverlay('❌ TADF: ' + resp.status + ' ' + (resp.responseText || '').slice(0, 200), 'error');
                }
            },
            onerror: function () { showOverlay('❌ TADF недоступен — проверь сеть', 'error'); },
            ontimeout: function () { showOverlay('❌ TADF таймаут (15 с)', 'error'); },
        });
    }

    /* Teatmik personlegal pages render data as plain HTML tables with
     * <table class="info"><tr><td>Label:</td><td>Value</td></tr></table>.
     * Email + phone are also exposed via OpenGraph meta tags + mailto/tel
     * links — those are the most reliable sources.
     *
     * Real DOM verified against TADF Ehitus OÜ (12503172) on 2026-04-27.
     */

    function scrapeMeta(prop) {
        const el = document.querySelector('meta[property="' + prop + '"]');
        return el ? (el.getAttribute('content') || '').trim() || null : null;
    }
    function scrapeMailto() {
        const a = document.querySelector('a[href^="mailto:"]');
        return a ? a.getAttribute('href').slice(7).trim() || null : null;
    }
    function scrapeTel() {
        const a = document.querySelector('a[href^="tel:"]');
        return a ? a.getAttribute('href').slice(4).trim() || null : null;
    }

    function scrapeText(selectors) {
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el && el.textContent.trim()) return el.textContent.trim();
        }
        return null;
    }

    /* Find a `<td>Label:</td><td>Value</td>` pair and return the value.
     * Strips icons (so the cell text "<icon> Aadress:" matches "Aadress").
     */
    function scrapeTableField(labels) {
        const lowerLabels = labels.map(s => s.toLowerCase().replace(/:$/, ''));
        for (const td of document.querySelectorAll('td')) {
            // Strip any embedded icon text (Font Awesome adds none, but be safe)
            let text = (td.textContent || '').trim().toLowerCase()
                .replace(/[:.\s]+$/, '').replace(/\s+/g, ' ');
            for (const lbl of lowerLabels) {
                if (text === lbl) {
                    const nextTd = td.nextElementSibling;
                    if (nextTd && nextTd.tagName === 'TD') {
                        const v = (nextTd.textContent || '').trim().replace(/\s+/g, ' ');
                        if (v.length >= 1 && v.length < 400) return v;
                    }
                }
            }
        }
        return null;
    }

    // /et/personlegal/<digits>[-slug] OR /en/personlegal/<digits>[-slug]
    const m = window.location.pathname.match(/personlegal\/(\d+)/);
    if (!m) {
        if (window.location.pathname.includes('/search') && getToken()) {
            showOverlay('🔎 TADF: выбери компанию в результатах — данные отправятся автоматически.', 'info');
        }
        return;
    }
    if (!getToken()) return;

    // The TADF link button may include a `target` hint in the URL fragment
    // (`#tadf=…&target=client|designer|builder`) so we know which form
    // section the auditor was on when they triggered the search.
    function readTargetHint() {
        const hash = (window.location.hash || '').replace(/^#/, '');
        for (const part of hash.split('&')) {
            const [k, v] = part.split('=');
            if (k === 'target' && v) return decodeURIComponent(v);
        }
        return null;
    }

    postToTadf({
        reg_code: m[1],
        name: scrapeText(['h1', 'h2', '.company-name']),
        address: scrapeTableField(['Aadress']),
        status: scrapeTableField(['Seisund']),
        email: scrapeMeta('business:contact_data:email') || scrapeMailto(),
        phone: scrapeMeta('business:contact_data:phone_number') || scrapeTel(),
        legal_form: scrapeTableField(['Õiguslik vorm']),
        capital: scrapeTableField(['Kapital']),
        target: readTargetHint(),
    });
})();
