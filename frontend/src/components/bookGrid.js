/**
 * bookGrid — renders the cover grid and handles all card-level interactions
 * via event delegation (one listener for the whole grid).
 */

import { renderBookCard, titleHue, esc } from "./bookCard.js";

export const BookGrid = {
    el: null,
    callbacks: {},

    /**
     * Mount the component.
     * @param {HTMLElement} container
     * @param {{ onSend?: Function, onEdit?: Function }} callbacks
     */
    init(container, callbacks = {}) {
        this.el = container;
        this.callbacks = callbacks;
        this._bindEvents();
    },

    /**
     * Re-render the grid from the current app state.
     * @param {{ books: object[], loading: boolean, search: string, author: string|null }} state
     */
    render(state) {
        const { books, loading, search, author } = state;

        if (loading) {
            this.el.innerHTML = this._skeletons(10);
            return;
        }

        if (!books.length) {
            const hasFilter = (search && search.trim()) || author;
            this.el.innerHTML = hasFilter
                ? this._noResultsHTML()
                : this._emptyLibraryHTML();
            return;
        }

        this.el.innerHTML = books.map(renderBookCard).join("\n");
    },

    // ── Private ──────────────────────────────────────────────────────────────

    _bindEvents() {
        // Action buttons (send / edit) — single delegated listener
        this.el.addEventListener("click", e => {
            const btn = e.target.closest("[data-action]");
            if (!btn) return;
            e.stopPropagation();
            const { action, id } = btn.dataset;
            const title = btn.closest(".book-card")
                ?.querySelector(".book-title")?.textContent ?? "";
            if (action === "send") this.callbacks.onSend?.(id, title);
            if (action === "edit") this.callbacks.onEdit?.(id, title);
            if (action === "cycle-status") this.callbacks.onCycleStatus?.(id, btn.dataset.status);
        });

        // Broken cover images — replace with placeholder without re-rendering
        // Error events don't bubble so we use capture phase
        document.addEventListener("error", e => {
            const img = e.target;
            if (img.tagName !== "IMG" || !img.closest(".book-cover")) return;
            const coverEl = img.closest(".book-cover");
            const title = img.closest(".book-card")
                ?.querySelector(".book-title")?.textContent ?? "?";
            const hue = titleHue(title);
            const initial = esc((title || "?")[0].toUpperCase());
            img.replaceWith(
                Object.assign(document.createElement("div"), {
                    className: "cover-placeholder",
                    innerHTML: `<span class="cover-initial">${initial}</span>`,
                    style: `--hue:${hue}`,
                })
            );
        }, true);
    },

    _skeletons(n) {
        return Array.from({ length: n }, () => `
<div class="book-card book-card-skeleton">
  <div class="book-cover"></div>
  <div class="book-meta">
    <div class="skeleton-line"></div>
    <div class="skeleton-line skeleton-line-short"></div>
  </div>
</div>`).join("\n");
    },

    _emptyLibraryHTML() {
        return `
<div class="empty-state">
  <div class="empty-icon">📚</div>
  <h2>Your library is empty</h2>
  <p>Click <strong>Scan Library</strong> to import books from your configured folder,
     or set <code>LIBRARY_PATH</code> in your <code>.env</code> file first.</p>
</div>`;
    },

    _noResultsHTML() {
        return `
<div class="empty-state">
  <div class="empty-icon">🔍</div>
  <h2>No results</h2>
  <p>No books match your current search or filter. Try different terms or clear the filter in the sidebar.</p>
</div>`;
    },
};
