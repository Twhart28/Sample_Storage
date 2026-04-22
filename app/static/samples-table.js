(() => {
  const root = document.querySelector("[data-samples-table]");
  const bootstrapNode = document.getElementById("samples-table-bootstrap");
  if (!root || !bootstrapNode) {
    return;
  }

  const bootstrap = JSON.parse(bootstrapNode.textContent || "{}");
  const table = document.getElementById("samples-live-table");
  const colgroup = table.querySelector("colgroup");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  const searchInput = document.getElementById("samples-live-search");
  const resultCount = document.getElementById("samples-result-count");
  const chips = document.getElementById("samples-filter-chips");
  const errorBox = document.getElementById("samples-table-error");
  const filterOverlay = document.getElementById("samples-filter-overlay");
  const filterWindow = document.getElementById("samples-filter-window");
  const columnPopover = document.getElementById("samples-column-picker");
  const columnButton = document.getElementById("samples-column-picker-button");
  const selectionToggleButton = document.getElementById("samples-analysis-toggle");
  const selectionActions = document.getElementById("samples-analysis-actions");
  const selectionAddButton = document.getElementById("samples-analysis-add");
  const selectionRemoveButton = document.getElementById("samples-analysis-remove");
  const selectionWorkspaceLink = document.getElementById("samples-analysis-start");
  const selectionClearButton = document.getElementById("samples-analysis-clear");
  const bulkOpenButton = document.getElementById("samples-bulk-open");
  const bulkDialog = document.getElementById("samples-bulk-dialog");
  const bulkCloseButton = document.getElementById("samples-bulk-close");
  const bulkFileInput = document.getElementById("samples-bulk-file");
  const bulkErrorBox = document.getElementById("samples-bulk-error");
  const bulkStatusBox = document.getElementById("samples-bulk-status");
  const bulkPreviewBox = document.getElementById("samples-bulk-preview");
  const bulkResetButton = document.getElementById("samples-bulk-reset");
  const bulkCommitButton = document.getElementById("samples-bulk-commit");

  const visibleColumnsStorageKey = "samples-table-visible-columns";
  const sampleActionSelection = window.SampleActionSelection || null;
  const canUseSampleActions = !!bootstrap.can_use_sample_actions && !!sampleActionSelection;
  const sampleActionsWorkspaceUrl = bootstrap.sample_actions_workspace_url || "/sample-actions";
  const sampleActionsStorageKey = bootstrap.sample_actions_storage_key || "sample-action-selection";
  const canBulkImportSamples = !!bulkOpenButton && !!bulkDialog;
  const optionColumns = new Set(["study", "sample_type", "study_role", "custody", "usage", "visit_label", "timepoint_label"]);
  const numberRangeColumns = new Set(["volume", "aliquot_number", "hemolysis_classification", "thaw_count"]);
  const dateRangeColumns = new Set(["collection_at", "created_at", "updated_at"]);
  const dateFieldMap = {
    collection_at: ["collection_from", "collection_to"],
    created_at: ["registered_from", "registered_to"],
    updated_at: ["updated_from", "updated_to"],
  };
  const numberFieldMap = {
    volume: ["volume_min", "volume_max"],
    aliquot_number: ["aliquot_min", "aliquot_max"],
    hemolysis_classification: ["hemolysis_min", "hemolysis_max"],
    thaw_count: ["thaw_count_min", "thaw_count_max"],
  };
  const multiValueFieldMap = {
    sample_type: "sample_type_ids",
    study: "study_ids",
    study_role: "study_roles",
    custody: "custodies",
    usage: "usages",
    visit_label: "visit_labels",
    timepoint_label: "timepoint_labels",
  };
  const columnMap = new Map((bootstrap.columns || []).map((column) => [column.key, column]));
  const columnWidthMap = {
    sample_id: "108px",
    study: "80px",
    sample_type: "92px",
    study_role: "96px",
    custody: "120px",
    usage: "82px",
    volume: "84px",
    location: "300px",
    visit_label: "68px",
    timepoint_label: "84px",
    aliquot_number: "74px",
    hemolysis_classification: "84px",
    thaw_count: "98px",
    collection_at: "132px",
    created_at: "132px",
    updated_at: "132px",
  };
  const compactColumns = new Set([
    "sample_id",
    "study",
    "sample_type",
    "study_role",
    "custody",
    "usage",
    "volume",
    "visit_label",
    "timepoint_label",
    "aliquot_number",
    "hemolysis_classification",
    "thaw_count",
    "collection_at",
    "created_at",
    "updated_at",
  ]);
  const numericColumns = new Set([
    "volume",
    "visit_label",
    "timepoint_label",
    "aliquot_number",
    "hemolysis_classification",
    "thaw_count",
    "collection_at",
    "created_at",
    "updated_at",
  ]);
  const storageTree = bootstrap.storage_tree || [];
  const locationNodeMap = new Map();
  const locationChildrenMap = new Map();
  const locationPathMap = new Map();
  const defaultVisibleColumns = bootstrap.default_visible_columns || [];
  const state = buildInitialState(bootstrap.initial_state || {});
  let rows = bootstrap.initial_rows || [];
  let debounceTimer = null;
  let fetchVersion = 0;
  let selectionMode = false;
  let bulkPreviewPayload = null;
  let lastSelectedRowId = null;
  const checkedRowIds = new Set();

  indexLocationTree(storageTree);
  if (canUseSampleActions) {
    selectionToggleButton.hidden = false;
    selectionToggleButton.classList.remove("hidden");
    selectionToggleButton?.addEventListener("click", () => {
      selectionMode = !selectionMode;
      if (!selectionMode) {
        checkedRowIds.clear();
        lastSelectedRowId = null;
      }
      renderTable();
    });
    selectionAddButton?.addEventListener("click", () => {
      const sampleIds = selectedRowIds();
      if (!sampleIds.length) {
        return;
      }
      sampleActionSelection.add(sampleIds, sampleActionsStorageKey);
      sampleIds.forEach((sampleId) => checkedRowIds.delete(sampleId));
      lastSelectedRowId = null;
      renderTable();
    });
    selectionRemoveButton?.addEventListener("click", () => {
      const sampleIds = selectedRowIds();
      if (!sampleIds.length) {
        return;
      }
      sampleActionSelection.remove(sampleIds, sampleActionsStorageKey);
      sampleIds.forEach((sampleId) => checkedRowIds.delete(sampleId));
      lastSelectedRowId = null;
      renderTable();
    });
    selectionClearButton?.addEventListener("click", () => {
      sampleActionSelection.clear(sampleActionsStorageKey);
      checkedRowIds.clear();
      lastSelectedRowId = null;
      renderTable();
    });
    selectionWorkspaceLink?.addEventListener("click", (event) => {
      if (sampleActionSelection.load(sampleActionsStorageKey).length === 0) {
        event.preventDefault();
      }
    });
  }

  if (canBulkImportSamples) {
    bulkOpenButton?.addEventListener("click", openBulkDialog);
    bulkCloseButton?.addEventListener("click", closeBulkDialog);
    bulkResetButton?.addEventListener("click", resetBulkDialog);
    bulkFileInput?.addEventListener("change", handleBulkFileSelected);
    bulkCommitButton?.addEventListener("click", commitBulkImport);
    bulkDialog?.addEventListener("click", (event) => {
      const rect = bulkDialog.getBoundingClientRect();
      const clickedBackdrop =
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom;
      if (clickedBackdrop) {
        closeBulkDialog();
      }
    });
    bulkDialog?.addEventListener("close", resetBulkDialog);
  }

  searchInput.value = state.q || "";
  renderTable();
  renderActiveState();

  searchInput.addEventListener("input", () => {
    state.q = searchInput.value || "";
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(fetchRows, 280);
  });

  columnButton.addEventListener("click", (event) => {
    event.stopPropagation();
    if (!columnPopover.classList.contains("hidden")) {
      closeOverlays();
      return;
    }
    renderColumnPicker();
    openColumnPicker(columnButton);
  });

  document.addEventListener("click", (event) => {
    const headerButton = event.target.closest("[data-column-trigger]");
    if (headerButton) {
      event.preventDefault();
      event.stopPropagation();
      openFilterWindow(headerButton.dataset.columnTrigger);
      return;
    }

    if (columnPopover.contains(event.target) || event.target === columnButton) {
      return;
    }

    closeColumnPicker();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeOverlays();
    }
  });

  filterOverlay?.addEventListener("click", (event) => {
    if (event.target === filterOverlay) {
      closeFilterWindow();
    }
  });

  async function fetchRows() {
    const version = ++fetchVersion;
    setError("");
    resultCount.textContent = "Updating...";
    try {
      const params = buildQueryParams();
      const response = await fetch(`${bootstrap.search_endpoint}?${params.toString()}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error("Unable to load samples");
      }
      const payload = await response.json();
      if (version !== fetchVersion) {
        return;
      }
      rows = payload;
      renderTable();
      renderActiveState();
    } catch (error) {
      if (version !== fetchVersion) {
        return;
      }
      setError(error.message || "Unable to load samples");
      renderActiveState();
    }
  }

  async function openFilterWindow(columnKey) {
    closeColumnPicker();
    filterWindow.innerHTML = `
      <div class="samples-filter-window-card">
        <p class="muted">Loading...</p>
      </div>
    `;
    filterOverlay.hidden = false;
    filterOverlay.classList.remove("hidden");

    if (columnKey === "location") {
      renderLocationWindow();
      return;
    }

    if (optionColumns.has(columnKey)) {
      try {
        const response = await fetch(bootstrap.filter_options_endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            column: columnKey,
            filters: buildFilterPayload(),
          }),
        });
        if (!response.ok) {
          throw new Error("Unable to load filter options");
        }
        const payload = await response.json();
        renderOptionWindow(columnKey, payload.options || []);
      } catch (error) {
        filterWindow.innerHTML = `
          <div class="samples-filter-window-card">
            <p class="form-error">${escapeHtml(error.message || "Unable to load filter options")}</p>
          </div>
        `;
      }
      return;
    }

    renderStaticWindow(columnKey);
  }

  function renderOptionWindow(columnKey, options) {
    const column = columnMap.get(columnKey);
    const searchId = `option-search-${columnKey}`;
    filterWindow.innerHTML = `
      <div class="samples-filter-window-card">
        <div class="samples-filter-window-head">
          <strong id="samples-filter-title">${escapeHtml(column.label)}</strong>
          <button type="button" class="ghost-button samples-filter-close">Close</button>
        </div>
        <div class="samples-filter-window-body">
          <div class="samples-sort-actions">
            ${renderSortButtons(columnKey)}
          </div>
          ${columnKey === "location" ? "" : `
            <div class="samples-option-tools">
              <button type="button" class="ghost-button samples-tool-button" data-action="select-all-options">All</button>
              <button type="button" class="ghost-button samples-tool-button" data-action="clear-option-selection">None</button>
            </div>
          `}
          ${columnKey === "location" ? "" : `<label class="samples-popover-search">Find options<input type="search" id="${searchId}" placeholder="Filter options" /></label>`}
          <div class="samples-option-list" id="option-list-${columnKey}">
            ${renderOptionInputs(columnKey, options)}
          </div>
        </div>
        <div class="actions-row samples-filter-window-footer">
          <button type="button" data-action="apply-filter">Apply</button>
          <button type="button" class="ghost-button" data-action="clear-filter">Clear</button>
        </div>
      </div>
    `;

    bindFilterWindowActions(columnKey);

    if (columnKey !== "location") {
      const searchNode = document.getElementById(searchId);
      const optionList = document.getElementById(`option-list-${columnKey}`);
      filterWindow.querySelector("[data-action='select-all-options']")?.addEventListener("click", () => {
        optionList.querySelectorAll("input[type='checkbox']").forEach((input) => {
          if (!input.closest(".samples-option-item")?.hidden) {
            input.checked = true;
          }
        });
      });
      filterWindow.querySelector("[data-action='clear-option-selection']")?.addEventListener("click", () => {
        optionList.querySelectorAll("input[type='checkbox']").forEach((input) => {
          input.checked = false;
        });
      });
      searchNode?.addEventListener("input", () => {
        const needle = (searchNode.value || "").trim().toLowerCase();
        optionList.querySelectorAll(".samples-option-item").forEach((item) => {
          const haystack = (item.dataset.filterLabel || "").toLowerCase();
          item.hidden = !!needle && !haystack.includes(needle);
        });
      });
    }
  }

  function renderLocationWindow() {
    filterWindow.innerHTML = `
      <div class="samples-filter-window-card">
        <div class="samples-filter-window-head">
          <strong id="samples-filter-title">Location</strong>
          <button type="button" class="ghost-button samples-filter-close">Close</button>
        </div>
        <div class="samples-filter-window-body">
          <div class="samples-sort-actions">
            ${renderSortButtons("location")}
          </div>
          <div class="samples-location-mode">
            <label class="samples-option-item samples-option-card">
              <input type="radio" name="location-filter" value="" ${state.location_state === "" ? "checked" : ""} />
              <span class="samples-option-label">Any location</span>
            </label>
            <label class="samples-option-item samples-option-card">
              <input type="radio" name="location-filter" value="placed" ${state.location_state === "placed" ? "checked" : ""} />
              <span class="samples-option-label">Placed only</span>
            </label>
            <label class="samples-option-item samples-option-card">
              <input type="radio" name="location-filter" value="unplaced" ${state.location_state === "unplaced" ? "checked" : ""} />
              <span class="samples-option-label">Unplaced only</span>
            </label>
          </div>
          <div class="samples-option-tools">
            <button type="button" class="ghost-button samples-tool-button" data-action="expand-location-tree">Expand all</button>
            <button type="button" class="ghost-button samples-tool-button" data-action="collapse-location-tree">Collapse all</button>
            <button type="button" class="ghost-button samples-tool-button" data-action="clear-location-selection">Clear folders</button>
          </div>
          <div class="samples-location-summary" id="samples-location-summary"></div>
          <div class="samples-location-tree-wrap" id="samples-location-tree-wrap">
            ${renderLocationTree(storageTree)}
          </div>
        </div>
        <div class="actions-row samples-filter-window-footer">
          <button type="button" data-action="apply-filter">Apply</button>
          <button type="button" class="ghost-button" data-action="clear-filter">Clear</button>
        </div>
      </div>
    `;

    bindFilterWindowActions("location");
    bindLocationTreeActions();
    updateLocationSummary();
    updateLocationTreeDisabledState();
  }

  function renderStaticWindow(columnKey) {
    const column = columnMap.get(columnKey);
    const rangeMarkup = numberRangeColumns.has(columnKey)
      ? renderNumberRangeFields(columnKey)
      : dateRangeColumns.has(columnKey)
        ? renderDateRangeFields(columnKey)
        : "";
    const clearLabel = columnKey === "sample_id" ? "Reset Sort" : "Clear";
    filterWindow.innerHTML = `
      <div class="samples-filter-window-card">
        <div class="samples-filter-window-head">
          <strong id="samples-filter-title">${escapeHtml(column.label)}</strong>
          <button type="button" class="ghost-button samples-filter-close">Close</button>
        </div>
        <div class="samples-filter-window-body">
          <div class="samples-sort-actions">
            ${renderSortButtons(columnKey)}
          </div>
          ${rangeMarkup}
        </div>
        <div class="actions-row samples-filter-window-footer">
          <button type="button" data-action="apply-filter">${columnKey === "sample_id" ? "Done" : "Apply"}</button>
          <button type="button" class="ghost-button" data-action="clear-filter">${clearLabel}</button>
        </div>
      </div>
    `;

    bindFilterWindowActions(columnKey);
  }

  function bindFilterWindowActions(columnKey) {
    filterWindow.querySelector(".samples-filter-close")?.addEventListener("click", closeFilterWindow);
    filterWindow.querySelectorAll("[data-action='sort']").forEach((button) => {
      button.addEventListener("click", () => {
        state.sort = button.dataset.sortColumn;
        state.sort_dir = button.dataset.sortDir;
        fetchRows();
      });
    });
    filterWindow.querySelector("[data-action='clear-sort']")?.addEventListener("click", () => {
      state.sort = "sample_id";
      state.sort_dir = "asc";
      fetchRows();
    });
    filterWindow.querySelector("[data-action='apply-filter']")?.addEventListener("click", () => {
      applyColumnFilter(columnKey);
      closeFilterWindow();
      fetchRows();
    });
    filterWindow.querySelector("[data-action='clear-filter']")?.addEventListener("click", () => {
      clearColumnFilter(columnKey);
      closeFilterWindow();
      fetchRows();
    });
  }

  function bindLocationTreeActions() {
    filterWindow.querySelectorAll("[data-location-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const branch = filterWindow.querySelector(`[data-location-branch='${button.dataset.locationToggle}']`);
        if (!branch) {
          return;
        }
        const collapsed = branch.classList.toggle("is-collapsed");
        button.textContent = collapsed ? "+" : "-";
      });
    });

    filterWindow.querySelectorAll("input[name='storage-node-filter']").forEach((input) => {
      input.addEventListener("change", () => {
        if (input.checked) {
          collapseDescendantSelections(Number.parseInt(input.value, 10));
        }
        updateLocationSummary();
      });
    });

    filterWindow.querySelectorAll("input[name='location-filter']").forEach((input) => {
      input.addEventListener("change", () => {
        if (input.value === "unplaced" && input.checked) {
          filterWindow.querySelectorAll("input[name='storage-node-filter']").forEach((checkbox) => {
            checkbox.checked = false;
          });
        }
        updateLocationTreeDisabledState();
        updateLocationSummary();
      });
    });

    filterWindow.querySelector("[data-action='expand-location-tree']")?.addEventListener("click", () => {
      filterWindow.querySelectorAll("[data-location-branch]").forEach((branch) => branch.classList.remove("is-collapsed"));
      filterWindow.querySelectorAll("[data-location-toggle]").forEach((button) => {
        button.textContent = "-";
      });
    });

    filterWindow.querySelector("[data-action='collapse-location-tree']")?.addEventListener("click", () => {
      filterWindow.querySelectorAll("[data-location-branch]").forEach((branch) => {
        if (branch.dataset.locationDepth !== "0") {
          branch.classList.add("is-collapsed");
        }
      });
      filterWindow.querySelectorAll("[data-location-toggle]").forEach((button) => {
        const branch = filterWindow.querySelector(`[data-location-branch='${button.dataset.locationToggle}']`);
        button.textContent = branch?.classList.contains("is-collapsed") ? "+" : "-";
      });
    });

    filterWindow.querySelector("[data-action='clear-location-selection']")?.addEventListener("click", () => {
      filterWindow.querySelectorAll("input[name='storage-node-filter']").forEach((checkbox) => {
        checkbox.checked = false;
      });
      updateLocationSummary();
    });
  }

  function renderColumnPicker() {
    const visibleSet = new Set(state.visible_columns);
    columnPopover.innerHTML = `
      <div class="samples-popover-card">
        <div class="samples-popover-head">
          <strong>Visible Columns</strong>
          <button type="button" class="ghost-button samples-popover-close">Close</button>
        </div>
        <div class="samples-option-list">
          ${(bootstrap.columns || [])
            .map(
              (column) => `
                <label class="samples-option-item">
                  <input type="checkbox" value="${column.key}" ${visibleSet.has(column.key) ? "checked" : ""} />
                  <span>${escapeHtml(column.label)}</span>
                </label>
              `
            )
            .join("")}
        </div>
      </div>
    `;
    columnPopover.querySelector(".samples-popover-close")?.addEventListener("click", closeColumnPicker);
    columnPopover.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const checked = Array.from(columnPopover.querySelectorAll("input[type='checkbox']:checked")).map((input) => input.value);
        if (checked.length === 0) {
          checkbox.checked = true;
          return;
        }
        state.visible_columns = (bootstrap.columns || []).map((column) => column.key).filter((key) => checked.includes(key));
        window.localStorage.setItem(visibleColumnsStorageKey, JSON.stringify(state.visible_columns));
        renderTable();
      });
    });
  }

  function applyColumnFilter(columnKey) {
    if (columnKey === "location") {
      const selected = filterWindow.querySelector("input[name='location-filter']:checked");
      state.location_state = selected ? selected.value : "";
      state.storage_node_ids = Array.from(filterWindow.querySelectorAll("input[name='storage-node-filter']:checked"))
        .map((input) => Number.parseInt(input.value, 10))
        .filter((value) => !Number.isNaN(value));
      state.storage_node_ids = normalizeSelectedLocationIds(state.storage_node_ids);
      if (state.location_state === "unplaced") {
        state.storage_node_ids = [];
      }
      return;
    }

    if (optionColumns.has(columnKey)) {
      const selected = Array.from(filterWindow.querySelectorAll("input[type='checkbox']:checked")).map((input) => input.value);
      state[multiValueFieldMap[columnKey]] = selected;
      return;
    }

    if (numberRangeColumns.has(columnKey)) {
      const [minField, maxField] = numberFieldMap[columnKey];
      state[minField] = filterWindow.querySelector(`[name='${minField}']`)?.value.trim() || "";
      state[maxField] = filterWindow.querySelector(`[name='${maxField}']`)?.value.trim() || "";
    }

    if (dateRangeColumns.has(columnKey)) {
      const [fromField, toField] = dateFieldMap[columnKey];
      state[fromField] = filterWindow.querySelector(`[name='${fromField}']`)?.value.trim() || "";
      state[toField] = filterWindow.querySelector(`[name='${toField}']`)?.value.trim() || "";
    }
  }

  function clearColumnFilter(columnKey) {
    if (columnKey === "sample_id") {
      state.sort = "sample_id";
      state.sort_dir = "asc";
      return;
    }
    if (columnKey === "location") {
      state.location_state = "";
      state.storage_node_ids = [];
      return;
    }
    if (optionColumns.has(columnKey)) {
      state[multiValueFieldMap[columnKey]] = [];
      return;
    }
    if (numberRangeColumns.has(columnKey)) {
      const [minField, maxField] = numberFieldMap[columnKey];
      state[minField] = "";
      state[maxField] = "";
      return;
    }
    if (dateRangeColumns.has(columnKey)) {
      const [fromField, toField] = dateFieldMap[columnKey];
      state[fromField] = "";
      state[toField] = "";
    }
  }

  function renderTable() {
    const visibleRowIds = new Set(rows.map((row) => row.id));
    Array.from(checkedRowIds).forEach((sampleId) => {
      if (!visibleRowIds.has(sampleId)) {
        checkedRowIds.delete(sampleId);
      }
    });
    if (lastSelectedRowId !== null && !visibleRowIds.has(lastSelectedRowId)) {
      lastSelectedRowId = null;
    }
    const visibleColumns = (state.visible_columns || []).filter((key) => columnMap.has(key));
    renderColumnGroup(visibleColumns);
    thead.innerHTML = `
      <tr>
        ${canUseSampleActions && selectionMode ? '<th class="sample-col sample-col--analysis sample-col--header">Select</th>' : ""}
        ${visibleColumns
          .map((key) => {
            const column = columnMap.get(key);
            const filterCount = getFilterCount(key);
            const isSorted = state.sort === key;
            const sortIndicator = isSorted ? (state.sort_dir === "asc" ? "&uarr;" : "&darr;") : "";
            return `
              <th class="${getColumnClassName(key, "header")}">
                <button type="button" class="samples-header-button" data-column-trigger="${key}">
                  <span class="samples-header-label">${escapeHtml(column.label)}</span>
                  <span class="samples-header-icons">
                    ${filterCount ? `<span class="samples-filter-indicator" title="${filterCount} active filter${filterCount === 1 ? "" : "s"}">${filterCount}</span>` : ""}
                    ${isSorted ? `<span class="samples-sort-indicator" title="Sorted ${state.sort_dir}">${sortIndicator}</span>` : ""}
                  </span>
                </button>
              </th>
            `;
          })
          .join("")}
      </tr>
    `;

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="${Math.max(visibleColumns.length + (canUseSampleActions && selectionMode ? 1 : 0), 1)}" class="samples-empty-state">No matching samples.</td></tr>`;
      syncSelectionActions();
      return;
    }

    tbody.innerHTML = rows
      .map((row) => {
        const inSelection = canUseSampleActions && sampleActionSelection.load(sampleActionsStorageKey).includes(row.id);
        const rowClasses = [];
        if (canUseSampleActions && selectionMode && inSelection) {
          rowClasses.push("sample-row--analysis");
        }
        if (canUseSampleActions && selectionMode && checkedRowIds.has(row.id)) {
          rowClasses.push("sample-row--selected");
        }
        return `
          <tr data-sample-row-id="${row.id}" class="${rowClasses.join(" ")}">
            ${canUseSampleActions && selectionMode ? `<td class="sample-col sample-col--analysis sample-col--cell">${renderSelectionCell(row, inSelection)}</td>` : ""}
            ${visibleColumns.map((key) => `<td class="${getColumnClassName(key, "cell")}">${renderCell(row, key)}</td>`).join("")}
          </tr>
        `;
      })
      .join("");
    bindSelectionRowControls();
    syncSelectionActions();
  }

  function renderColumnGroup(visibleColumns) {
    if (!colgroup) {
      return;
    }
    const minimumWidth = visibleColumns.reduce((total, key) => {
      const width = Number.parseInt(columnWidthMap[key] || "0", 10);
      return total + (Number.isNaN(width) ? 0 : width);
    }, canUseSampleActions && selectionMode ? 96 : 0);
    table.style.minWidth = minimumWidth ? `${minimumWidth}px` : "";
    colgroup.innerHTML = [
      canUseSampleActions && selectionMode ? '<col class="sample-col sample-col--analysis sample-col--track" style="width:96px">' : "",
      ...visibleColumns.map((key) => {
        const width = columnWidthMap[key];
        return `<col class="${getColumnClassName(key, "col")}"${width ? ` style="width:${width}"` : ""}>`;
      }),
    ].join("");
  }

  function renderSelectionCell(row, inSelection) {
    const checked = checkedRowIds.has(row.id);
    const summary = inSelection ? '<span class="sample-analysis-flag">In selection</span>' : '<span class="sample-analysis-flag muted">Not added</span>';
    return `
      <label class="sample-analysis-cell">
        <input type="checkbox" data-analysis-row value="${row.id}" ${checked ? "checked" : ""} />
        <span>${summary}</span>
      </label>
    `;
  }

  function bindSelectionRowControls() {
    if (!canUseSampleActions || !selectionMode) {
      return;
    }
    tbody.querySelectorAll("tr[data-sample-row-id]").forEach((rowElement) => {
      rowElement.addEventListener("click", (event) => {
        if (event.target.closest("a, button, input")) {
          return;
        }
        const sampleId = Number.parseInt(rowElement.dataset.sampleRowId || "", 10);
        if (!Number.isInteger(sampleId)) {
          return;
        }
        handleSelectionInteraction(sampleId, event);
      });
    });
    tbody.querySelectorAll("[data-analysis-row]").forEach((input) => {
      input.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const sampleId = Number.parseInt(input.value, 10);
        if (!Number.isInteger(sampleId)) {
          return;
        }
        handleSelectionInteraction(sampleId, event);
      });
    });
  }

  function syncSelectionActions() {
    if (!canUseSampleActions) {
      return;
    }
    selectionActions.hidden = !selectionMode;
    selectionActions.classList.toggle("hidden", !selectionMode);
    const selectedIds = selectedRowIds();
    selectionAddButton.disabled = !selectionMode || selectedIds.length === 0;
    selectionRemoveButton.disabled = !selectionMode || selectedIds.length === 0;
    selectionClearButton.disabled = sampleActionSelection.load(sampleActionsStorageKey).length === 0;
    const persistedIds = sampleActionSelection.load(sampleActionsStorageKey);
    selectionWorkspaceLink.href = sampleActionSelection.actionUrl(persistedIds, sampleActionsWorkspaceUrl);
    selectionWorkspaceLink.classList.toggle("is-disabled", persistedIds.length === 0);
    selectionWorkspaceLink.setAttribute("aria-disabled", persistedIds.length === 0 ? "true" : "false");
    selectionWorkspaceLink.textContent = persistedIds.length ? `Open actions workspace (${persistedIds.length})` : "Open actions workspace";
    selectionToggleButton.textContent = selectionMode
      ? "Exit Select"
      : persistedIds.length ? `Select (${persistedIds.length})` : "Select";
  }

  function selectedRowIds() {
    return rows.map((row) => row.id).filter((sampleId) => checkedRowIds.has(sampleId));
  }

  function handleSelectionInteraction(sampleId, event) {
    const additive = !!(event.ctrlKey || event.metaKey);
    const useRange = !!event.shiftKey && Number.isInteger(lastSelectedRowId);
    if (useRange) {
      selectRowRange(lastSelectedRowId, sampleId, additive);
      lastSelectedRowId = sampleId;
      renderTable();
      return;
    }
    if (additive) {
      if (checkedRowIds.has(sampleId)) {
        checkedRowIds.delete(sampleId);
      } else {
        checkedRowIds.add(sampleId);
      }
      lastSelectedRowId = sampleId;
      renderTable();
      return;
    }
    checkedRowIds.clear();
    checkedRowIds.add(sampleId);
    lastSelectedRowId = sampleId;
    renderTable();
  }

  function selectRowRange(anchorId, targetId, additive) {
    const rowOrder = rows.map((row) => row.id);
    const anchorIndex = rowOrder.indexOf(anchorId);
    const targetIndex = rowOrder.indexOf(targetId);
    if (anchorIndex === -1 || targetIndex === -1) {
      checkedRowIds.clear();
      checkedRowIds.add(targetId);
      return;
    }
    const start = Math.min(anchorIndex, targetIndex);
    const end = Math.max(anchorIndex, targetIndex);
    if (!additive) {
      checkedRowIds.clear();
    }
    rowOrder.slice(start, end + 1).forEach((sampleId) => checkedRowIds.add(sampleId));
  }

  function getColumnClassName(key, role) {
    const classes = [`sample-col`, `sample-col--${key}`];
    if (role === "header") {
      classes.push("sample-col--header");
    }
    if (role === "cell") {
      classes.push("sample-col--cell");
    }
    if (role === "col") {
      classes.push("sample-col--track");
    }
    if (compactColumns.has(key)) {
      classes.push("sample-col--compact");
    }
    if (numericColumns.has(key)) {
      classes.push("sample-col--numeric");
    }
    if (key === "location") {
      classes.push("sample-col--location");
    }
    return classes.join(" ");
  }

  function renderActiveState() {
    const activeChips = [];
      const optionLabels = {
        sample_type_ids: "Type",
        study_ids: "Study",
        study_roles: "Study Role",
        custodies: "Custody",
        usages: "Usage",
        visit_labels: "Visit",
        timepoint_labels: "Timepoint",
      };
    Object.entries(optionLabels).forEach(([field, label]) => {
      if (!state[field] || !state[field].length) {
        return;
      }
      activeChips.push(`<span class="samples-chip">${escapeHtml(label)}: ${escapeHtml(state[field].join(", "))}</span>`);
    });
    if (state.location_state) {
      activeChips.push(`<span class="samples-chip">Location: ${escapeHtml(state.location_state)}</span>`);
    }
    if (state.storage_node_ids?.length) {
      state.storage_node_ids.forEach((nodeId) => {
        const path = locationPathMap.get(nodeId);
        if (path) {
          activeChips.push(`<span class="samples-chip">Location: ${escapeHtml(path)}</span>`);
        }
      });
    }
    appendRangeChip(activeChips, "Volume", state.volume_min, state.volume_max);
    appendRangeChip(activeChips, "Aliquot", state.aliquot_min, state.aliquot_max);
    appendRangeChip(activeChips, "Hemolysis", state.hemolysis_min, state.hemolysis_max);
    appendRangeChip(activeChips, "Thaw", state.thaw_count_min, state.thaw_count_max);
    appendRangeChip(activeChips, "Collection", state.collection_from, state.collection_to);
    appendRangeChip(activeChips, "Registered", state.registered_from, state.registered_to);
    appendRangeChip(activeChips, "Updated", state.updated_from, state.updated_to);
    chips.innerHTML = activeChips.join("");
    resultCount.textContent = `${rows.length} sample${rows.length === 1 ? "" : "s"}`;
  }

  function appendRangeChip(target, label, fromValue, toValue) {
    if (!fromValue && !toValue) {
      return;
    }
    const value = [fromValue || "--", toValue || "--"].join(" to ");
    target.push(`<span class="samples-chip">${escapeHtml(label)}: ${escapeHtml(value)}</span>`);
  }

  function getFilterCount(columnKey) {
    if (columnKey === "location") {
      return (state.location_state ? 1 : 0) + (state.storage_node_ids?.length || 0);
    }
    if (optionColumns.has(columnKey)) {
      const field = multiValueFieldMap[columnKey];
      return state[field]?.length || 0;
    }
    if (numberRangeColumns.has(columnKey)) {
      const [minField, maxField] = numberFieldMap[columnKey];
      return (state[minField] ? 1 : 0) + (state[maxField] ? 1 : 0);
    }
    if (dateRangeColumns.has(columnKey)) {
      const [fromField, toField] = dateFieldMap[columnKey];
      return (state[fromField] ? 1 : 0) + (state[toField] ? 1 : 0);
    }
    return 0;
  }

  function buildQueryParams() {
    const params = new URLSearchParams();
    if (state.q) {
      params.set("q", state.q);
    }
    appendRepeated(params, "sample_type_ids", state.sample_type_ids);
    appendRepeated(params, "study_ids", state.study_ids);
    appendRepeated(params, "study_roles", state.study_roles);
    appendRepeated(params, "custodies", state.custodies);
    appendRepeated(params, "usages", state.usages);
    appendRepeated(params, "visit_labels", state.visit_labels);
    appendRepeated(params, "timepoint_labels", state.timepoint_labels);
    if (state.location_state) {
      params.set("location_state", state.location_state);
    }
    appendRepeated(params, "storage_node_ids", state.storage_node_ids);
    appendValue(params, "aliquot_min", state.aliquot_min);
    appendValue(params, "aliquot_max", state.aliquot_max);
    appendValue(params, "thaw_count_min", state.thaw_count_min);
    appendValue(params, "thaw_count_max", state.thaw_count_max);
    appendValue(params, "volume_min", state.volume_min);
    appendValue(params, "volume_max", state.volume_max);
    appendValue(params, "hemolysis_min", state.hemolysis_min);
    appendValue(params, "hemolysis_max", state.hemolysis_max);
    appendValue(params, "collection_from", state.collection_from);
    appendValue(params, "collection_to", state.collection_to);
    appendValue(params, "registered_from", state.registered_from);
    appendValue(params, "registered_to", state.registered_to);
    appendValue(params, "updated_from", state.updated_from);
    appendValue(params, "updated_to", state.updated_to);
    appendValue(params, "sort", state.sort);
    appendValue(params, "sort_dir", state.sort_dir);
    return params;
  }

  function buildFilterPayload() {
    return {
      q: state.q,
      sample_type_ids: state.sample_type_ids,
      study_ids: state.study_ids,
      study_roles: state.study_roles,
      custodies: state.custodies,
      usages: state.usages,
      location_state: state.location_state || null,
      storage_node_ids: state.storage_node_ids,
      visit_labels: state.visit_labels,
      timepoint_labels: state.timepoint_labels,
      aliquot_min: parseIntegerOrNull(state.aliquot_min),
      aliquot_max: parseIntegerOrNull(state.aliquot_max),
      hemolysis_min: parseFloatOrNull(state.hemolysis_min),
      hemolysis_max: parseFloatOrNull(state.hemolysis_max),
      thaw_count_min: parseIntegerOrNull(state.thaw_count_min),
      thaw_count_max: parseIntegerOrNull(state.thaw_count_max),
      volume_min: parseFloatOrNull(state.volume_min),
      volume_max: parseFloatOrNull(state.volume_max),
      collection_from: parseFilterDateToIso(state.collection_from),
      collection_to: parseFilterDateToIso(state.collection_to),
      registered_from: parseFilterDateToIso(state.registered_from),
      registered_to: parseFilterDateToIso(state.registered_to),
      updated_from: parseFilterDateToIso(state.updated_from),
      updated_to: parseFilterDateToIso(state.updated_to),
      sort: state.sort,
      sort_dir: state.sort_dir,
    };
  }

  function buildInitialState(initialState) {
    return {
      q: initialState.q || "",
      sample_type_ids: mergedList(initialState.sample_type_ids, initialState.sample_type_id),
      study_ids: mergedList(initialState.study_ids, initialState.study_id),
      study_roles: mergedList(initialState.study_roles, initialState.study_role),
      custodies: mergedList(initialState.custodies, initialState.custody),
      usages: mergedList(initialState.usages, initialState.usage),
      location_state: initialState.location_state || "",
      storage_node_ids: Array.isArray(initialState.storage_node_ids) ? initialState.storage_node_ids.map(Number) : [],
      visit_labels: mergedList(initialState.visit_labels, initialState.visit_label),
      timepoint_labels: mergedList(initialState.timepoint_labels, initialState.timepoint_label),
      aliquot_min: toInputValue(initialState.aliquot_min),
      aliquot_max: toInputValue(initialState.aliquot_max),
      hemolysis_min: toInputValue(initialState.hemolysis_min),
      hemolysis_max: toInputValue(initialState.hemolysis_max),
      thaw_count_min: toInputValue(initialState.thaw_count_min),
      thaw_count_max: toInputValue(initialState.thaw_count_max),
      volume_min: toInputValue(initialState.volume_min),
      volume_max: toInputValue(initialState.volume_max),
      collection_from: initialState.collection_from ? formatInputDate(initialState.collection_from) : "",
      collection_to: initialState.collection_to ? formatInputDate(initialState.collection_to) : "",
      registered_from: initialState.registered_from ? formatInputDate(initialState.registered_from) : "",
      registered_to: initialState.registered_to ? formatInputDate(initialState.registered_to) : "",
      updated_from: initialState.updated_from ? formatInputDate(initialState.updated_from) : "",
      updated_to: initialState.updated_to ? formatInputDate(initialState.updated_to) : "",
      sort: initialState.sort || "sample_id",
      sort_dir: initialState.sort_dir || "asc",
      visible_columns: loadVisibleColumns(),
    };
  }

  function loadVisibleColumns() {
    try {
      const raw = window.localStorage.getItem(visibleColumnsStorageKey);
      if (!raw) {
        return [...defaultVisibleColumns];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.length) {
        return [...defaultVisibleColumns];
      }
      return parsed.filter((key) => columnMap.has(key));
    } catch {
      return [...defaultVisibleColumns];
    }
  }

  function renderCell(row, key) {
    if (key === "sample_id") {
      return `<a href="/samples/${row.id}"><strong>${escapeHtml(row.sample_id)}</strong></a>`;
    }
    if (key === "study") {
      return escapeHtml(row.study_name || "--");
    }
    if (key === "sample_type") {
      return escapeHtml(row.sample_type_name || "Unassigned");
    }
    if (key === "study_role") {
      return escapeHtml((row.study_role || "").replaceAll("_", " ") || "--");
    }
    if (key === "custody") {
      return escapeHtml((row.custody_label || "").replaceAll("_", " ") || "--");
    }
    if (key === "usage") {
      return escapeHtml((row.usage_label || "").replaceAll("_", " ") || "--");
    }
    if (key === "volume") {
      if (row.volume === null || row.volume === undefined) {
        return "--";
      }
      return `${escapeHtml(String(row.volume))} ${escapeHtml(row.volume_units || "")}`.trim();
    }
    if (key === "location") {
      return escapeHtml(row.location_path || "Unplaced");
    }
    if (key === "visit_label") {
      return escapeHtml(row.visit_label || "--");
    }
    if (key === "timepoint_label") {
      return escapeHtml(row.timepoint_label || "--");
    }
    if (key === "aliquot_number") {
      return row.aliquot_number === null || row.aliquot_number === undefined ? "--" : escapeHtml(String(row.aliquot_number));
    }
    if (key === "hemolysis_classification") {
      return row.hemolysis_classification === null || row.hemolysis_classification === undefined ? "--" : escapeHtml(String(row.hemolysis_classification));
    }
    if (key === "thaw_count") {
      return escapeHtml(String(row.thaw_count ?? 0));
    }
    if (key === "collection_at") {
      return formatDateTime(row.collection_at);
    }
    if (key === "created_at") {
      return formatDateTime(row.created_at);
    }
    if (key === "updated_at") {
      return formatDateTime(row.updated_at);
    }
    return "--";
  }

  function renderOptionInputs(columnKey, options) {
    if (columnKey === "location") {
      const selected = state.location_state || "";
      return `
        <label class="samples-option-item samples-option-card">
          <input type="radio" name="location-filter" value="" ${selected === "" ? "checked" : ""} />
          <span class="samples-option-label">Either</span>
          <small class="samples-option-count">All</small>
        </label>
        ${options
          .map(
            (option) => `
              <label class="samples-option-item samples-option-card" data-filter-label="${escapeHtml(option.label)}">
                <input type="radio" name="location-filter" value="${escapeHtml(option.value)}" ${option.selected ? "checked" : ""} />
                <span class="samples-option-label">${escapeHtml(option.label)}</span>
                <small class="samples-option-count">${option.count}</small>
              </label>
            `
          )
          .join("")}
      `;
    }
    return options
      .map(
        (option) => `
          <label class="samples-option-item samples-option-card" data-filter-label="${escapeHtml(option.label)}">
            <input type="checkbox" value="${escapeHtml(option.value)}" ${option.selected ? "checked" : ""} />
            <span class="samples-option-label">${escapeHtml(option.label)}</span>
            <small class="samples-option-count">${option.count}</small>
          </label>
        `
      )
      .join("");
  }

  function renderSortButtons(columnKey) {
    return `
      <button type="button" class="ghost-button samples-sort-button" data-action="sort" data-sort-column="${columnKey}" data-sort-dir="asc" title="Sort ascending">Ascending</button>
      <button type="button" class="ghost-button samples-sort-button" data-action="sort" data-sort-column="${columnKey}" data-sort-dir="desc" title="Sort descending">Descending</button>
      <button type="button" class="ghost-button samples-sort-button" data-action="clear-sort" title="Clear sort">Clear Sort</button>
    `;
  }

  function renderNumberRangeFields(columnKey) {
    const [minField, maxField] = numberFieldMap[columnKey];
    const step = columnKey === "volume" ? "0.01" : columnKey === "hemolysis_classification" ? "0.5" : "1";
    return `
      <div class="samples-range-grid">
        <label>Min
          <input type="number" step="${step}" name="${minField}" value="${escapeHtml(state[minField] || "")}" />
        </label>
        <label>Max
          <input type="number" step="${step}" name="${maxField}" value="${escapeHtml(state[maxField] || "")}" />
        </label>
      </div>
    `;
  }

  function renderDateRangeFields(columnKey) {
    const [fromField, toField] = dateFieldMap[columnKey];
    return `
      <div class="samples-range-grid">
        <label>From
          <input type="text" name="${fromField}" value="${escapeHtml(state[fromField] || "")}" placeholder="MM/DD/YY HH:MM" />
        </label>
        <label>To
          <input type="text" name="${toField}" value="${escapeHtml(state[toField] || "")}" placeholder="MM/DD/YY HH:MM" />
        </label>
      </div>
    `;
  }

  function renderLocationTree(nodes, depth = 0) {
    if (!nodes.length) {
      return `<p class="muted">No storage locations available.</p>`;
    }
    return `
      <div class="samples-location-tree">
        ${nodes.map((node) => renderLocationNode(node, depth)).join("")}
      </div>
    `;
  }

  function renderLocationNode(node, depth) {
    const hasChildren = Array.isArray(node.children) && node.children.length > 0;
    const selected = state.storage_node_ids.includes(node.id);
    const collapsed = depth > 0 ? " is-collapsed" : "";
    return `
      <div class="samples-location-branch${collapsed}" data-location-branch="${node.id}" data-location-depth="${depth}">
        <div class="samples-location-row" style="--location-depth:${depth}">
          ${hasChildren
            ? `<button type="button" class="tree-toggle samples-location-toggle" data-location-toggle="${node.id}">${depth > 0 ? "+" : "-"}</button>`
            : `<span class="tree-spacer"></span>`}
          <label class="samples-location-check">
            <input type="checkbox" name="storage-node-filter" value="${node.id}" ${selected ? "checked" : ""} />
            <span>${escapeHtml(node.display_name)}</span>
          </label>
          <span class="node-kind">${escapeHtml(node.node_type)}</span>
        </div>
        ${hasChildren ? `<div class="samples-location-children">${renderLocationTree(node.children, depth + 1)}</div>` : ""}
      </div>
    `;
  }

  function updateLocationSummary() {
    const summary = document.getElementById("samples-location-summary");
    if (!summary) {
      return;
    }
    const selectedIds = Array.from(filterWindow.querySelectorAll("input[name='storage-node-filter']:checked"))
      .map((input) => Number.parseInt(input.value, 10))
      .filter((value) => !Number.isNaN(value));
    const mode = filterWindow.querySelector("input[name='location-filter']:checked")?.value || "";
    const normalizedIds = normalizeSelectedLocationIds(selectedIds);
    if (selectedIds.length !== normalizedIds.length) {
      filterWindow.querySelectorAll("input[name='storage-node-filter']").forEach((checkbox) => {
        checkbox.checked = normalizedIds.includes(Number.parseInt(checkbox.value, 10));
      });
    }
    const labels = normalizedIds.map((nodeId) => locationPathMap.get(nodeId)).filter(Boolean);
    if (mode === "unplaced") {
      summary.innerHTML = `<span class="samples-chip">Unplaced only</span>`;
      return;
    }
    if (mode === "placed" && !labels.length) {
      summary.innerHTML = `<span class="samples-chip">Placed only</span>`;
      return;
    }
    if (!labels.length) {
      summary.innerHTML = `<span class="muted">Select a freezer, shelf, rack, or box to filter by that branch.</span>`;
      return;
    }
    summary.innerHTML = labels
      .map((label) => `<span class="samples-chip">${escapeHtml(label)}</span>`)
      .join("");
  }

  function updateLocationTreeDisabledState() {
    const wrap = document.getElementById("samples-location-tree-wrap");
    if (!wrap) {
      return;
    }
    const disabled = filterWindow.querySelector("input[name='location-filter'][value='unplaced']")?.checked;
    wrap.classList.toggle("is-disabled", !!disabled);
    wrap.querySelectorAll("input, button").forEach((node) => {
      node.disabled = !!disabled;
    });
  }

  function normalizeSelectedLocationIds(selectedIds) {
    const selectedSet = new Set(selectedIds);
    return selectedIds.filter((nodeId) => {
      let currentParentId = locationNodeMap.get(nodeId)?.parent_id ?? null;
      while (currentParentId !== null && currentParentId !== undefined) {
        if (selectedSet.has(currentParentId)) {
          return false;
        }
        currentParentId = locationNodeMap.get(currentParentId)?.parent_id ?? null;
      }
      return true;
    });
  }

  function collapseDescendantSelections(nodeId) {
    const descendants = collectDescendantIds(nodeId);
    filterWindow.querySelectorAll("input[name='storage-node-filter']").forEach((checkbox) => {
      const value = Number.parseInt(checkbox.value, 10);
      if (descendants.includes(value)) {
        checkbox.checked = false;
      }
    });
  }

  function collectDescendantIds(nodeId) {
    const descendants = [];
    const stack = [...(locationChildrenMap.get(nodeId) || [])];
    while (stack.length) {
      const childId = stack.pop();
      descendants.push(childId);
      stack.push(...(locationChildrenMap.get(childId) || []));
    }
    return descendants;
  }

  function indexLocationTree(nodes, parentId = null, path = []) {
    nodes.forEach((node) => {
      const nextPath = [...path, node.display_name];
      locationNodeMap.set(node.id, { ...node, parent_id: parentId });
      locationChildrenMap.set(node.id, (node.children || []).map((child) => child.id));
      locationPathMap.set(node.id, nextPath.join(" / "));
      if (node.children?.length) {
        indexLocationTree(node.children, node.id, nextPath);
      }
    });
  }

  function openColumnPicker(anchor) {
    columnPopover.hidden = false;
    columnPopover.classList.remove("hidden");
    const anchorRect = anchor.getBoundingClientRect();
    const rootRect = root.getBoundingClientRect();
    const nodeRect = columnPopover.getBoundingClientRect();
    const maxLeft = Math.max(rootRect.width - nodeRect.width - 12, 0);
    const desiredLeft = anchorRect.left - rootRect.left - 8;
    columnPopover.style.top = `${anchorRect.bottom - rootRect.top + 8}px`;
    columnPopover.style.left = `${Math.min(Math.max(desiredLeft, 0), maxLeft)}px`;
  }

  function closeFilterWindow() {
    filterOverlay.hidden = true;
    filterOverlay.classList.add("hidden");
  }

  function closeColumnPicker() {
    columnPopover.hidden = true;
    columnPopover.classList.add("hidden");
  }

  function closeOverlays() {
    closeFilterWindow();
    closeColumnPicker();
  }

  function openBulkDialog() {
    if (!bulkDialog) {
      return;
    }
    bulkDialog.showModal();
  }

  function closeBulkDialog() {
    bulkDialog?.close();
  }

  function resetBulkDialog() {
    bulkPreviewPayload = null;
    if (bulkFileInput) {
      bulkFileInput.value = "";
      bulkFileInput.disabled = false;
    }
    if (bulkCommitButton) {
      bulkCommitButton.disabled = true;
      bulkCommitButton.hidden = true;
      bulkCommitButton.classList.add("hidden");
      bulkCommitButton.textContent = "Import Valid Rows";
    }
    if (bulkResetButton) {
      bulkResetButton.hidden = true;
      bulkResetButton.classList.add("hidden");
    }
    if (bulkPreviewBox) {
      bulkPreviewBox.innerHTML = "";
      bulkPreviewBox.hidden = true;
      bulkPreviewBox.classList.add("hidden");
    }
    setBulkStatus("");
    setBulkError("");
  }

  async function handleBulkFileSelected() {
    const file = bulkFileInput?.files?.[0];
    if (!file) {
      resetBulkDialog();
      return;
    }
    setBulkError("");
    setBulkStatus("Validating workbook...", "info");
    if (bulkPreviewBox) {
      bulkPreviewBox.innerHTML = "";
      bulkPreviewBox.hidden = true;
      bulkPreviewBox.classList.add("hidden");
    }
    if (bulkCommitButton) {
      bulkCommitButton.disabled = true;
      bulkCommitButton.hidden = true;
      bulkCommitButton.classList.add("hidden");
    }
    if (bulkResetButton) {
      bulkResetButton.hidden = false;
      bulkResetButton.classList.remove("hidden");
    }
    if (bulkFileInput) {
      bulkFileInput.disabled = true;
    }
    try {
      const formData = new FormData();
      formData.append("import_file", file);
      const response = await fetch("/api/samples/bulk/preview-upload", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to preview workbook");
      }
      bulkPreviewPayload = payload;
      renderBulkPreview(payload);
    } catch (error) {
      bulkPreviewPayload = null;
      setBulkStatus("");
      setBulkError(error.message || "Unable to preview workbook");
    } finally {
      if (bulkFileInput) {
        bulkFileInput.disabled = false;
      }
    }
  }

  async function commitBulkImport() {
    if (!bulkPreviewPayload?.raw_payload) {
      return;
    }
    setBulkError("");
    setBulkStatus("Importing samples...", "info");
    if (bulkCommitButton) {
      bulkCommitButton.disabled = true;
      bulkCommitButton.textContent = "Importing...";
    }
    try {
      const response = await fetch("/api/samples/bulk/commit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          raw_payload: bulkPreviewPayload.raw_payload,
          target_box_id: null,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to import workbook");
      }
      renderBulkResult(payload);
      await fetchRows();
    } catch (error) {
      setBulkStatus("");
      setBulkError(error.message || "Unable to import workbook");
      if (bulkCommitButton) {
        bulkCommitButton.disabled = false;
        bulkCommitButton.textContent = "Import Valid Rows";
      }
    }
  }

  function renderBulkPreview(preview) {
    const hasGlobalErrors = Array.isArray(preview.global_errors) && preview.global_errors.length > 0;
    const hasValidRows = Number(preview.valid_rows || 0) > 0;
    const hasInvalidRows = Number(preview.invalid_rows || 0) > 0;
    setBulkStatus(
      `Preview ready: ${preview.valid_rows || 0} valid / ${preview.invalid_rows || 0} invalid / ${preview.total_rows || 0} total`,
      hasInvalidRows || hasGlobalErrors ? "warning" : "success",
    );
    if (bulkPreviewBox) {
      bulkPreviewBox.innerHTML = renderBulkTable(
        "Preview",
        preview.rows || [],
        preview.global_errors || [],
        `${preview.valid_rows || 0} valid / ${preview.invalid_rows || 0} invalid / ${preview.total_rows || 0} total`,
      );
      bulkPreviewBox.hidden = false;
      bulkPreviewBox.classList.remove("hidden");
    }
    if (bulkCommitButton) {
      bulkCommitButton.hidden = false;
      bulkCommitButton.classList.remove("hidden");
      bulkCommitButton.disabled = !hasValidRows || hasGlobalErrors;
      bulkCommitButton.textContent = "Import Valid Rows";
    }
  }

  function renderBulkResult(result) {
    const hasFailures = Number(result.failed_rows || 0) > 0 || (result.global_errors || []).length > 0;
    setBulkStatus(
      `Import complete: ${result.imported_rows || 0} imported / ${result.skipped_rows || 0} skipped / ${result.failed_rows || 0} failed`,
      hasFailures ? "warning" : "success",
    );
    if (bulkPreviewBox) {
      bulkPreviewBox.innerHTML = renderBulkTable(
        "Import Result",
        result.rows || [],
        result.global_errors || [],
        `${result.imported_rows || 0} imported / ${result.skipped_rows || 0} skipped / ${result.failed_rows || 0} failed`,
      );
      bulkPreviewBox.hidden = false;
      bulkPreviewBox.classList.remove("hidden");
    }
    if (bulkCommitButton) {
      bulkCommitButton.hidden = true;
      bulkCommitButton.classList.add("hidden");
      bulkCommitButton.disabled = true;
      bulkCommitButton.textContent = "Import Valid Rows";
    }
    if (bulkResetButton) {
      bulkResetButton.hidden = false;
      bulkResetButton.classList.remove("hidden");
    }
  }

  function renderBulkTable(title, rows, globalErrors, summary) {
    return `
      <div class="section-head">
        <div>
          <h3>${escapeHtml(title)}</h3>
          <p class="muted">${escapeHtml(summary)}</p>
        </div>
      </div>
      ${globalErrors.length ? `
        <div class="bulk-errors">
          ${globalErrors.map((error) => `<p class="form-error">${escapeHtml(error)}</p>`).join("")}
        </div>
      ` : ""}
      <div class="bulk-table-wrap">
        <table class="table bulk-table samples-bulk-table">
          <thead>
            <tr>
              <th>Row</th>
              <th>ID</th>
              <th>Type</th>
              <th>Placement</th>
              <th>Box</th>
              <th>Position</th>
              <th>Status</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr class="bulk-row-${escapeHtml(row.status || "invalid")}">
                <td>${escapeHtml(String(row.row_number ?? "--"))}</td>
                <td>${escapeHtml(row.sample_id || "--")}</td>
                <td>${escapeHtml(row.sample_type || "--")}</td>
                <td>${escapeHtml(renderPlacementSummary(row))}</td>
                <td>${escapeHtml(row.assigned_box_name || row.box || "--")}</td>
                <td>${escapeHtml(row.assigned_position || row.position || "--")}</td>
                <td><span class="status-pill">${escapeHtml(row.status || "--")}</span></td>
                <td>${escapeHtml((row.errors || []).join("; ") || "--")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderPlacementSummary(row) {
    const parts = [row.placement_mode || "--"];
    if (row.placement_group) {
      parts.push(`#${row.placement_group}`);
    }
    if (row.placement_offset !== null && row.placement_offset !== undefined && row.placement_offset !== "") {
      parts.push(`+${row.placement_offset}`);
    }
    return parts.join(" ");
  }

  function setBulkError(message) {
    if (!bulkErrorBox) {
      return;
    }
    bulkErrorBox.textContent = message;
    bulkErrorBox.classList.toggle("hidden", !message);
  }

  function setBulkStatus(message, tone = "info") {
    if (!bulkStatusBox) {
      return;
    }
    bulkStatusBox.textContent = message;
    bulkStatusBox.dataset.tone = tone;
    bulkStatusBox.classList.toggle("hidden", !message);
  }

  function setError(message) {
    errorBox.textContent = message;
    errorBox.classList.toggle("hidden", !message);
  }

  function appendRepeated(params, key, values) {
    (values || []).forEach((value) => {
      if (value !== null && value !== undefined && value !== "") {
        params.append(key, value);
      }
    });
  }

  function appendValue(params, key, value) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, value);
    }
  }

  function mergedList(values, single) {
    const merged = Array.isArray(values) ? [...values] : [];
    if (single !== null && single !== undefined && single !== "" && !merged.includes(single)) {
      merged.push(single);
    }
    return merged.map(String);
  }

  function parseIntegerOrNull(value) {
    if (value === "" || value === null || value === undefined) {
      return null;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function parseFloatOrNull(value) {
    if (value === "" || value === null || value === undefined) {
      return null;
    }
    const parsed = Number.parseFloat(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function formatDateTime(value) {
    if (!value) {
      return "--";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "--";
    }
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const year = String(date.getFullYear()).slice(-2);
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${month}/${day}/${year} ${hours}:${minutes}`;
  }

  function formatInputDate(value) {
    return formatDateTime(value).replace("--", "");
  }

  function parseFilterDateToIso(value) {
    if (!value) {
      return null;
    }
    const match = String(value).trim().match(/^(\d{2})\/(\d{2})\/(\d{2}) (\d{2}):(\d{2})$/);
    if (!match) {
      return null;
    }
    const [, month, day, year, hours, minutes] = match;
    return `20${year}-${month}-${day}T${hours}:${minutes}:00`;
  }

  function toInputValue(value) {
    return value === null || value === undefined ? "" : String(value);
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
