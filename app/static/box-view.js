(() => {
  const BOX_ZOOM_KEY = "sample-storage-box-zoom";
  const BOX_FIELD_PREFIX = "sample-storage-box-show-";
  const DEFAULT_ZOOM = 100;
  const controls = document.querySelector("[data-box-controls]");
  const placeDialog = document.getElementById("box-place-dialog");
  const placeForm = document.getElementById("box-place-form");
  const sampleSearch = document.getElementById("place-sample-search");
  const sampleSelect = document.getElementById("place-sample-id");
  const positionIdField = document.getElementById("place-position-id");
  const positionLabel = document.getElementById("place-position-label");
  const zoomInput = controls?.querySelector("[data-box-zoom]");
  const zoomValue = controls?.querySelector("[data-box-zoom-value]");

  if (controls) {
    controls.querySelectorAll("[data-field-toggle]").forEach((input) => {
      const stored = loadFieldToggle(input.dataset.fieldToggle, input.checked);
      input.checked = stored;
      applyFieldToggle(input.dataset.fieldToggle, stored);
      input.addEventListener("change", () => {
        applyFieldToggle(input.dataset.fieldToggle, input.checked);
        saveFieldToggle(input.dataset.fieldToggle, input.checked);
      });
    });

    const initialZoom = loadZoom();
    applyZoom(initialZoom);
    if (zoomInput) {
      zoomInput.value = String(initialZoom);
      zoomInput.addEventListener("input", () => {
        const nextZoom = normalizeZoom(zoomInput.value);
        applyZoom(nextZoom);
        saveZoom(nextZoom);
      });
    }
  }

  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-action='open-place']");
    if (openButton && placeDialog) {
      positionIdField.value = openButton.dataset.positionId || "";
      positionLabel.textContent = `Open position ${openButton.dataset.positionLabel || ""}`;
      resetPlacementFilter();
      placeDialog.showModal();
      return;
    }

    if (event.target.closest("[data-action='close-place-dialog']")) {
      placeDialog?.close();
    }
  });

  sampleSearch?.addEventListener("input", filterSamples);

  placeForm?.addEventListener("submit", () => {
    placeDialog?.close();
  });

  function filterSamples() {
    const query = (sampleSearch.value || "").trim().toLowerCase();
    let firstVisible = null;
    Array.from(sampleSelect.options).forEach((option) => {
      const matches = !query || (option.dataset.search || "").includes(query);
      option.hidden = !matches;
      if (matches && !firstVisible) {
        firstVisible = option;
      }
    });
    if (firstVisible) {
      sampleSelect.value = firstVisible.value;
    }
  }

  function resetPlacementFilter() {
    if (!sampleSelect) return;
    if (sampleSearch) {
      sampleSearch.value = "";
    }
    Array.from(sampleSelect.options).forEach((option) => {
      option.hidden = false;
    });
    if (sampleSelect.options.length > 0) {
      sampleSelect.value = sampleSelect.options[0].value;
    }
  }

  function applyZoom(percent) {
    document.documentElement.style.setProperty("--box-zoom", String(percent / 100));
    if (zoomValue) {
      zoomValue.textContent = `${percent}%`;
    }
  }

  function applyFieldToggle(field, enabled) {
    document.documentElement.dataset[`show${capitalize(field)}`] = enabled ? "true" : "false";
  }

  function loadZoom() {
    const stored = window.localStorage.getItem(BOX_ZOOM_KEY);
    return normalizeZoom(stored ?? DEFAULT_ZOOM);
  }

  function saveZoom(percent) {
    window.localStorage.setItem(BOX_ZOOM_KEY, String(percent));
  }

  function loadFieldToggle(field, fallbackValue) {
    const stored = window.localStorage.getItem(`${BOX_FIELD_PREFIX}${field}`);
    if (stored === null) {
      return fallbackValue;
    }
    return stored === "true";
  }

  function saveFieldToggle(field, enabled) {
    window.localStorage.setItem(`${BOX_FIELD_PREFIX}${field}`, String(enabled));
  }

  function normalizeZoom(value) {
    const numeric = Number.parseInt(String(value), 10);
    if (Number.isNaN(numeric)) {
      return DEFAULT_ZOOM;
    }
    return Math.min(140, Math.max(70, numeric));
  }

  function capitalize(value) {
    return value ? value.charAt(0).toUpperCase() + value.slice(1) : "";
  }
})();
