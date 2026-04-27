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
    const previewUrl = bootstrap.preview_url || "/api/samples/selection-preview";
    const summary = document.getElementById("sample-actions-selection-summary");
    const clearButton = document.getElementById("sample-actions-clear-selection");
    const preview = document.getElementById("sample-actions-preview");
    const previewEmpty = document.getElementById("sample-actions-preview-empty");
    const previewSummary = document.getElementById("sample-actions-preview-summary");
    const previewBody = document.getElementById("sample-actions-preview-body");
    let previewRequestId = 0;

    const seededIds = Array.isArray(bootstrap.sample_ids) ? bootstrap.sample_ids : [];
    if (seededIds.length) {
      SampleActionSelection.add(seededIds, storageKey);
    }

    document.querySelectorAll("[data-sample-action-open]").forEach((button) => {
      button.addEventListener("click", () => {
        const selectedIds = SampleActionSelection.load(storageKey);
        if (!selectedIds.length || button.disabled) {
          return;
        }
        updateWorkspaceActionUrls(selectedIds);
        const dialog = document.getElementById(`sample-action-dialog-${button.dataset.actionKey || ""}`);
        if (dialog?.showModal) {
          dialog.showModal();
        }
      });
    });

    document.querySelectorAll(".sample-action-dialog").forEach((dialog) => {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) {
          dialog.close();
        }
      });
    });

    document.querySelectorAll("[data-sample-action-close]").forEach((button) => {
      button.addEventListener("click", () => {
        button.closest("dialog")?.close();
      });
    });

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
      document.querySelectorAll("[data-sample-action-open]").forEach((button) => {
        const disabled = selectedIds.length === 0;
        button.disabled = disabled;
        button.classList.toggle("is-disabled", disabled);
        button.setAttribute("aria-disabled", disabled ? "true" : "false");
      });
      updateWorkspaceActionUrls(selectedIds);
      renderSelectedPreview(selectedIds);
    }

    function updateWorkspaceActionUrls(selectedIds) {
      document.querySelectorAll("[data-sample-action-download]").forEach((link) => {
        const actionUrl = link.dataset.actionUrl || link.getAttribute("href") || DEFAULT_WORKSPACE_URL;
        link.href = SampleActionSelection.actionUrl(selectedIds, actionUrl);
      });
      document.querySelectorAll("[data-sample-action-form]").forEach((form) => {
        const actionUrl = form.dataset.actionUrl || form.getAttribute("action") || DEFAULT_WORKSPACE_URL;
        form.action = SampleActionSelection.actionUrl(selectedIds, actionUrl);
      });
      document.querySelectorAll("[data-sample-action-dialog-count]").forEach((node) => {
        node.textContent = selectedIds.length
          ? `${selectedIds.length} selected sample${selectedIds.length === 1 ? "" : "s"} will be included in the workbook.`
          : "No samples selected.";
      });
    }

    async function renderSelectedPreview(selectedIds) {
      const requestId = ++previewRequestId;
      if (!selectedIds.length) {
        if (preview) {
          preview.hidden = true;
        }
        if (previewEmpty) {
          previewEmpty.hidden = false;
        }
        if (previewBody) {
          previewBody.innerHTML = "";
        }
        return;
      }

      if (preview) {
        preview.hidden = false;
      }
      if (previewEmpty) {
        previewEmpty.hidden = true;
      }
      if (previewSummary) {
        previewSummary.textContent = "Loading selected sample details...";
      }
      if (previewBody) {
        previewBody.innerHTML = `<tr><td colspan="6" class="muted">Loading...</td></tr>`;
      }

      try {
        const response = await fetch(SampleActionSelection.actionUrl(selectedIds, previewUrl), {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`Preview failed with status ${response.status}`);
        }
        const rows = await response.json();
        if (requestId !== previewRequestId) {
          return;
        }
        if (previewSummary) {
          previewSummary.textContent = `${rows.length} selected sample${rows.length === 1 ? "" : "s"} found.`;
        }
        if (previewBody) {
          previewBody.innerHTML = rows.length
            ? rows.map(renderPreviewRow).join("")
            : `<tr><td colspan="6" class="muted">Selected samples were not found.</td></tr>`;
        }
      } catch {
        if (requestId !== previewRequestId) {
          return;
        }
        if (previewSummary) {
          previewSummary.textContent = "Could not load selected sample details.";
        }
        if (previewBody) {
          previewBody.innerHTML = `<tr><td colspan="6" class="muted">Refresh the page or return to Samples and rebuild the selection.</td></tr>`;
        }
      }
    }

    function renderPreviewRow(row) {
      return `
        <tr>
          <td><strong>${escapeHtml(row.sample_id || "--")}</strong></td>
          <td>${escapeHtml(row.sample_type_name || "--")}</td>
          <td>${escapeHtml(row.study_name || "--")}</td>
          <td>${escapeHtml(labelize(row.study_role) || "--")}</td>
          <td>${escapeHtml(formatVolume(row))}</td>
          <td>${escapeHtml(row.location_path || "Unplaced")}</td>
        </tr>
      `;
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

  function formatVolume(row) {
    if (row.volume === null || row.volume === undefined || row.volume === "") {
      return "--";
    }
    return `${Number(row.volume).toLocaleString(undefined, { maximumFractionDigits: 6 })} ${row.volume_units || "mL"}`;
  }

  function labelize(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
