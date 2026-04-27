// ==UserScript==
// @name         TADF Connector
// @namespace    https://github.com/sapsan14/tadf-audit
// @version      0.3.0
// @description  Шлёт данные из EHR.ee и Teatmik.ee в открытый аудит TADF (без копипастов).
// @author       Anton Sokolov / Fjodor Sokolov
// @match        https://livekluster.ehr.ee/*
// @match        https://www.teatmik.ee/*
// @match        https://teatmik.ee/*
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @connect      tadf-audit.h2oatlas.ee
// @connect      livekluster.ehr.ee
// @run-at       document-idle
// ==/UserScript==

/* TADF Connector — bridges the auditor's logged-in EHR / Teatmik tab to
 * the TADF audit they're working on.
 *
 * Auth model: TADF generates a short-lived per-audit HMAC token when the
 * auditor clicks "🔎 Открыть в EHR / Teatmik" and embeds it in the URL
 * fragment (#tadf=<audit_id>:<expiry>:<sig>).
 *
 * The token survives in-site navigation (search page → company detail
 * page) via origin-scoped localStorage with a 24h TTL — same window as
 * the token's own expiry. Without this, clicking on a search result
 * would lose the fragment and the helper would have nothing to report.
 *
 * No cookies leave the browser. Only the page's own JSON / scraped DOM
 * is sent, plus the bearer token for auth.
 */

(function () {
    'use strict';

    const TADF_BASE = 'https://tadf-audit.h2oatlas.ee';
    const HASH_KEY = 'tadf';
    const LS_KEY = 'tadf_connector_token';
    const LS_TTL_MS = 24 * 3600 * 1000;

    // ---- token plumbing ---------------------------------------------------

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
            localStorage.setItem(LS_KEY, JSON.stringify({
                ...ctx,
                savedAt: Date.now(),
            }));
        } catch (e) {
            console.warn('[TADF] could not save token to localStorage:', e);
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
        // Fragment wins over storage (newer URL = newer audit / refreshed token).
        const fromHash = readTokenFromHash();
        if (fromHash) {
            saveToken(fromHash);
            return fromHash;
        }
        return readTokenFromStorage();
    }

    // Always capture the token on first arrival, even if we don't extract
    // anything on this page yet (search pages, login pages, etc).
    const incomingToken = readTokenFromHash();
    if (incomingToken) {
        saveToken(incomingToken);
    }

    // ---- POST to TADF ------------------------------------------------------

    function postToTadf(path, payload) {
        const ctx = getToken();
        if (!ctx) {
            showOverlay(
                '⚠️ TADF token не найден. Открой страницу из кнопки в TADF, не вручную.',
                'error'
            );
            return;
        }
        GM_xmlhttpRequest({
            method: 'POST',
            url: TADF_BASE + path + '/' + ctx.auditId,
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
                            title: 'TADF Connector',
                            timeout: 4000,
                        });
                    }
                } else if (resp.status === 401) {
                    showOverlay('❌ TADF токен истёк — открой страницу из TADF заново', 'error');
                } else {
                    showOverlay(
                        '❌ TADF: ' + resp.status + ' ' + (resp.responseText || '').slice(0, 200),
                        'error'
                    );
                }
            },
            onerror: function () { showOverlay('❌ TADF недоступен — проверь сеть', 'error'); },
            ontimeout: function () { showOverlay('❌ TADF таймаут (15 с)', 'error'); },
        });
    }

    function showOverlay(text, kind) {
        const old = document.getElementById('tadf-connector-overlay');
        if (old) old.remove();
        const div = document.createElement('div');
        div.id = 'tadf-connector-overlay';
        div.textContent = text;
        Object.assign(div.style, {
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            zIndex: '999999',
            padding: '12px 18px',
            borderRadius: '6px',
            fontSize: '14px',
            fontFamily: 'system-ui, sans-serif',
            color: 'white',
            backgroundColor: kind === 'success' ? '#16a34a' : kind === 'info' ? '#2563eb' : '#dc2626',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            cursor: 'pointer',
            maxWidth: '360px',
            lineHeight: '1.4',
        });
        div.addEventListener('click', () => div.remove());
        document.body.appendChild(div);
        if (kind === 'success' || kind === 'info') {
            setTimeout(() => div.remove(), 6000);
        }
    }

    // ---- EHR ---------------------------------------------------------------

    function handleEhr() {
        const m = window.location.pathname.match(/buildings\/(\d+)/) ||
                  window.location.pathname.match(/objects\/(\d+)/);
        if (!m) return;  // not a building page — nothing to do
        const ehrCode = m[1];
        if (!getToken()) return;  // no audit context — silent

        fetch(`/api/building/v3/${ehrCode}`, {
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        })
            .then(r => r.ok ? r.json() : Promise.reject('EHR API ' + r.status))
            .then(data => postToTadf('/api/import-ehr', { ehr_code: ehrCode, ...data }))
            .catch(err => {
                console.warn('[TADF] EHR API fetch failed, falling back to DOM:', err);
                postToTadf('/api/import-ehr', scrapeEhrDom(ehrCode));
            });
    }

    function scrapeEhrDom(ehrCode) {
        const out = { ehr_code: ehrCode, _source: 'dom' };
        document.querySelectorAll('dt, .label, th').forEach(el => {
            const label = (el.textContent || '').trim().toLowerCase();
            const value = (el.nextElementSibling?.textContent || '').trim();
            if (!value) return;
            if (label.includes('aadress')) out.address = value;
            if (label.includes('katastr')) out.kataster_no = value;
            if (label.includes('ehitisaasta')) out.construction_year = value;
            if (label.includes('kasutus') && label.includes('otsta')) out.use_purpose = value;
        });
        return out;
    }

    // ---- Teatmik -----------------------------------------------------------

    function handleTeatmik() {
        // /et/personlegal/<digits>[-slug] OR /en/personlegal/<digits>[-slug]
        const m = window.location.pathname.match(/personlegal\/(\d+)/);
        if (!m) {
            // Search page or anything else — show a hint banner if there's
            // a token in storage so the user knows to click a result.
            if (window.location.pathname.includes('/search') && getToken()) {
                showOverlay('🔎 TADF: выбери компанию в результатах — данные отправятся автоматически.', 'info');
            }
            return;
        }
        if (!getToken()) return;

        const out = {
            reg_code: m[1],
            name: scrapeText(['h1', 'h2', '.company-name', '[data-testid="company-name"]']),
            address: scrapeLabelled(['aadress', 'адрес']),
            status: scrapeLabelled(['staatus', 'статус', 'state']),
        };
        postToTadf('/api/import-teatmik', out);
    }

    function scrapeText(selectors) {
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el && el.textContent.trim()) return el.textContent.trim();
        }
        return null;
    }

    function scrapeLabelled(labels) {
        const all = document.querySelectorAll('dt, th, .label, label');
        for (const el of all) {
            const text = (el.textContent || '').trim().toLowerCase();
            for (const lbl of labels) {
                if (text.includes(lbl)) {
                    const sib = el.nextElementSibling;
                    if (sib && sib.textContent.trim()) return sib.textContent.trim();
                }
            }
        }
        return null;
    }

    // ---- entry point -------------------------------------------------------

    if (window.location.hostname.includes('ehr.ee')) {
        // SPA — wait briefly for content to render after route change.
        setTimeout(handleEhr, 1500);
    } else if (window.location.hostname.includes('teatmik.ee')) {
        handleTeatmik();
    }
})();
