(() => {
  const DEFAULT_STORAGE_KEY = "analysis-batch-selection";
  const DEFAULT_WORKSPACE_URL = "/analyses";

  const AnalysisBatchSelection = {
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
            .filter((value) => Number.isInteger(value) && value > 0)
        )
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

    workspaceUrl(sampleIds, workspaceUrl = DEFAULT_WORKSPACE_URL) {
      const params = new URLSearchParams();
      for (const sampleId of sampleIds || []) {
        params.append("sample_ids", sampleId);
      }
      const query = params.toString();
      return query ? `${workspaceUrl}?${query}` : workspaceUrl;
    },

    downloadUrl(sampleIds, downloadUrl = "/analyses/log") {
      const params = new URLSearchParams();
      for (const sampleId of sampleIds || []) {
        params.append("sample_ids", sampleId);
      }
      const query = params.toString();
      return query ? `${downloadUrl}?${query}` : downloadUrl;
    },

    eligible(sample) {
      if (!sample) {
        return false;
      }
      return !sample.is_archived && !sample.is_out_for_analysis && !!sample.location_position_id;
    },
  };

  window.AnalysisBatchSelection = AnalysisBatchSelection;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
    return;
  }
  init();

  function init() {
    initSampleDetailButtons();
    initAnalysisWorkspace();
  }

  function initSampleDetailButtons() {
    const bootstrapNode = document.getElementById("analysis-page-bootstrap");
    if (!bootstrapNode) {
      return;
    }
    const bootstrap = parseJsonNode(bootstrapNode, {});
    const storageKey = bootstrap.storage_key || DEFAULT_STORAGE_KEY;
    const workspaceUrl = bootstrap.workspace_url || DEFAULT_WORKSPACE_URL;

    document.querySelectorAll("[data-analysis-add]").forEach((button) => {
      button.addEventListener("click", () => {
        const sampleId = Number.parseInt(button.dataset.sampleId || "", 10);
        if (!Number.isInteger(sampleId)) {
          return;
        }
        if (button.dataset.eligible !== "true") {
          window.alert("Only placed, active samples can be added to analysis.");
          return;
        }
        AnalysisBatchSelection.add([sampleId], storageKey);
        updateDetailButtons(storageKey, workspaceUrl);
      });
    });

    updateDetailButtons(storageKey, workspaceUrl);
  }

  function updateDetailButtons(storageKey, workspaceUrl) {
    const selected = new Set(AnalysisBatchSelection.load(storageKey));
    document.querySelectorAll("[data-analysis-add]").forEach((button) => {
      const sampleId = Number.parseInt(button.dataset.sampleId || "", 10);
      const inBatch = selected.has(sampleId);
      button.textContent = button.closest(".sample-actions-row")
        ? inBatch ? "Added to analysis selection" : "Add this sample to analysis"
        : inBatch ? "Added to analysis" : "Add to analysis";
    });
  }

  function initAnalysisWorkspace() {
    const root = document.querySelector("[data-analysis-workspace]");
    const bootstrapNode = document.getElementById("analysis-workspace-bootstrap");
    if (!root || !bootstrapNode) {
      return;
    }

    const bootstrap = parseJsonNode(bootstrapNode, {});
    const storageKey = bootstrap.storage_key || DEFAULT_STORAGE_KEY;
    const workspaceUrl = bootstrap.workspace_url || DEFAULT_WORKSPACE_URL;
    const downloadUrl = bootstrap.download_url || "/analyses/log";
    const summary = document.getElementById("analysis-selection-summary");
    const clearButton = document.getElementById("analysis-clear-selection");
    const downloadLink = document.getElementById("analysis-download-log");

    const seededIds = Array.isArray(bootstrap.sample_ids) ? bootstrap.sample_ids : [];
    if (seededIds.length) {
      AnalysisBatchSelection.add(seededIds, storageKey);
    }

    clearButton?.addEventListener("click", () => {
      AnalysisBatchSelection.clear(storageKey);
      renderWorkspace();
    });

    renderWorkspace();

    function renderWorkspace() {
      const selectedIds = AnalysisBatchSelection.load(storageKey);
      summary.textContent = selectedIds.length
        ? `${selectedIds.length} sample${selectedIds.length === 1 ? "" : "s"} selected for analysis`
        : "No samples are currently staged for analysis.";
      if (downloadLink) {
        downloadLink.href = AnalysisBatchSelection.downloadUrl(selectedIds, downloadUrl);
        downloadLink.classList.toggle("is-disabled", selectedIds.length === 0);
        downloadLink.setAttribute("aria-disabled", selectedIds.length === 0 ? "true" : "false");
      }
      root.querySelectorAll('[data-analysis-workspace-link]').forEach((link) => {
        link.href = AnalysisBatchSelection.workspaceUrl(selectedIds, workspaceUrl);
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
