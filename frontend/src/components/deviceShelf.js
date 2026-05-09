/**
 * deviceShelf — a right-side drawer that lists all EPUBs on the connected
 * device, cross-referenced with the local library.
 *
 * Usage:
 *   DeviceShelf.init()          — call once at startup (attaches overlay click handler)
 *   DeviceShelf.open()          — fetch books and slide the drawer in
 *   DeviceShelf.close()         — slide the drawer out
 */

import { getDeviceBooks } from "../api.js";

export const DeviceShelf = {
    _drawer: null,
    _overlay: null,
    _activeTab: "all",   // "all" | "library" | "device-only"

    /** Wire up the overlay and drawer elements created in index.html. */
    init() {
        this._drawer  = document.getElementById("device-shelf");
        this._overlay = document.getElementById("device-shelf-overlay");

        this._overlay?.addEventListener("click", () => this.close());

        this._drawer?.addEventListener("click", e => {
            // Close button
            if (e.target.closest(".shelf-close-btn")) {
                this.close();
                return;
            }
            // Tab switching
            const tab = e.target.closest(".shelf-tab");
            if (tab) {
                this._activeTab = tab.dataset.tab;
                this._drawer.querySelectorAll(".shelf-tab")
                    .forEach(t => t.classList.toggle("active", t === tab));
                this._renderBooks(this._books || []);
            }
        });

        document.addEventListener("keydown", e => {
            if (e.key === "Escape" && this._drawer?.classList.contains("shelf--open")) {
                this.close();
            }
        });
    },

    /** Fetch device books and open the drawer. */
    async open() {
        if (!this._drawer) return;
        this._activeTab = "all";
        this._showLoading();
        this._drawer.classList.add("shelf--open");
        this._overlay?.classList.add("visible");

        try {
            this._books = await getDeviceBooks();
            this._renderBooks(this._books);
        } catch (err) {
            this._showError(err.message);
        }
    },

    /** Close the drawer. */
    close() {
        this._drawer?.classList.remove("shelf--open");
        this._overlay?.classList.remove("visible");
    },

    // ── Private ──────────────────────────────────────────────────────────────

    _showLoading() {
        if (!this._drawer) return;
        this._drawer.innerHTML = `
<div class="shelf-header">
  <h2 class="shelf-title">Device Shelf</h2>
  <button class="btn-icon shelf-close-btn" aria-label="Close shelf">✕</button>
</div>
<div class="shelf-loading">Loading…</div>`;
    },

    _showError(msg) {
        if (!this._drawer) return;
        this._drawer.innerHTML = `
<div class="shelf-header">
  <h2 class="shelf-title">Device Shelf</h2>
  <button class="btn-icon shelf-close-btn" aria-label="Close shelf">✕</button>
</div>
<div class="shelf-error">${_esc(msg)}</div>`;
    },

    _renderBooks(books) {
        if (!this._drawer) return;

        const inLibrary   = books.filter(b => b.in_library);
        const deviceOnly  = books.filter(b => !b.in_library);
        const displayed   = this._activeTab === "library"     ? inLibrary
                          : this._activeTab === "device-only" ? deviceOnly
                          : books;

        const tabs = [
            { id: "all",         label: `All (${books.length})` },
            { id: "library",     label: `In library (${inLibrary.length})` },
            { id: "device-only", label: `Not in library (${deviceOnly.length})` },
        ].map(t => `<button class="shelf-tab ${t.id === this._activeTab ? "active" : ""}"
                            data-tab="${t.id}">${_esc(t.label)}</button>`).join("");

        const rows = displayed.length
            ? displayed.map(b => this._bookRow(b)).join("")
            : `<li class="shelf-empty">No books in this view.</li>`;

        this._drawer.innerHTML = `
<div class="shelf-header">
  <h2 class="shelf-title">Device Shelf <span class="shelf-count">${books.length} book${books.length !== 1 ? "s" : ""}</span></h2>
  <button class="btn-icon shelf-close-btn" aria-label="Close shelf">✕</button>
</div>
<div class="shelf-tabs">${tabs}</div>
<ul class="shelf-book-list">${rows}</ul>`;
    },

    _bookRow(book) {
        const thumb = book.cover_path
            ? `<img class="shelf-cover" src="${_esc(book.cover_path)}" alt="" loading="lazy" />`
            : `<div class="shelf-cover shelf-cover-placeholder"></div>`;

        const title  = book.title    || book.filename;
        const author = book.author   ? `<span class="shelf-author">${_esc(book.author)}</span>` : "";
        const badge  = book.in_library
            ? `<span class="shelf-badge shelf-badge-library">In library</span>`
            : `<span class="shelf-badge shelf-badge-device">Device only</span>`;

        return `<li class="shelf-book-row" ${book.book_id ? `data-book-id="${_esc(book.book_id)}"` : ""}>
  ${thumb}
  <div class="shelf-book-info">
    <span class="shelf-title-text" title="${_esc(title)}">${_esc(title)}</span>
    ${author}
  </div>
  ${badge}
</li>`;
    },
};

function _esc(val) {
    return String(val ?? "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
