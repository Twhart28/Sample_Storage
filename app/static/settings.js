(() => {
  const bootstrapNode = document.getElementById("settings-bootstrap");
  const clientRoot = document.querySelector("[data-settings-client]");
  if (!bootstrapNode || !clientRoot) {
    return;
  }

  const bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  const sampleColumnsWrap = document.getElementById("settings-sample-columns");
  const boxFieldsWrap = document.getElementById("settings-box-fields");
  const boxZoomInput = document.getElementById("settings-box-zoom");
  const boxZoomValue = document.getElementById("settings-box-zoom-value");
  const notice = document.getElementById("settings-client-notice");

  const sampleColumnsKey = "samples-table-visible-columns";
  const boxZoomKey = "sample-storage-box-zoom";
  const boxFieldPrefix = "sample-storage-box-show-";

  const defaultSampleColumns = bootstrap.default_sample_columns || [];
  const sampleColumns = bootstrap.sample_columns || [];
  const boxFields = bootstrap.box_fields || [];
  const defaultBoxZoom = Number.parseInt(String(bootstrap.default_box_zoom || 100), 10);

  renderSampleColumns();
  renderBoxFields();
  loadBoxZoom();

  clientRoot.querySelector("[data-settings-action='save-sample-columns']")?.addEventListener("click", saveSampleColumns);
  clientRoot.querySelector("[data-settings-action='reset-sample-columns']")?.addEventListener("click", resetSampleColumns);
  clientRoot.querySelector("[data-settings-action='save-box-settings']")?.addEventListener("click", saveBoxSettings);
  clientRoot.querySelector("[data-settings-action='reset-box-settings']")?.addEventListener("click", resetBoxSettings);
  boxZoomInput?.addEventListener("input", updateZoomLabel);

  function renderSampleColumns() {
    const selected = new Set(loadSampleColumns());
    sampleColumnsWrap.innerHTML = sampleColumns
      .map(
        (column) => `
          <label class="settings-option-card">
            <input type="checkbox" value="${escapeHtml(column.key)}" ${selected.has(column.key) ? "checked" : ""} />
            <span>${escapeHtml(column.label)}</span>
          </label>
        `
      )
      .join("");
  }

  function renderBoxFields() {
    boxFieldsWrap.innerHTML = boxFields
      .map(
        (field) => `
          <label class="settings-option-card">
            <input type="checkbox" value="${escapeHtml(field.key)}" ${loadBoxField(field.key, field.default) ? "checked" : ""} />
            <span>${escapeHtml(field.label)}</span>
          </label>
        `
      )
      .join("");
  }

  function loadSampleColumns() {
    try {
      const raw = window.localStorage.getItem(sampleColumnsKey);
      if (!raw) {
        return [...defaultSampleColumns];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.length) {
        return [...defaultSampleColumns];
      }
      return parsed.filter((key) => sampleColumns.some((column) => column.key === key));
    } catch {
      return [...defaultSampleColumns];
    }
  }

  function saveSampleColumns() {
    const checked = Array.from(sampleColumnsWrap.querySelectorAll("input:checked")).map((input) => input.value);
    if (!checked.length) {
      showNotice("Select at least one sample column.");
      return;
    }
    window.localStorage.setItem(sampleColumnsKey, JSON.stringify(sampleColumns.map((column) => column.key).filter((key) => checked.includes(key))));
    showNotice("Sample workspace defaults saved.");
  }

  function resetSampleColumns() {
    window.localStorage.removeItem(sampleColumnsKey);
    renderSampleColumns();
    showNotice("Sample workspace defaults reset.");
  }

  function loadBoxField(key, fallbackValue) {
    const raw = window.localStorage.getItem(`${boxFieldPrefix}${key}`);
    if (raw === null) {
      return !!fallbackValue;
    }
    return raw === "true";
  }

  function loadBoxZoom() {
    const stored = normalizeZoom(window.localStorage.getItem(boxZoomKey) ?? defaultBoxZoom);
    boxZoomInput.value = String(stored);
    updateZoomLabel();
  }

  function saveBoxSettings() {
    boxFieldsWrap.querySelectorAll("input[type='checkbox']").forEach((input) => {
      window.localStorage.setItem(`${boxFieldPrefix}${input.value}`, String(input.checked));
    });
    window.localStorage.setItem(boxZoomKey, String(normalizeZoom(boxZoomInput.value)));
    updateZoomLabel();
    showNotice("Storage workspace defaults saved.");
  }

  function resetBoxSettings() {
    boxFields.forEach((field) => {
      window.localStorage.removeItem(`${boxFieldPrefix}${field.key}`);
    });
    window.localStorage.removeItem(boxZoomKey);
    renderBoxFields();
    loadBoxZoom();
    showNotice("Storage workspace defaults reset.");
  }

  function updateZoomLabel() {
    boxZoomValue.textContent = `${normalizeZoom(boxZoomInput.value)}%`;
  }

  function normalizeZoom(value) {
    const numeric = Number.parseInt(String(value), 10);
    if (Number.isNaN(numeric)) {
      return defaultBoxZoom;
    }
    return Math.min(140, Math.max(70, numeric));
  }

  function showNotice(message) {
    notice.textContent = message;
    notice.classList.remove("hidden");
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }
})();
