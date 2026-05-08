/**
 * EditModal — native <dialog>-based metadata editor.
 * Usage: EditModal.open(bookId, title, author, coverPath)
 *        EditModal.close()
 * Dispatches "book-updated" on document with detail: updatedBook on save.
 */

import { editBook } from "../api.js";

let _dialog = null;
let _currentId = null;

export const EditModal = {
    /**
     * @param {string} bookId
     * @param {string} currentTitle
     * @param {string} currentAuthor
     * @param {string|null} currentCoverPath
     */
    open(bookId, currentTitle, currentAuthor, currentCoverPath = null) {
        _currentId = bookId;
        if (!_dialog) {
            _dialog = _buildDialog();
            document.body.appendChild(_dialog);
        }
        _populate(_dialog, currentTitle, currentAuthor, currentCoverPath);
        _dialog.showModal();
    },

    close() {
        _dialog?.close();
    },
};

// ---------------------------------------------------------------------------
// Build
// ---------------------------------------------------------------------------

function _buildDialog() {
    const d = document.createElement("dialog");
    d.className = "edit-modal";
    d.innerHTML = `
<div class="edit-modal-card">
  <h2 class="edit-modal-heading">Edit Metadata</h2>
  <div class="edit-modal-cover-row">
    <div class="edit-cover-preview" id="edit-cover-preview"></div>
    <label class="edit-cover-label">
      Change Cover
      <input type="file" id="edit-cover-input" accept="image/*" class="edit-file-input" />
    </label>
  </div>
  <div class="edit-fields">
    <label class="edit-field-label">
      Title
      <input type="text" id="edit-title" class="edit-text-input" />
    </label>
    <label class="edit-field-label">
      Author
      <input type="text" id="edit-author" class="edit-text-input" />
    </label>
  </div>
  <p class="edit-error" id="edit-error" hidden></p>
  <div class="edit-actions">
    <button class="btn-ghost" id="edit-cancel">Cancel</button>
    <button class="btn-primary" id="edit-save">Save</button>
  </div>
</div>`.trim();

    // Backdrop click closes
    d.addEventListener("click", e => { if (e.target === d) EditModal.close(); });

    d.querySelector("#edit-cancel").addEventListener("click", () => EditModal.close());

    d.querySelector("#edit-cover-input").addEventListener("change", e => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = ev => _setPreview(d, ev.target.result);
        reader.readAsDataURL(file);
    });

    d.querySelector("#edit-save").addEventListener("click", () => _save(d));

    return d;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _populate(d, title, author, coverPath) {
    d.querySelector("#edit-title").value = title || "";
    d.querySelector("#edit-author").value = author || "";
    d.querySelector("#edit-cover-input").value = "";
    _setPreview(d, coverPath);
    const err = d.querySelector("#edit-error");
    err.hidden = true;
    err.textContent = "";
}

function _setPreview(d, src) {
    const el = d.querySelector("#edit-cover-preview");
    if (src) {
        el.innerHTML = `<img src="${src}" alt="Cover preview" />`;
    } else {
        el.innerHTML = `<span class="edit-cover-placeholder">No cover</span>`;
    }
}

async function _save(d) {
    const saveBtn = d.querySelector("#edit-save");
    const errEl   = d.querySelector("#edit-error");

    saveBtn.disabled = true;
    errEl.hidden = true;

    const fd     = new FormData();
    const title  = d.querySelector("#edit-title").value.trim();
    const author = d.querySelector("#edit-author").value.trim();
    const file   = d.querySelector("#edit-cover-input").files[0];

    if (title)  fd.append("title",  title);
    if (author) fd.append("author", author);
    if (file)   fd.append("cover",  file);

    try {
        const updated = await editBook(_currentId, fd);
        document.dispatchEvent(new CustomEvent("book-updated", { detail: updated }));
        EditModal.close();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
    } finally {
        saveBtn.disabled = false;
    }
}
