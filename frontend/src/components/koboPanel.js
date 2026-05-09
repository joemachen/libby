/**
 * koboPanel — device status indicator in the header.
 *
 * Polls GET /api/kobo/status every POLL_MS milliseconds.
 * On connect/disconnect it toggles the CSS class "kobo-connected" on #app,
 * which the CSS uses to enable/disable send buttons without re-rendering cards.
 *
 * When connected, renders:
 *   [● KOBOeReader — 12.3 GB free]  [📚]  [⏏]
 */

import { getKoboStatus, sendToKobo, bulkSendToKobo, ejectKobo } from "../api.js";

const POLL_MS = 8_000;

export const KoboPanel = {
    el: null,
    _device: null,
    _callbacks: {},
    _ejecting: false,

    /**
     * Mount the panel and start polling.
     * @param {HTMLElement} container
     * @param {{ onSent?: Function, onError?: Function, onConnected?: Function, onDisconnected?: Function, onShelfOpen?: Function }} callbacks
     */
    init(container, callbacks = {}) {
        this.el = container;
        this._callbacks = callbacks;
        this._render(null);
        this._poll();
    },

    /**
     * Send a single book to the Kobo. Called by app.js from the grid's onSend handler.
     * @param {string} bookId
     * @param {string} bookTitle
     */
    async sendBook(bookId, bookTitle) {
        if (!this._device) {
            this._callbacks.onError?.("No Kobo device connected.");
            return;
        }
        try {
            const result = await sendToKobo(bookId);
            this._callbacks.onSent?.(bookTitle, result);
        } catch (err) {
            this._callbacks.onError?.(err.message);
        }
    },

    /**
     * Send multiple books to the Kobo. Called by app.js from the grid's onBulkSend handler.
     * @param {string[]} bookIds
     */
    async sendBooks(bookIds) {
        if (!this._device) {
            this._callbacks.onError?.("No Kobo device connected.");
            return;
        }
        try {
            const data = await bulkSendToKobo(bookIds);
            this._callbacks.onBulkSent?.(data.results);
        } catch (err) {
            this._callbacks.onError?.(err.message);
        }
    },

    // ── Private ──────────────────────────────────────────────────────────────

    async _poll() {
        try {
            const data = await getKoboStatus();
            const wasConnected = this._device !== null;
            const nowConnected = data.connected;

            this._device = nowConnected ? data.device : null;
            this._render(this._device);

            if (!wasConnected && nowConnected) {
                document.getElementById("app")?.classList.add("kobo-connected");
                this._callbacks.onConnected?.(this._device);
            } else if (wasConnected && !nowConnected) {
                document.getElementById("app")?.classList.remove("kobo-connected");
                this._callbacks.onDisconnected?.();
            }
        } catch {
            // Server may not be ready yet — silent
        }
        setTimeout(() => this._poll(), POLL_MS);
    },

    _render(device) {
        if (!device) {
            this.el.innerHTML =
                `<span class="kobo-pill kobo-pill-off">No Kobo connected</span>`;
            return;
        }

        const free = _fmtBytes(device.free_space);
        this.el.innerHTML = `
<span class="kobo-pill kobo-pill-on">
  <span class="kobo-dot"></span>
  <span class="kobo-pill-label">${_esc(device.name)}&thinsp;—&thinsp;${free} free</span>
</span>
<button class="btn-icon kobo-action-btn" data-kobo-action="shelf" title="View Kobo shelf">
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
  </svg>
</button>
<button class="btn-icon kobo-action-btn kobo-eject-btn" data-kobo-action="eject" title="Safely eject Kobo">
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
    <polyline points="23 7 12 2 1 7"/><rect x="1" y="11" width="22" height="3" rx="1"/>
    <line x1="12" y1="2" x2="12" y2="11"/>
  </svg>
</button>`;

        this.el.querySelectorAll("[data-kobo-action]").forEach(btn => {
            btn.addEventListener("click", () => this._handleAction(btn.dataset.koboAction, btn));
        });
    },

    async _handleAction(action, btn) {
        if (action === "shelf") {
            this._callbacks.onShelfOpen?.();
        } else if (action === "eject") {
            if (this._ejecting) return;
            this._ejecting = true;
            btn.disabled = true;
            btn.style.opacity = "0.5";
            try {
                await ejectKobo();
                this._callbacks.onEjected?.();
            } catch (err) {
                this._callbacks.onError?.(err.message);
                btn.disabled = false;
                btn.style.opacity = "";
            } finally {
                this._ejecting = false;
            }
        }
    },
};

// ── Utilities ─────────────────────────────────────────────────────────────────

function _fmtBytes(n) {
    for (const u of ["B", "KB", "MB", "GB"]) {
        if (n < 1024) return `${n.toFixed(1)} ${u}`;
        n /= 1024;
    }
    return `${n.toFixed(1)} TB`;
}

function _esc(val) {
    return String(val ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
