/**
 * SettingsModal — gear-icon panel for library path and theme.
 * Usage: SettingsModal.open()  /  SettingsModal.close()
 * Theme is applied immediately on radio change; reverted on Cancel.
 */

import { getSettings, updateSettings, browseFolder } from "../api.js";

const THEME_KEY = "libby-theme";

let _dialog     = null;
let _snapTheme  = null;   // theme when modal opened — restored on cancel

export const SettingsModal = {
    async open() {
        if (!_dialog) {
            _dialog = _build();
            document.body.appendChild(_dialog);
        }
        _snapTheme = _getTheme();
        await _populate(_dialog);
        _dialog.showModal();
    },

    close() {
        _dialog?.close();
    },
};

// ---------------------------------------------------------------------------
// Theme helpers (used by init script in index.html too, via localStorage)
// ---------------------------------------------------------------------------

function _getTheme() {
    return localStorage.getItem(THEME_KEY) || "system";
}

function _applyTheme(t) {
    if (t === "system") {
        document.documentElement.removeAttribute("data-theme");
    } else {
        document.documentElement.setAttribute("data-theme", t);
    }
    localStorage.setItem(THEME_KEY, t);
}

// ---------------------------------------------------------------------------
// Build
// ---------------------------------------------------------------------------

function _build() {
    const d = document.createElement("dialog");
    d.className = "settings-modal";
    d.innerHTML = `
<div class="settings-card">
  <h2 class="settings-heading">Settings</h2>

  <section class="settings-section">
    <h3 class="settings-section-title">Library</h3>
    <label class="settings-field-label">
      Folder path
      <div class="settings-path-row">
        <input type="text" id="settings-library-path" class="settings-text-input"
               placeholder="/path/to/your/books" spellcheck="false" />
        <button type="button" class="btn-ghost settings-browse-btn" id="settings-browse">Browse…</button>
      </div>
    </label>
    <p class="settings-hint">The folder scanned for EPUB files. Takes effect on the next scan.</p>
  </section>

  <section class="settings-section">
    <h3 class="settings-section-title">Theme</h3>
    <div class="settings-radio-group">
      <label class="settings-radio-label">
        <input type="radio" name="theme" value="system" />
        System default
      </label>
      <label class="settings-radio-label">
        <input type="radio" name="theme" value="dark" />
        Dark
      </label>
      <label class="settings-radio-label">
        <input type="radio" name="theme" value="light" />
        Light
      </label>
    </div>
  </section>

  <p class="settings-error" id="settings-error" hidden></p>

  <div class="settings-actions">
    <button class="btn-ghost" id="settings-cancel">Cancel</button>
    <button class="btn-primary" id="settings-save">Save</button>
  </div>
</div>`.trim();

    // Backdrop click
    d.addEventListener("click", e => { if (e.target === d) _cancel(d); });

    // Cancel
    d.querySelector("#settings-cancel").addEventListener("click", () => _cancel(d));

    // Live theme preview
    d.querySelectorAll("input[name='theme']").forEach(radio => {
        radio.addEventListener("change", () => {
            if (radio.checked) _applyTheme(radio.value);
        });
    });

    // Browse button — opens native OS folder picker via server
    d.querySelector("#settings-browse").addEventListener("click", () => _browse(d));

    // Save
    d.querySelector("#settings-save").addEventListener("click", () => _save(d));

    return d;
}

// ---------------------------------------------------------------------------
// Populate / cancel / save
// ---------------------------------------------------------------------------

async function _populate(d) {
    const errEl = d.querySelector("#settings-error");
    errEl.hidden = true;
    errEl.textContent = "";

    // Theme radios — set from localStorage immediately (no API needed)
    const current = _getTheme();
    d.querySelectorAll("input[name='theme']").forEach(r => {
        r.checked = r.value === current;
    });

    // Library path — fetch from server
    try {
        const data = await getSettings();
        d.querySelector("#settings-library-path").value = data.library_path || "";
    } catch {
        d.querySelector("#settings-library-path").value = "";
    }
}

async function _browse(d) {
    const btn   = d.querySelector("#settings-browse");
    const input = d.querySelector("#settings-library-path");
    btn.disabled = true;
    try {
        const { path } = await browseFolder();
        if (path) input.value = path;
    } catch (err) {
        // Non-fatal: user cancelled or tkinter unavailable — leave input unchanged
        const errEl = d.querySelector("#settings-error");
        errEl.textContent = err.message;
        errEl.hidden = false;
    } finally {
        btn.disabled = false;
    }
}

function _cancel(d) {
    // Revert live theme preview if it changed
    if (_snapTheme !== null) _applyTheme(_snapTheme);
    SettingsModal.close();
}

async function _save(d) {
    const saveBtn = d.querySelector("#settings-save");
    const errEl   = d.querySelector("#settings-error");
    saveBtn.disabled = true;
    errEl.hidden = true;

    const libraryPath = d.querySelector("#settings-library-path").value.trim();
    const theme = [...d.querySelectorAll("input[name='theme']")]
        .find(r => r.checked)?.value || "system";

    try {
        if (libraryPath) {
            await updateSettings({ library_path: libraryPath });
        }
        _applyTheme(theme);   // persist chosen theme to localStorage
        _snapTheme = theme;
        SettingsModal.close();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
    } finally {
        saveBtn.disabled = false;
    }
}
