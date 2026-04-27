// ==UserScript==
// @name         TADF Connector
// @namespace    https://github.com/sapsan14/tadf-audit
// @version      0.2.0
// @description  Шлёт данные из EHR.ee и Teatmik.ee в открытый аудит TADF (без копипастов).
// @author       Anton Sokolov / Fjodor Sokolov
// @match        https://livekluster.ehr.ee/ui/ehr/v1/buildings/*
// @match        https://livekluster.ehr.ee/ui/ehr/v1/objects/*
// @match        https://www.teatmik.ee/et/personlegal/*
// @match        https://www.teatmik.ee/en/personlegal/*
// @match        https://teatmik.ee/et/personlegal/*
// @match        https://teatmik.ee/en/personlegal/*
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
 * fragment (#tadf=<audit_id>:<expiry>:<sig>). This script reads it,
 * fetches the page data via the auditor's existing browser session, and
 * POSTs it to TADF's /api endpoint. No cookies leave the browser.
 */

(function () {
    'use strict';

    const TADF_BASE = 'https://tadf-audit.h2oatlas.ee';
    const HASH_KEY = 'tadf';

    // ---- helpers -----------------------------------------------------------

    function readToken() {
        // Format in URL fragment: #tadf=<audit_id>:<expiry>:<sig>
        // Multiple fragments separated by `&` are tolerated.
        const hash = window.location.hash.replace(/^#/, '');
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

    function postToTadf(path, payload) {
        const ctx = readToken();
        if (!ctx) {
            console.log('[TADF Connector] no token in URL fragment — открой страницу из TADF, не вручную');
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
                    showOverlay('✅ Отправлено в TADF', 'success');
                    if (typeof GM_notification === 'function') {
                        GM_notification({
                            text: 'Данные отправлены в TADF — переключитесь на вкладку.',
                            title: 'TADF Connector',
                            timeout: 4000,
                        });
                    }
                } else {
                    showOverlay('❌ TADF: ' + resp.status + ' ' + resp.responseText.slice(0, 200), 'error');
                }
            },
            onerror: function () {
                showOverlay('❌ TADF недоступен — проверь сеть', 'error');
            },
            ontimeout: function () {
                showOverlay('❌ TADF таймаут (15 с)', 'error');
            },
        });
    }

    function showOverlay(text, kind) {
        // Remove old overlay first
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
            backgroundColor: kind === 'success' ? '#16a34a' : '#dc2626',
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
            cursor: 'pointer',
        });
        div.addEventListener('click', () => div.remove());
        document.body.appendChild(div);
        // Auto-dismiss success overlays after 5 s
        if (kind === 'success') {
            setTimeout(() => div.remove(), 5000);
        }
    }

    // ---- EHR ---------------------------------------------------------------

    function handleEhr() {
        // Pull the EHR-code out of the URL: /ui/ehr/v1/buildings/<code>
        const m = window.location.pathname.match(/buildings\/(\d+)/);
        if (!m) return;
        const ehrCode = m[1];

        // The SPA already has the building object cached after page load —
        // we re-fetch through the same authed session to get a clean JSON
        // payload independent of the rendered DOM.
        fetch(`/api/building/v3/${ehrCode}`, {
            credentials: 'include',
            headers: { 'Accept': 'application/json' },
        })
            .then(r => r.ok ? r.json() : Promise.reject('EHR API ' + r.status))
            .then(data => {
                postToTadf('/api/import-ehr', { ehr_code: ehrCode, ...data });
            })
            .catch(err => {
                // Fall back to scraping the DOM if the API path moved.
                console.warn('[TADF Connector] EHR API fetch failed, falling back to DOM:', err);
                postToTadf('/api/import-ehr', scrapeEhrDom(ehrCode));
            });
    }

    function scrapeEhrDom(ehrCode) {
        // Lightweight DOM fallback — collect any obvious labelled values.
        const out = { ehr_code: ehrCode, _source: 'dom' };
        document.querySelectorAll('dt, .label, th').forEach(el => {
            const label = (el.textContent || '').trim().toLowerCase();
            const value = (el.nextElementSibling?.textContent || '').trim();
            if (!value) return;
            if (label.includes('aadress') || label.includes('адрес')) out.address = value;
            if (label.includes('katastr')) out.kataster_no = value;
            if (label.includes('ehitisaasta') || label.includes('год')) out.construction_year = value;
            if (label.includes('kasutus') && label.includes('otsta')) out.use_purpose = value;
        });
        return out;
    }

    // ---- Teatmik -----------------------------------------------------------

    function handleTeatmik() {
        // /et/personlegal/<reg_code>
        const m = window.location.pathname.match(/personlegal\/(\d+)/);
        if (!m) return;
        const regCode = m[1];

        // The page is HTML-rendered after CAPTCHA — DOM is the source of truth.
        const out = {
            reg_code: regCode,
            name: scrapeText(['h1', 'h2', '.company-name']),
            address: scrapeLabelled(['aadress', 'адрес']),
            status: scrapeLabelled(['staatus', 'статус']),
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
        // Wait briefly for the SPA to populate cookies / state.
        setTimeout(handleEhr, 1500);
    } else if (window.location.hostname.includes('teatmik.ee')) {
        handleTeatmik();
    }
})();
