(() => {
  const DEFAULT_STORAGE_KEY = "sample-action-selection";
  const DEFAULT_WORKSPACE_URL = "/sample-actions";

  const SampleActionSelection = {
    load(storageKey = DEFAULT_STORAGE_KEY) {
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (!raw) {
          return [];
        }
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) {
          return [];
        }
        return parsed
          .map((value) => Number.parseInt(value, 10))
          .filter((value) => Number.isInteger(value) && value > 0);
      } catch {
        return [];
      }
    },

    save(sampleIds, storageKey = DEFAULT_STORAGE_KEY) {
      const normalized = Array.from(
        new Set(
          (sampleIds || [])
            .map((value) => Number.parseInt(value, 10))
            .filter((value) => Number.isInteger(value) && value > 0),
        ),
      );
      window.localStorage.setItem(storageKey, JSON.stringify(normalized));
      return normalized;
    },

    add(sampleIds, storageKey = DEFAULT_STORAGE_KEY) {
      return this.save([...this.load(storageKey), ...(sampleIds || [])], storageKey);
    },

    remove(sampleIds, storageKey = DEFAULT_STORAGE_KEY) {
      const removeSet = new Set((sampleIds || []).map((value) => Number.parseInt(value, 10)));
      return this.save(this.load(storageKey).filter((value) => !removeSet.has(value)), storageKey);
    },

    clear(storageKey = DEFAULT_STORAGE_KEY) {
      window.localStorage.removeItem(storageKey);
      return [];
    },

    actionUrl(sampleIds, baseUrl = DEFAULT_WORKSPACE_URL) {
      const params = new URLSearchParams();
      for (const sampleId of sampleIds || []) {
        params.append("sample_ids", sampleId);
      }
      const query = params.toString();
      return query ? `${baseUrl}?${query}` : baseUrl;
    },
  };

  window.SampleActionSelection = SampleActionSelection;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
    return;
  }
  init();

  function init() {
    initSampleDetailButtons();
    initWorkspace();
    initActionPage();
  }

  function initSampleDetailButtons() {
    const bootstrapNode = document.getElementById("sample-actions-page-bootstrap");
    if (!bootstrapNode) {
      return;
    }
    const bootstrap = parseJsonNode(bootstrapNode, {});
    const storageKey = bootstrap.storage_key || DEFAULT_STORAGE_KEY;

    document.querySelectorAll("[data-sample-action-add]").forEach((button) => {
      button.addEventListener("click", () => {
        const sampleId = Number.parseInt(button.dataset.sampleId || "", 10);
        if (!Number.isInteger(sampleId)) {
          return;
        }
        SampleActionSelection.add([sampleId], storageKey);
        updateDetailButtons(storageKey);
      });
    });

    updateDetailButtons(storageKey);
  }

  function updateDetailButtons(storageKey) {
    const selected = new Set(SampleActionSelection.load(storageKey));
    document.querySelectorAll("[data-sample-action-add]").forEach((button) => {
      const sampleId = Number.parseInt(button.dataset.sampleId || "", 10);
      const inSelection = selected.has(sampleId);
      button.textContent = button.closest(".sample-actions-row")
        ? inSelection ? "Added to selection" : "Add this sample to selection"
        : inSelection ? "Added to selection" : "Add to selection";
    });
  }

  function initWorkspace() {
    const root = document.querySelector("[data-sample-actions-workspace]");
    const bootstrapNode = document.getElementById("sample-actions-workspace-bootstrap");
    if (!root || !bootstrapNode) {
      return;
    }
    const bootstrap = parseJsonNode(bootstrapNode, {});
    const storageKey = bootstrap.storage_key || DEFAULT_STORAGE_KEY;
    const summary = document.getElementById("sample-actions-selection-summary");
    const clearButton = document.getElementById("sample-actions-clear-selection");

    const seededIds = Array.isArray(bootstrap.sample_ids) ? bootstrap.sample_ids : [];
    if (seededIds.length) {
      SampleActionSelection.add(seededIds, storageKey);
    }

    clearButton?.addEventListener("click", () => {
      SampleActionSelection.clear(storageKey);
      renderWorkspace();
    });

    renderWorkspace();

    function renderWorkspace() {
      const selectedIds = SampleActionSelection.load(storageKey);
      if (summary) {
        summary.textContent = selectedIds.length
          ? `${selectedIds.length} sample${selectedIds.length === 1 ? "" : "s"} selected for batch actions`
          : "No samples are currently staged.";
      }
      root.querySelectorAll("[data-sample-action-link]").forEach((link) => {
        const actionUrl = link.dataset.actionUrl || DEFAULT_WORKSPACE_URL;
        link.href = SampleActionSelection.actionUrl(selectedIds, actionUrl);
        const disabled = selectedIds.length === 0;
        link.classList.toggle("is-disabled", disabled);
        link.setAttribute("aria-disabled", disabled ? "true" : "false");
      });
    }
  }

  function initActionPage() {
    const root = document.querySelector("[data-sample-action-page]");
    const bootstrapNode = document.getElementById("sample-action-page-bootstrap");
    if (!root || !bootstrapNode) {
      return;
    }
    const bootstrap = parseJsonNode(bootstrapNode, {});
    const storageKey = bootstrap.storage_key || DEFAULT_STORAGE_KEY;
    const summary = document.getElementById("sample-action-selection-summary");
    const clearButton = document.getElementById("sample-action-clear-selection");
    const downloadLink = document.getElementById("sample-action-download-log");

    const seededIds = Array.isArray(bootstrap.sample_ids) ? bootstrap.sample_ids : [];
    if (seededIds.length) {
      SampleActionSelection.add(seededIds, storageKey);
    }

    clearButton?.addEventListener("click", () => {
      SampleActionSelection.clear(storageKey);
      renderPage();
    });

    renderPage();

    function renderPage() {
      const selectedIds = SampleActionSelection.load(storageKey);
      if (summary) {
        summary.textContent = selectedIds.length
          ? `${selectedIds.length} sample${selectedIds.length === 1 ? "" : "s"} staged for this action`
          : "No samples are currently staged for this action.";
      }
      if (downloadLink) {
        const downloadUrl = downloadLink.dataset.actionUrl || downloadLink.getAttribute("href") || "#";
        downloadLink.href = SampleActionSelection.actionUrl(selectedIds, downloadUrl);
        const disabled = selectedIds.length === 0;
        downloadLink.classList.toggle("is-disabled", disabled);
        downloadLink.setAttribute("aria-disabled", disabled ? "true" : "false");
      }
      root.querySelectorAll("[data-sample-action-link]").forEach((link) => {
        const actionUrl = link.dataset.actionUrl || DEFAULT_WORKSPACE_URL;
        link.href = SampleActionSelection.actionUrl(selectedIds, actionUrl);
      });
    }
  }

  function parseJsonNode(node, fallback) {
    try {
      return JSON.parse(node.textContent || "{}");
    } catch {
      return fallback;
    }
  }
})();
