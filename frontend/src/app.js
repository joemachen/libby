/**
 * app.js — entry point.
 * Owns all application state and coordinates the components.
 * Components render; app.js decides when and with what data.
 */

import { getBooks, scanLibrary, updateReadStatus, getDeviceBooks } from "./api.js";
import { BookGrid    } from "./components/bookGrid.js";
import { SearchBar   } from "./components/searchBar.js";
import { Sidebar     } from "./components/sidebar.js";
import { DevicePanel } from "./components/devicePanel.js";
import { DeviceShelf } from "./components/deviceShelf.js";
import { EditModal     } from "./components/editModal.js";
import { SettingsModal } from "./components/settingsModal.js";

// ── Application state ─────────────────────────────────────────────────────────

const state = {
    books:         [],
    total:         0,
    page:          1,
    pages:         1,
    search:        "",
    author:        null,   // null = all authors
    statusFilter:  null,   // null = all statuses
    sort:          "title",
    loading:       false,
    scanning:      false,
    deviceFilenames: new Set(),  // filenames currently on the connected device
    selectionMode: false,
};

// ── Bootstrap ─────────────────────────────────────────────────────────────────

async function init() {
    DeviceShelf.init();

    DevicePanel.init(document.getElementById("device-panel"), {
        onConnected: async device => {
            toast(`Device connected — ${_fmtBytes(device.free_space)} free.`, "success");
            await _refreshDeviceFilenames();
        },
        onDisconnected: () => {
            toast("Device disconnected.", "info");
            state.deviceFilenames = new Set();
            _render();
        },
        onSent:     (title, res) => toast(`"${title}" sent to device (${_fmtBytes(res.bytes_transferred)}).`, "success"),
        onBulkSent: results      => _handleBulkSentResults(results),
        onEjected:  ()           => toast("Device ejected safely.", "success"),
        onShelfOpen: ()          => DeviceShelf.open(),
        onError: msg             => toast(msg, "error"),
    });

    BookGrid.init(document.getElementById("book-grid"), {
        onSend: (id, title) => KoboPanel.sendBook(id, title),
        onEdit: (id, title) => {
            const book = state.books.find(b => b.id === id);
            EditModal.open(id, book?.title ?? title, book?.author ?? "", book?.cover_path ?? null);
        },
        onCycleStatus: handleCycleStatus,
        onBulkSend: ids => DevicePanel.sendBooks(ids),
        onSelectToggle: () => {
            // Called when the bulk-bar Cancel button is pressed
            state.selectionMode = false;
            SearchBar.setSelectionMode(false);
        },
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
        onSelectToggle: () => {
            state.selectionMode = BookGrid.toggleSelectionMode();
            // If pagination changes page, selection clears — keep button in sync
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
    // Selection is per-page only — clear when reloading
    if (state.selectionMode) {
        BookGrid.clearSelection();
    }
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
    BookGrid.render(state, state.deviceFilenames);
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

// ── Kobo helpers ──────────────────────────────────────────────────────────────

/** Fetch the list of EPUBs on the device and update state.deviceFilenames. */
async function _refreshDeviceFilenames() {
    try {
        const books = await getDeviceBooks();
        state.deviceFilenames = new Set(books.map(b => b.filename));
        _render();
    } catch {
        // Device may have been ejected between poll and fetch — ignore
    }
}

/**
 * Show a toast summarising bulk-send results.
 * @param {Array<{id: string, title: string, ok: boolean, error: string}>} results
 */
function _handleBulkSentResults(results) {
    const sent   = results.filter(r => r.ok).length;
    const failed = results.filter(r => !r.ok).length;
    if (failed === 0) {
        toast(`${sent} book${sent !== 1 ? "s" : ""} sent to Kobo.`, "success");
    } else {
        const failTitles = results.filter(r => !r.ok).map(r => `"${r.title}"`).join(", ");
        toast(`${sent} sent, ${failed} failed: ${failTitles}`, "error");
    }
    // Exit selection mode after send
    if (state.selectionMode) {
        state.selectionMode = false;
        BookGrid.toggleSelectionMode();
        SearchBar.setSelectionMode(false);
    }
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
