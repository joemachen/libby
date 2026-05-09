/**
 * Centralised API client. All fetch() calls live here.
 * Components import functions from this module — never call fetch() directly.
 */

const BASE = "";  // Same origin — Flask serves both API and frontend

/**
 * Shared fetch wrapper. Throws on non-2xx responses with the server's message.
 * @param {string} path
 * @param {RequestInit} [options]
 * @returns {Promise<any>} Parsed JSON data field
 */
async function request(path, options = {}) {
    const res = await fetch(BASE + path, options);
    const json = await res.json();
    if (!res.ok || json.status === "error") {
        const msg = json.message ?? `HTTP ${res.status}`;
        throw new Error(msg);
    }
    return json.data ?? json;
}

// ── Health ───────────────────────────────────────────────────────────────────

/** @returns {Promise<{status: string}>} */
export async function getHealth() {
    return request("/api/health");
}

// ── Books ────────────────────────────────────────────────────────────────────

/**
 * @param {{ page?: number, limit?: number, search?: string, author?: string, status?: string, sort?: string }} [params]
 * @returns {Promise<{books: object[], total: number, page: number, pages: number}>}
 */
export async function getBooks(params = {}) {
    const qs = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
    ).toString();
    return request(`/api/books${qs ? "?" + qs : ""}`);
}

/**
 * Trigger a library scan.
 * @returns {Promise<{scanned: number, added: number, updated: number}>}
 */
export async function scanLibrary() {
    return request("/api/scan", { method: "POST" });
}

/**
 * Update read status for a book.
 * @param {string} id
 * @param {"unread"|"reading"|"read"} status
 * @returns {Promise<object>} Updated book
 */
export async function updateReadStatus(id, status) {
    return request(`/api/books/${id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ read_status: status }),
    });
}

/**
 * Edit book metadata (title, author, cover image).
 * @param {string} id
 * @param {FormData} formData
 * @returns {Promise<object>} Updated book
 */
export async function editBook(id, formData) {
    return request(`/api/books/${id}/edit`, { method: "POST", body: formData });
}

// ── Settings ─────────────────────────────────────────────────────────────────

/** @returns {Promise<{library_path: string}>} */
export async function getSettings() {
    return request("/api/settings");
}

/** @returns {Promise<{path: string|null}>} Selected folder path, or null if cancelled. */
export async function browseFolder() {
    return request("/api/settings/browse");
}

/**
 * @param {{ library_path?: string }} settings
 * @returns {Promise<object>} Updated fields
 */
export async function updateSettings(settings) {
    return request("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
    });
}

// ── Authors ──────────────────────────────────────────────────────────────────

/** @returns {Promise<string[]>} Sorted list of author names. */
export async function getAuthors() {
    return request("/api/authors");
}

// ── Kobo ─────────────────────────────────────────────────────────────────────

/** @returns {Promise<{connected: boolean, device?: object}>} */
export async function getKoboStatus() {
    return request("/api/kobo/status");
}

/**
 * Send a book to the connected Kobo.
 * @param {string} bookId
 * @returns {Promise<{bytes_transferred: number}>}
 */
export async function sendToKobo(bookId) {
    return request("/api/kobo/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book_id: bookId }),
    });
}

/**
 * Send multiple books to the Kobo in one request.
 * @param {string[]} bookIds
 * @returns {Promise<{results: Array<{id:string, title:string|null, ok:boolean, error?:string}>}>}
 */
export async function bulkSendToKobo(bookIds) {
    return request("/api/kobo/send/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book_ids: bookIds }),
    });
}

/** Safely eject the connected Kobo from the OS. */
export async function ejectKobo() {
    return request("/api/kobo/eject", { method: "POST" });
}

/**
 * List all EPUBs on the Kobo, cross-referenced with the local library.
 * @returns {Promise<Array<{filename:string, in_library:boolean, book_id:string|null, title:string|null, author:string|null, cover_path:string|null}>>}
 */
export async function getKoboBooks() {
    return request("/api/kobo/books");
}
