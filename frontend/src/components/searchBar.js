/**
 * searchBar — search input, sort selector, scan button, and book count/pagination.
 */

const SORT_OPTIONS = [
    { value: "title",      label: "Sort: Title" },
    { value: "author",     label: "Sort: Author" },
    { value: "date_added", label: "Sort: Date Added" },
];

export const SearchBar = {
    el: null,
    callbacks: {},
    _searchInput: null,
    _scanBtn: null,
    _selectBtn: null,
    _countText: null,
    _prevBtn: null,
    _nextBtn: null,
    _pageInfo: null,
    _selectMode: false,

    /**
     * Mount and wire the search bar.
     * @param {HTMLElement} container
     * @param {{ onSearch, onSort, onScan, onPage, onSelectToggle }} callbacks
     */
    init(container, callbacks) {
        this.el = container;
        this.callbacks = callbacks;
        this._render();
        this._bindEvents();
    },

    /**
     * Sync the Select button visual state — call when selection mode is
     * cancelled externally (e.g. via the bulk-bar Cancel button).
     * @param {boolean} active
     */
    setSelectionMode(active) {
        this._selectMode = active;
        if (!this._selectBtn) return;
        this._selectBtn.classList.toggle("active", active);
        this._selectBtn.textContent = active ? "Cancel Select" : "Select";
    },

    /** Update scan button state while a scan is in progress. */
    setScanning(scanning) {
        if (!this._scanBtn) return;
        this._scanBtn.disabled = scanning;
        this._scanBtn.textContent = scanning ? "Scanning…" : "Scan Library";
    },

    /** Update the count row and pagination controls. */
    renderMeta(total, page, pages) {
        if (!this._countText) return;

        if (total === 0) {
            this._countText.textContent = "";
        } else {
            this._countText.textContent =
                `${total} book${total !== 1 ? "s" : ""}`;
        }

        if (!this._pageInfo) return;

        if (pages <= 1) {
            this._prevBtn.hidden = true;
            this._nextBtn.hidden = true;
            this._pageInfo.hidden = true;
        } else {
            this._prevBtn.hidden = false;
            this._nextBtn.hidden = false;
            this._pageInfo.hidden = false;
            this._prevBtn.disabled = page <= 1;
            this._nextBtn.disabled = page >= pages;
            this._pageInfo.textContent = `Page ${page} / ${pages}`;
        }
    },

    // ── Private ──────────────────────────────────────────────────────────────

    _render() {
        this.el.innerHTML = `
<div class="search-bar-inner">
  <input
    type="search"
    id="search-input"
    class="search-input"
    placeholder="Search by title or author…"
    autocomplete="off"
    spellcheck="false"
  />
  <select id="sort-select" class="sort-select">
    ${SORT_OPTIONS.map(o =>
        `<option value="${o.value}">${o.label}</option>`
    ).join("")}
  </select>
  <button id="select-btn" class="btn-ghost select-toggle-btn">Select</button>
  <button id="scan-btn" class="btn-primary" style="margin-left:auto">
    Scan Library
  </button>
</div>
<div class="book-count-bar">
  <span id="book-count-text" class="book-count-text"></span>
  <div class="pagination-controls">
    <button id="prev-page" class="btn-icon" title="Previous page" hidden>‹</button>
    <span   id="page-info"  class="page-info"                          hidden></span>
    <button id="next-page" class="btn-icon" title="Next page"     hidden>›</button>
  </div>
</div>`;

        this._searchInput = this.el.querySelector("#search-input");
        this._selectBtn   = this.el.querySelector("#select-btn");
        this._scanBtn     = this.el.querySelector("#scan-btn");
        this._countText   = this.el.querySelector("#book-count-text");
        this._prevBtn     = this.el.querySelector("#prev-page");
        this._nextBtn     = this.el.querySelector("#next-page");
        this._pageInfo    = this.el.querySelector("#page-info");
    },

    _bindEvents() {
        const debouncedSearch = _debounce(
            term => this.callbacks.onSearch?.(term), 300
        );

        this._searchInput.addEventListener("input", e =>
            debouncedSearch(e.target.value)
        );

        this.el.querySelector("#sort-select").addEventListener("change", e =>
            this.callbacks.onSort?.(e.target.value)
        );

        this._selectBtn.addEventListener("click", () => {
            this._selectMode = !this._selectMode;
            this._selectBtn.classList.toggle("active", this._selectMode);
            this._selectBtn.textContent = this._selectMode ? "Cancel Select" : "Select";
            this.callbacks.onSelectToggle?.();
        });

        this._scanBtn.addEventListener("click", () =>
            this.callbacks.onScan?.()
        );

        this._prevBtn.addEventListener("click", () =>
            this.callbacks.onPage?.("prev")
        );

        this._nextBtn.addEventListener("click", () =>
            this.callbacks.onPage?.("next")
        );
    },
};

function _debounce(fn, ms) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}
