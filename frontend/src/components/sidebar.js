/**
 * sidebar — author filter list.
 * Fetches authors from the API and renders a clickable list.
 * Active author is highlighted; clicking "All" clears the filter.
 */

import { getAuthors } from "../api.js";

const STATUS_OPTIONS = [
    { value: null,      label: "All books" },
    { value: "unread",  label: "Unread" },
    { value: "reading", label: "Reading" },
    { value: "read",    label: "Read" },
];

export const Sidebar = {
    el: null,
    callbacks: {},
    _activeAuthor: null,
    _activeStatus: null,
    _authors: [],

    /**
     * Mount the sidebar and load authors.
     * @param {HTMLElement} container
     * @param {{ onAuthor: Function, onStatus: Function }} callbacks
     */
    init(container, callbacks = {}) {
        this.el = container;
        this.callbacks = callbacks;
        this._bindEvents();
        this.loadAuthors();
    },

    /** Fetch the author list and re-render. */
    async loadAuthors() {
        try {
            this._authors = await getAuthors();
            this._render();
        } catch (err) {
            console.warn("[sidebar] Failed to load authors:", err.message);
        }
    },

    /** Sync the highlighted author to match app state without a full reload. */
    setActiveAuthor(author) {
        this._activeAuthor = author;
        this.el.querySelectorAll(".author-item").forEach(el => {
            const isActive = (el.dataset.author || null) === author;
            el.classList.toggle("active", isActive);
        });
    },

    /** Sync the highlighted status filter to match app state. */
    setActiveStatus(status) {
        this._activeStatus = status;
        this.el.querySelectorAll(".status-filter-item").forEach(el => {
            const isActive = (el.dataset.status || null) === status;
            el.classList.toggle("active", isActive);
        });
    },

    // ── Private ──────────────────────────────────────────────────────────────

    _render() {
        const items = this._authors.map(a => {
            const name  = typeof a === "string" ? a : a.name;
            const count = typeof a === "string" ? null : a.count;
            const active = this._activeAuthor === name ? "active" : "";
            const countBadge = count != null
                ? `<span class="author-count">${count}</span>`
                : "";
            return `<li class="author-item ${active}"
                        data-author="${_esc(name)}"
                        title="${_esc(name)}">
                      <span class="author-name-text">${_esc(name)}</span>
                      ${countBadge}
                    </li>`;
        }).join("");

        const statusItems = STATUS_OPTIONS.map(o => {
            const active = this._activeStatus === o.value ? "active" : "";
            const dataVal = o.value ?? "";
            return `<li class="status-filter-item ${active}" data-status="${_esc(dataVal)}">${_esc(o.label)}</li>`;
        }).join("");

        this.el.innerHTML = `
<p class="sidebar-section-title">Status</p>
<ul class="author-list status-filter-list">
  ${statusItems}
</ul>
<p class="sidebar-section-title" style="margin-top:var(--space-4)">Authors</p>
<ul class="author-list">
  <li class="author-item ${this._activeAuthor === null ? "active" : ""}"
      data-author="">All authors</li>
  ${items}
</ul>`;
    },

    _bindEvents() {
        this.el.addEventListener("click", e => {
            const statusItem = e.target.closest(".status-filter-item");
            if (statusItem) {
                const status = statusItem.dataset.status || null;
                this._activeStatus = status;
                this.el.querySelectorAll(".status-filter-item")
                    .forEach(el => el.classList.remove("active"));
                statusItem.classList.add("active");
                this.callbacks.onStatus?.(status);
                return;
            }

            const authorItem = e.target.closest(".author-item");
            if (!authorItem) return;
            const author = authorItem.dataset.author || null;
            this._activeAuthor = author;
            this.el.querySelectorAll(".author-item")
                .forEach(el => el.classList.remove("active"));
            authorItem.classList.add("active");
            this.callbacks.onAuthor?.(author);
        });
    },
};

function _esc(val) {
    return String(val ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
