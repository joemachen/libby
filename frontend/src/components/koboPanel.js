/**
 * koboPanel — device status indicator in the header.
 *
 * Polls GET /api/kobo/status every POLL_MS milliseconds.
 * On connect/disconnect it toggles the CSS class "kobo-connected" on #app,
 * which the CSS uses to enable/disable send buttons without re-rendering cards.
 */

import { getKoboStatus, sendToKobo } from "../api.js";

const POLL_MS = 8_000;

export const KoboPanel = {
    el: null,
    _device: null,
    _callbacks: {},

    /**
     * Mount the panel and start polling.
     * @param {HTMLElement} container  – the header element for device status
     * @param {{ onSent?: Function, onError?: Function }} callbacks
     */
    init(container, callbacks = {}) {
        this.el = container;
        this._callbacks = callbacks;
        this._render(null);
        this._poll();
    },

    /**
     * Send a book to the Kobo. Called by app.js from the grid's onSend handler.
     * @param {string} bookId
     * @param {string} bookTitle  – used only for toast messaging
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
  ${_esc(device.name)}&thinsp;—&thinsp;${free} free
</span>`;
    },
};

// ── Utilities ─────────────────────────────────────────────────────────────────

function _fmtBytes(n) {
    for (const u of ["B", "KB", "MB", "GB"]) {
        if (n < 1024) return `${n.toFixed(1)} ${u}`;
        n /= 1024;
    }
    return `${n.toFixed(1)} TB`;
}

function _esc(val) {
    return String(val ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
