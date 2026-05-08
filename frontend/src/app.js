/**
 * app.js — entry point.
 * Owns all application state and coordinates the components.
 * Components render; app.js decides when and with what data.
 */

import { getBooks, scanLibrary, updateReadStatus } from "./api.js";
import { BookGrid   } from "./components/bookGrid.js";
import { SearchBar  } from "./components/searchBar.js";
import { Sidebar    } from "./components/sidebar.js";
import { KoboPanel  } from "./components/koboPanel.js";
import { EditModal     } from "./components/editModal.js";
import { SettingsModal } from "./components/settingsModal.js";

// ── Application state ─────────────────────────────────────────────────────────

const state = {
    books:        [],
    total:        0,
    page:         1,
    pages:        1,
    search:       "",
    author:       null,   // null = all authors
    statusFilter: null,   // null = all statuses
    sort:         "title",
    loading:      false,
    scanning:     false,
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────

async function init() {
    KoboPanel.init(document.getElementById("kobo-panel"), {
        onConnected:    device => toast(`Kobo connected — ${_fmtBytes(device.free_space)} free.`, "success"),
        onDisconnected: ()     => toast("Kobo disconnected.", "info"),
        onSent:  (title, res)  => toast(`"${title}" sent to Kobo (${_fmtBytes(res.bytes_transferred)}).`, "success"),
        onError: msg           => toast(msg, "error"),
    });

    BookGrid.init(document.getElementById("book-grid"), {
        onSend: (id, title) => KoboPanel.sendBook(id, title),
        onEdit: (id, title) => {
            const book = state.books.find(b => b.id === id);
            EditModal.open(id, book?.title ?? title, book?.author ?? "", book?.cover_path ?? null);
        },
        onCycleStatus: handleCycleStatus,
    });

    SearchBar.init(document.getElementById("search-bar"), {
        onSearch: term => {
            state.search = term;
            state.page   = 1;
            loadBooks();
        },
        onSort: sort => {
            state.sort = sort;
            state.page = 1;
            loadBooks();
        },
        onScan: handleScan,
        onPage: dir => {
            state.page = dir === "prev"
                ? Math.max(1, state.page - 1)
                : Math.min(state.pages, state.page + 1);
            loadBooks();
        },
    });

    Sidebar.init(document.getElementById("sidebar"), {
        onAuthor: author => {
            state.author = author;
            state.page   = 1;
            loadBooks();
        },
        onStatus: status => {
            state.statusFilter = status;
            state.page         = 1;
            loadBooks();
        },
    });

    document.getElementById("settings-btn").addEventListener("click", () => SettingsModal.open());

    _initSidebarToggle();

    document.addEventListener("book-updated", e => {
        const updated = e.detail;
        const idx = state.books.findIndex(b => b.id === updated.id);
        if (idx !== -1) state.books[idx] = updated;
        _render();
    });

    await loadBooks();
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadBooks() {
    state.loading = true;
    _render();

    try {
        const result = await getBooks({
            page:   state.page,
            sort:   state.sort,
            search: state.search        || undefined,
            author: state.author        || undefined,
            status: state.statusFilter  || undefined,
        });
        state.books  = result.books;
        state.total  = result.total;
        state.page   = result.page;
        state.pages  = result.pages;
    } catch (err) {
        toast(err.message, "error");
        state.books = [];
        state.total = 0;
    } finally {
        state.loading = false;
        _render();
    }
}

async function handleScan() {
    if (state.scanning) return;
    state.scanning = true;
    SearchBar.setScanning(true);

    try {
        const result = await scanLibrary();
        const { added, updated, errors, scanned } = result;
        const msg = `Scan complete — ${scanned} found, ${added} added, ${updated} updated` +
                    (errors ? `, ${errors} errors` : ".");
        toast(msg, added + updated > 0 ? "success" : "info");
        state.page = 1;
        await loadBooks();
        await Sidebar.loadAuthors();
    } catch (err) {
        toast(err.message, "error");
    } finally {
        state.scanning = false;
        SearchBar.setScanning(false);
    }
}

async function handleCycleStatus(id, currentStatus) {
    const next = { unread: "reading", reading: "read", read: "unread" }[currentStatus] ?? "reading";
    try {
        const updated = await updateReadStatus(id, next);
        const idx = state.books.findIndex(b => b.id === id);
        if (idx !== -1) state.books[idx] = updated;
        _render();
    } catch (err) {
        toast(err.message, "error");
    }
}

// ── Render ────────────────────────────────────────────────────────────────────

function _render() {
    BookGrid.render(state);
    SearchBar.renderMeta(state.total, state.page, state.pages);
    Sidebar.setActiveAuthor(state.author);
    Sidebar.setActiveStatus(state.statusFilter);
}

// ── Toast notifications ───────────────────────────────────────────────────────

/**
 * Show a temporary notification banner.
 * @param {string} message
 * @param {"info"|"success"|"error"} type
 */
function toast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.textContent = message;
    container.appendChild(el);

    // Trigger CSS transition on next frame
    requestAnimationFrame(() => {
        requestAnimationFrame(() => el.classList.add("toast-visible"));
    });

    setTimeout(() => {
        el.classList.remove("toast-visible");
        el.addEventListener("transitionend", () => el.remove(), { once: true });
    }, 4000);
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function _fmtBytes(n) {
    for (const u of ["B", "KB", "MB", "GB"]) {
        if (n < 1024) return `${n.toFixed(1)} ${u}`;
        n /= 1024;
    }
    return `${n.toFixed(1)} TB`;
}

// ── Sidebar drawer toggle (mobile) ────────────────────────────────────────────

function _initSidebarToggle() {
    const toggleBtn = document.getElementById("sidebar-toggle");
    const sidebar   = document.getElementById("sidebar");
    const overlay   = document.getElementById("sidebar-overlay");
    if (!toggleBtn || !sidebar || !overlay) return;

    function _openSidebar() {
        sidebar.classList.add("sidebar--open");
        overlay.classList.add("visible");
        toggleBtn.setAttribute("aria-expanded", "true");
    }

    function _closeSidebar() {
        sidebar.classList.remove("sidebar--open");
        overlay.classList.remove("visible");
        toggleBtn.setAttribute("aria-expanded", "false");
    }

    toggleBtn.addEventListener("click", () => {
        sidebar.classList.contains("sidebar--open") ? _closeSidebar() : _openSidebar();
    });

    overlay.addEventListener("click", _closeSidebar);

    // Auto-close when a filter is picked on narrow screens
    sidebar.addEventListener("click", e => {
        if (e.target.closest(".author-item, .status-filter-item")) {
            if (window.matchMedia("(max-width: 768px)").matches) _closeSidebar();
        }
    });
}

// ── Start ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", init);
