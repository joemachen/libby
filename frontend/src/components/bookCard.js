/**
 * bookCard — pure rendering function, no DOM state.
 * Returns an HTML string for a single book.
 * All event handling is done via delegation in bookGrid.js.
 */

/**
 * Render a book as an HTML article string.
 * @param {object} book
 * @param {{ onDevice?: boolean, selected?: boolean }} [opts]
 * @returns {string}
 */
export function renderBookCard(book, { onDevice = false, selected = false } = {}) {
    const cover = book.cover_path
        ? `<img src="${esc(book.cover_path)}" alt="${esc(book.title)}" loading="lazy" />`
        : coverPlaceholder(book);

    const statusLabel = { unread: "Unread", reading: "Reading", read: "Read" };
    const status = book.read_status || "unread";
    const nextLabel = { unread: "mark Reading", reading: "mark Read", read: "mark Unread" }[status];
    const statusDot = `<span class="status-dot status-${esc(status)}"
        data-action="cycle-status" data-id="${esc(book.id)}" data-status="${esc(status)}"
        title="${esc(statusLabel[status])} — click to ${esc(nextLabel)}"></span>`;

    const onDeviceBadge = onDevice
        ? `<span class="on-kobo-badge" title="Already on device">On device</span>`
        : "";

    // Checkbox shown in selection mode (CSS hides it otherwise)
    const checkbox = `<label class="card-select" title="Select">
      <input type="checkbox" class="card-checkbox" data-action="select"
             data-id="${esc(book.id)}" ${selected ? "checked" : ""} />
    </label>`;

    return `
<article class="book-card" data-id="${esc(book.id)}" ${selected ? 'data-selected="true"' : ""}>
  <div class="book-cover">
    ${cover}
    ${onDeviceBadge}
    ${checkbox}
    <div class="book-actions" aria-hidden="true">
      <button class="action-btn send-btn"
              data-action="send" data-id="${esc(book.id)}"
              title="Send to device">📤 Send to device</button>
      <button class="action-btn edit-btn"
              data-action="edit" data-id="${esc(book.id)}"
              title="Edit metadata">✏️ Edit</button>
    </div>
  </div>
  <div class="book-meta">
    <div class="book-title-row">
      <h3 class="book-title" title="${esc(book.title)}">${esc(book.title)}</h3>
      ${statusDot}
    </div>
    ${book.author
        ? `<p class="book-author" title="${esc(book.author)}">${esc(book.author)}</p>`
        : ""}
  </div>
</article>`.trim();
}

/**
 * Generate a CSS-only cover placeholder with a deterministic hue from the title.
 * @param {object} book
 * @returns {string}
 */
function coverPlaceholder(book) {
    const hue = titleHue(book.title);
    const initial = esc((book.title || "?")[0].toUpperCase());
    return `<div class="cover-placeholder" style="--hue:${hue}">
  <span class="cover-initial">${initial}</span>
</div>`;
}

/**
 * Map a title string to a 0–359 hue value (deterministic).
 * @param {string} title
 * @returns {number}
 */
export function titleHue(title) {
    let h = 0;
    for (const ch of String(title ?? "")) {
        h = Math.imul(h, 31) + ch.charCodeAt(0);
    }
    return Math.abs(h % 360);
}

/**
 * Escape a value for safe insertion into HTML attribute or text content.
 * @param {unknown} val
 * @returns {string}
 */
export function esc(val) {
    return String(val ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
