/**
 * bookGrid — renders the cover grid and handles all card-level interactions
 * via event delegation (one listener for the whole grid).
 *
 * Selection mode: toggled by toggleSelectionMode(). While active, clicking a
 * card toggles its selection instead of triggering send/edit actions. A fixed
 * bulk-action bar appears at the bottom of the viewport.
 */

import { renderBookCard, titleHue, esc } from "./bookCard.js";

export const BookGrid = {
    el: null,
    _bulkBar: null,
    callbacks: {},

    // Selection state
    _selectionMode: false,
    _selected: new Set(),   // Set of book ids

    /**
     * Mount the component.
     * @param {HTMLElement} container
     * @param {{ onSend?: Function, onEdit?: Function, onCycleStatus?: Function, onBulkSend?: Function }} callbacks
     */
    init(container, callbacks = {}) {
        this.el = container;
        this.callbacks = callbacks;
        this._bulkBar = this._createBulkBar();
        this._bindEvents();
    },

    /**
     * Re-render the grid from the current app state.
     * @param {{ books: object[], loading: boolean, search: string, author: string|null }} state
     * @param {Set<string>} [koboFilenames]  – filenames currently on the Kobo device
     */
    render(state, koboFilenames = new Set()) {
        const { books, loading, search, author } = state;

        if (loading) {
            this.el.innerHTML = this._skeletons(10);
            this._updateBulkBar();
            return;
        }

        if (!books.length) {
            const hasFilter = (search && search.trim()) || author;
            this.el.innerHTML = hasFilter
                ? this._noResultsHTML()
                : this._emptyLibraryHTML();
            this._updateBulkBar();
            return;
        }

        this.el.innerHTML = books.map(book => {
            const filename = (book.file_path || "").split(/[\\/]/).pop();
            return renderBookCard(book, {
                onDevice: koboFilenames.has(filename),
                selected:  this._selected.has(book.id),
            });
        }).join("\n");

        this._updateBulkBar();
    },

    // ── Selection API ─────────────────────────────────────────────────────────

    /** Toggle selection mode on/off. Clears selection when turning off. */
    toggleSelectionMode() {
        this._selectionMode = !this._selectionMode;
        if (!this._selectionMode) this._selected.clear();
        this.el.classList.toggle("selection-mode", this._selectionMode);
        this._updateBulkBar();
        return this._selectionMode;
    },

    /** @returns {string[]} IDs of currently selected books. */
    getSelectedIds() {
        return [...this._selected];
    },

    /** Clear selection without leaving selection mode. */
    clearSelection() {
        this._selected.clear();
        this.el.querySelectorAll(".book-card[data-selected]").forEach(card => {
            card.removeAttribute("data-selected");
            const cb = card.querySelector(".card-checkbox");
            if (cb) cb.checked = false;
        });
        this._updateBulkBar();
    },

    // ── Private ──────────────────────────────────────────────────────────────

    _bindEvents() {
        this.el.addEventListener("click", e => {
            // Checkbox click — always handle regardless of mode
            const cb = e.target.closest(".card-checkbox");
            if (cb) {
                e.stopPropagation();
                this._toggleSelect(cb.dataset.id, cb.checked);
                return;
            }

            // In selection mode, clicking anywhere on the card toggles selection
            if (this._selectionMode) {
                const card = e.target.closest(".book-card");
                if (!card) return;
                e.stopPropagation();
                const id = card.dataset.id;
                const nowSelected = !this._selected.has(id);
                this._toggleSelect(id, nowSelected);
                const cardCb = card.querySelector(".card-checkbox");
                if (cardCb) cardCb.checked = nowSelected;
                return;
            }

            // Normal mode — action buttons
            const btn = e.target.closest("[data-action]");
            if (!btn) return;
            e.stopPropagation();
            const { action, id } = btn.dataset;
            const title = btn.closest(".book-card")
                ?.querySelector(".book-title")?.textContent ?? "";
            if (action === "send")         this.callbacks.onSend?.(id, title);
            if (action === "edit")         this.callbacks.onEdit?.(id, title);
            if (action === "cycle-status") this.callbacks.onCycleStatus?.(id, btn.dataset.status);
        });

        // Broken cover images — replace with placeholder without re-rendering
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
                    style:     `--hue:${hue}`,
                })
            );
        }, true);
    },

    _toggleSelect(id, nowSelected) {
        if (nowSelected) {
            this._selected.add(id);
        } else {
            this._selected.delete(id);
        }
        // Update card attribute for CSS styling
        const card = this.el.querySelector(`.book-card[data-id="${id}"]`);
        if (card) {
            card.toggleAttribute("data-selected", nowSelected);
        }
        this._updateBulkBar();
    },

    _createBulkBar() {
        const bar = document.createElement("div");
        bar.className = "bulk-action-bar";
        bar.setAttribute("aria-live", "polite");
        bar.innerHTML = `
<span class="bulk-count"></span>
<div class="bulk-actions">
  <button class="btn-primary bulk-send-btn" disabled>📤 Send to Kobo</button>
  <button class="btn-ghost bulk-cancel-btn">Cancel</button>
</div>`;

        bar.querySelector(".bulk-send-btn").addEventListener("click", () => {
            const ids = this.getSelectedIds();
            if (ids.length) this.callbacks.onBulkSend?.(ids);
        });

        bar.querySelector(".bulk-cancel-btn").addEventListener("click", () => {
            if (this._selectionMode) this.toggleSelectionMode();
            this.callbacks.onSelectToggle?.();
        });

        document.body.appendChild(bar);
        return bar;
    },

    /** Sync the bulk-action bar with current selection state. */
    _updateBulkBar() {
        if (!this._bulkBar) return;
        const count = this._selected.size;
        const visible = this._selectionMode;
        this._bulkBar.classList.toggle("bulk-bar-visible", visible);
        this._bulkBar.querySelector(".bulk-count").textContent =
            count === 0 ? "No books selected"
            : count === 1 ? "1 book selected"
            : `${count} books selected`;
        const sendBtn = this._bulkBar.querySelector(".bulk-send-btn");
        sendBtn.disabled = count === 0;
        // Send button stays disabled when no Kobo — kobo.css rule handles the
        // pointer-events; here we also disable it for non-connected state via
        // the app-level kobo-connected class.
        sendBtn.classList.toggle(
            "kobo-send-inactive",
            !document.getElementById("app")?.classList.contains("kobo-connected")
        );
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
