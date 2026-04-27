(() => {
  const browser = document.querySelector("[data-storage-browser]");
  if (!browser) return;

  const canManageTree = browser.dataset.manageTree === "true";
  const allowedChildren = {
    root: ["freezer"],
    freezer: ["shelf", "rack"],
    shelf: ["rack", "box"],
    rack: ["box"],
    box: [],
  };
  const storageStateKey = "storage-browser-collapsed";

  const addDialog = document.getElementById("storage-add-dialog");
  const addForm = document.getElementById("storage-add-form");
  const editDialog = document.getElementById("storage-edit-dialog");
  const editForm = document.getElementById("storage-edit-form");
  const moveDialog = document.getElementById("storage-move-dialog");
  const moveForm = document.getElementById("storage-move-form");
  const moveSelectedButton = document.getElementById("storage-move-selected-button");
  const clearSelectedButton = document.getElementById("storage-clear-selected-button");
  const moveTargetSelect = document.getElementById("storage-move-target");
  const moveSummary = document.getElementById("storage-move-summary");
  const moveHelp = document.getElementById("storage-move-help");
  const moveSubmitButton = document.getElementById("storage-move-submit");
  const deleteButton = document.getElementById("storage-delete-button");
  const bulkOpenButton = document.getElementById("storage-bulk-open");
  const bulkDialog = document.getElementById("storage-bulk-dialog");
  const bulkCloseButton = document.getElementById("storage-bulk-close");
  const bulkFileInput = document.getElementById("storage-bulk-file");
  const bulkErrorBox = document.getElementById("storage-bulk-error");
  const bulkStatusBox = document.getElementById("storage-bulk-status");
  const bulkPreviewBox = document.getElementById("storage-bulk-preview");
  const bulkResetButton = document.getElementById("storage-bulk-reset");
  const bulkRefreshButton = document.getElementById("storage-bulk-refresh");
  const bulkCommitButton = document.getElementById("storage-bulk-commit");
  const collapsed = new Set(loadCollapsedState(browser));
  const selectedNodeIds = new Set();
  let lastSelectedNodeId = null;
  let draggedId = null;
  let draggedNodeIds = [];
  let bulkPreviewPayload = null;

  browser.querySelectorAll(".storage-node").forEach((node) => {
    const nodeId = node.dataset.nodeId;
    setNodeCollapsed(node, nodeId ? collapsed.has(nodeId) : false);
  });

  document.addEventListener("click", async (event) => {
    const actionTarget = event.target.closest("[data-action]");
    if (!actionTarget) return;

    const action = actionTarget.dataset.action;
    const node = actionTarget.closest(".storage-node");

    if (action === "toggle" && node) {
      toggleNode(node);
      return;
    }

    if (action === "close-dialog") {
      addDialog?.close();
      editDialog?.close();
      moveDialog?.close();
      return;
    }

    if (!canManageTree) return;

    if (action === "clear-selected") {
      clearSelection();
      return;
    }

    if (action === "add-root") {
      openAddDialog(null);
      return;
    }

    if (action === "add-child" && node) {
      openAddDialog(node);
      return;
    }

    if (action === "edit" && node) {
      openEditDialog(node);
    }
  });

  if (canManageTree) {
    browser.querySelectorAll(".storage-row").forEach((row) => {
      row.addEventListener("click", handleRowClick);
      row.addEventListener("dragstart", handleDragStart);
      row.addEventListener("dragend", clearDragState);
      row.addEventListener("dragover", handleDragOver);
      row.addEventListener("dragleave", handleDragLeave);
      row.addEventListener("drop", handleDrop);
    });

    addForm?.addEventListener("submit", handleAddSubmit);
    editForm?.addEventListener("submit", handleEditSubmit);
    deleteButton?.addEventListener("click", handleDelete);
    document.getElementById("add-node-type")?.addEventListener("change", toggleAddStorageFields);
    document.getElementById("add-box-rack-col")?.addEventListener("input", uppercaseInput);
    document.getElementById("edit-box-rack-col")?.addEventListener("input", uppercaseInput);
    moveSelectedButton?.addEventListener("click", openMoveDialog);
    moveForm?.addEventListener("submit", handleMoveSubmit);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && selectedNodeIds.size && !document.querySelector("dialog[open]")) {
        clearSelection();
      }
    });
    renderSelectionState();
  }

  if (bulkDialog && bulkOpenButton) {
    bulkOpenButton.addEventListener("click", openBulkDialog);
    bulkCloseButton?.addEventListener("click", closeBulkDialog);
    bulkResetButton?.addEventListener("click", resetBulkDialog);
    bulkRefreshButton?.addEventListener("click", () => window.location.assign("/storage"));
    bulkFileInput?.addEventListener("change", handleBulkFileSelected);
    bulkCommitButton?.addEventListener("click", commitBulkImport);
    bulkDialog.addEventListener("click", (event) => {
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
    bulkDialog.addEventListener("close", resetBulkDialog);
    if (new URLSearchParams(window.location.search).get("bulk") === "boxes") {
      openBulkDialog();
    }
  }

  function handleRowClick(event) {
    const row = event.currentTarget;
    const node = row.closest(".storage-node[data-node-id]");
    if (!node) return;
    if (event.target.closest("[data-action], a, button, input, textarea, select")) {
      return;
    }
    const nodeId = node.dataset.nodeId;
    if (!nodeId) return;

    if (event.shiftKey && lastSelectedNodeId) {
      selectRange(lastSelectedNodeId, nodeId, event.ctrlKey || event.metaKey);
      lastSelectedNodeId = nodeId;
      renderSelectionState();
      return;
    }

    if (event.ctrlKey || event.metaKey) {
      if (selectedNodeIds.has(nodeId)) {
        selectedNodeIds.delete(nodeId);
      } else {
        selectedNodeIds.add(nodeId);
      }
      lastSelectedNodeId = nodeId;
      renderSelectionState();
      return;
    }

    selectedNodeIds.clear();
    selectedNodeIds.add(nodeId);
    lastSelectedNodeId = nodeId;
    renderSelectionState();
  }

  function toggleNode(node) {
    const nodeId = node.dataset.nodeId;
    if (!nodeId) return;

    if (collapsed.has(nodeId)) {
      collapsed.delete(nodeId);
      saveCollapsedState();
      setNodeCollapsed(node, false);
      return;
    }

    collapseNodeAndDescendants(node);
  }

  function collapseNodeAndDescendants(node) {
    const nodeId = node.dataset.nodeId;
    if (!nodeId) return;
    collapsed.add(nodeId);
    setNodeCollapsed(node, true);
    node.querySelectorAll(".storage-node").forEach((child) => {
      if (child.dataset.nodeId) {
        collapsed.add(child.dataset.nodeId);
      }
      setNodeCollapsed(child, true);
    });
    saveCollapsedState();
  }

  function setNodeCollapsed(node, isCollapsed) {
    const toggle = node.querySelector(":scope > .storage-row [data-action='toggle']");
    const children = node.querySelector(":scope > .tree-children");
    if (!toggle || !children) return;
    node.classList.toggle("storage-node-collapsed", isCollapsed);
    children.hidden = isCollapsed;
    toggle.textContent = isCollapsed ? "+" : "-";
    toggle.setAttribute("aria-expanded", String(!isCollapsed));
  }

  function openAddDialog(node) {
    if (!addDialog || !addForm) return;
    const parentIdField = document.getElementById("add-parent-id");
    const parentLabelField = document.getElementById("add-parent-label");
    const typeSelect = document.getElementById("add-node-type");
    const nameField = document.getElementById("add-node-name");
    const notesField = document.getElementById("add-node-notes");
    const rackRowsField = document.getElementById("add-rack-rows");
    const rackColsField = document.getElementById("add-rack-cols");
    const rackSlotRowField = document.getElementById("add-box-rack-row");
    const rackSlotColField = document.getElementById("add-box-rack-col");

    const parentType = node ? node.dataset.nodeType : "root";
    const types = allowedChildren[parentType] || [];
    parentIdField.value = node ? node.dataset.nodeId : "";
    parentLabelField.value = node ? node.dataset.nodeDisplayName : "Root";
    typeSelect.innerHTML = types.map((type) => `<option value="${type}">${type}</option>`).join("");
    nameField.value = "";
    notesField.value = "";
    document.getElementById("add-box-rows").value = "";
    document.getElementById("add-box-cols").value = "";
    rackRowsField.value = "";
    rackColsField.value = "";
    rackSlotRowField.value = "";
    rackSlotColField.value = "";
    toggleAddStorageFields();
    addDialog.showModal();
  }

  function openEditDialog(node) {
    if (!editDialog || !editForm) return;
    document.getElementById("edit-node-id").value = node.dataset.nodeId;
    document.getElementById("edit-node-type").value = node.dataset.nodeType;
    document.getElementById("edit-node-name").value = node.dataset.nodeName;
    document.getElementById("edit-node-notes").value = node.dataset.nodeNotes || "";
    document.getElementById("edit-rack-rows").value = node.dataset.rackLayoutRows || "";
    document.getElementById("edit-rack-cols").value = node.dataset.rackLayoutCols || "";
    document.getElementById("edit-box-rack-row").value = node.dataset.rackSlotRow || "";
    document.getElementById("edit-box-rack-col").value = node.dataset.rackSlotColLabel || "";
    document.getElementById("edit-node-path").textContent = node.dataset.nodePath;
    toggleEditStorageFields(node);
    editDialog.showModal();
  }

  function openMoveDialog() {
    if (!moveDialog || !moveTargetSelect || !moveSummary || !moveHelp || !moveSubmitButton) return;
    const selectedNodes = selectedNodeDetails();
    if (!selectedNodes.length) {
      return;
    }
    const options = buildMoveTargetOptions(selectedNodes);
    moveSummary.textContent = summarizeSelection(selectedNodes);
    moveTargetSelect.innerHTML = options.length
      ? options.map((option) => `<option value="${option.value}">${escapeHtml(option.label)}</option>`).join("")
      : "";
    const hasOptions = options.length > 0;
    moveHelp.textContent = hasOptions
      ? "Choose the new parent location for the selected items."
      : "No valid destination is available for the current selection.";
    moveHelp.classList.toggle("hidden", false);
    moveTargetSelect.disabled = !hasOptions;
    moveSubmitButton.disabled = !hasOptions;
    moveDialog.showModal();
  }

  function toggleAddStorageFields() {
    const typeSelect = document.getElementById("add-node-type");
    const boxDimensions = document.getElementById("box-dimensions");
    const rackLayoutFields = document.getElementById("rack-layout-fields");
    const boxRackSlotFields = document.getElementById("box-rack-slot-fields");
    const rackSlotHelp = document.getElementById("add-box-rack-slot-help");
    const rackSlotRowField = document.getElementById("add-box-rack-row");
    const rackSlotColField = document.getElementById("add-box-rack-col");
    if (!typeSelect || !boxDimensions || !rackLayoutFields || !boxRackSlotFields || !rackSlotHelp || !rackSlotRowField || !rackSlotColField) return;
    const selectedType = typeSelect.value;
    boxDimensions.classList.toggle("hidden", selectedType !== "box");
    rackLayoutFields.classList.toggle("hidden", selectedType !== "rack");
    const parentId = document.getElementById("add-parent-id")?.value || "";
    const parentNode = parentId ? browser.querySelector(`.storage-node[data-node-id="${parentId}"]`) : null;
    const isRackParent = parentNode?.dataset.nodeType === "rack";
    const canUseRackSlot = selectedType === "box" && isRackParent && Boolean(parentNode?.dataset.rackLayoutLabel);
    boxRackSlotFields.classList.toggle("hidden", selectedType !== "box" || !isRackParent);
    rackSlotRowField.disabled = !canUseRackSlot;
    rackSlotColField.disabled = !canUseRackSlot;
    if (canUseRackSlot) {
      rackSlotRowField.max = parentNode.dataset.rackLayoutRows || "";
      rackSlotColField.maxLength = columnNumberToLabel(Number(parentNode.dataset.rackLayoutCols || 1)).length;
      rackSlotHelp.textContent = `Optional. Parent rack layout is ${parentNode.dataset.rackLayoutLabel}. Enter row number and column letter; the tree shows it as column + row, like A2.`;
    } else {
      rackSlotRowField.value = "";
      rackSlotColField.value = "";
      rackSlotRowField.removeAttribute("max");
      rackSlotColField.removeAttribute("maxLength");
      rackSlotHelp.textContent = "Configure a rack layout on the parent rack before assigning box rack positions.";
    }
  }

  function toggleEditStorageFields(node) {
    const isRack = node?.dataset.nodeType === "rack";
    const isBox = node?.dataset.nodeType === "box";
    const editRackLayoutFields = document.getElementById("edit-rack-layout-fields");
    const editBoxRackSlotFields = document.getElementById("edit-box-rack-slot-fields");
    const rackSlotHelp = document.getElementById("edit-box-rack-slot-help");
    const rackSlotRowField = document.getElementById("edit-box-rack-row");
    const rackSlotColField = document.getElementById("edit-box-rack-col");
    if (!editRackLayoutFields || !editBoxRackSlotFields || !rackSlotHelp || !rackSlotRowField || !rackSlotColField) return;
    editRackLayoutFields.classList.toggle("hidden", !isRack);
    const parentNodeId = node?.dataset.parentId || "";
    const parentNode = parentNodeId ? browser.querySelector(`.storage-node[data-node-id="${parentNodeId}"]`) : null;
    const isRackParent = parentNode?.dataset.nodeType === "rack";
    const canUseRackSlot = isBox && isRackParent && Boolean(parentNode?.dataset.rackLayoutLabel);
    editBoxRackSlotFields.classList.toggle("hidden", !isBox || !isRackParent);
    rackSlotRowField.disabled = !canUseRackSlot;
    rackSlotColField.disabled = !canUseRackSlot;
    if (canUseRackSlot) {
      rackSlotRowField.max = parentNode.dataset.rackLayoutRows || "";
      rackSlotColField.maxLength = columnNumberToLabel(Number(parentNode.dataset.rackLayoutCols || 1)).length;
      rackSlotHelp.textContent = `Optional. Parent rack layout is ${parentNode.dataset.rackLayoutLabel}. Enter row number and column letter; the tree shows it as column + row, like A2.`;
    } else {
      rackSlotRowField.value = "";
      rackSlotColField.value = "";
      rackSlotRowField.removeAttribute("max");
      rackSlotColField.removeAttribute("maxLength");
      rackSlotHelp.textContent = "Configure a rack layout on the parent rack before assigning box rack positions.";
    }
  }

  async function handleAddSubmit(event) {
    event.preventDefault();
    const nodeType = document.getElementById("add-node-type").value;
    const rackSlot = nodeType === "box" ? rackSlotFromFields("add-box-rack-row", "add-box-rack-col", "add") : null;
    if (rackSlot === undefined) return;
    const payload = {
      name: document.getElementById("add-node-name").value,
      notes: document.getElementById("add-node-notes").value || null,
      node_type: nodeType,
      parent_id: numberOrNull(document.getElementById("add-parent-id").value),
      rack_rows: nodeType === "rack" ? numberOrNull(document.getElementById("add-rack-rows").value) : null,
      rack_cols: nodeType === "rack" ? numberOrNull(document.getElementById("add-rack-cols").value) : null,
      rack_slot: rackSlot,
    };
    const response = await fetchJson("/api/storage/node", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (payload.node_type === "box") {
      const rows = numberOrNull(document.getElementById("add-box-rows").value);
      const cols = numberOrNull(document.getElementById("add-box-cols").value);
      if (rows && cols) {
        await fetchJson("/api/storage/box", {
          method: "POST",
          body: JSON.stringify({ box_id: response.id, rows, cols }),
        });
      }
    }
    reloadWithCurrentState();
  }

  async function handleEditSubmit(event) {
    event.preventDefault();
    const nodeId = document.getElementById("edit-node-id").value;
    const nodeType = document.getElementById("edit-node-type").value;
    const rackSlot = nodeType === "box" ? rackSlotFromFields("edit-box-rack-row", "edit-box-rack-col", "edit") : null;
    if (rackSlot === undefined) return;
    await fetchJson(`/api/storage/node/${nodeId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: document.getElementById("edit-node-name").value,
        notes: document.getElementById("edit-node-notes").value || null,
        rack_rows: nodeType === "rack" ? numberOrNull(document.getElementById("edit-rack-rows").value) : null,
        rack_cols: nodeType === "rack" ? numberOrNull(document.getElementById("edit-rack-cols").value) : null,
        rack_slot: rackSlot,
      }),
    });
    reloadWithCurrentState();
  }

  async function handleDelete() {
    const nodeId = document.getElementById("edit-node-id").value;
    if (!window.confirm("Delete this node? This will remove empty descendants too.")) {
      return;
    }
    await fetchJson(`/api/storage/node/${nodeId}`, { method: "DELETE" });
    reloadWithCurrentState();
  }

  async function handleMoveSubmit(event) {
    event.preventDefault();
    if (!moveTargetSelect) {
      return;
    }
    const selectedIds = Array.from(selectedNodeIds);
    if (!selectedIds.length) {
      return;
    }
    const rawValue = moveTargetSelect.value;
    const parentId = rawValue === "__root__" ? null : Number(rawValue);
    const targetLabel = rawValue === "__root__"
      ? "Root"
      : browser.querySelector(`.storage-node[data-node-id="${rawValue}"]`)?.dataset.nodePath || "selected destination";
    if (!window.confirm(`Move ${selectedIds.length} selected item${selectedIds.length === 1 ? "" : "s"} to ${targetLabel}?`)) {
      return;
    }
    await fetchJson("/api/storage/nodes/move", {
      method: "POST",
      body: JSON.stringify({
        node_ids: selectedIds.map((nodeId) => Number(nodeId)),
        parent_id: parentId,
      }),
    });
    reloadWithCurrentState();
  }

  function handleDragStart(event) {
    const node = event.currentTarget.closest(".storage-node[data-node-id]");
    const nodeId = node?.dataset.nodeId || null;
    if (!nodeId) {
      event.preventDefault();
      return;
    }
    if (!selectedNodeIds.has(nodeId)) {
      selectedNodeIds.clear();
      selectedNodeIds.add(nodeId);
      lastSelectedNodeId = nodeId;
      renderSelectionState();
    }
    draggedId = nodeId;
    draggedNodeIds = Array.from(selectedNodeIds);
    draggedNodeIds.forEach((selectedId) => {
      browser.querySelector(`.storage-node[data-node-id="${selectedId}"]`)?.classList.add("is-dragging");
    });
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", draggedNodeIds.join(","));
  }

  function handleDragOver(event) {
    if (!draggedNodeIds.length) return;
    const row = event.currentTarget;
    const targetNode = row.closest(".storage-node[data-node-id]");
    clearRowDropState(row);
    if (isValidDrop(targetNode)) {
      event.preventDefault();
      row.classList.add("drop-valid");
    }
  }

  function handleDragLeave(event) {
    clearRowDropState(event.currentTarget);
  }

  async function handleDrop(event) {
    event.preventDefault();
    const row = event.currentTarget;
    const targetNode = row.closest(".storage-node[data-node-id]");
    clearRowDropState(row);
    if (!isValidDrop(targetNode)) return;
    await fetchJson("/api/storage/nodes/move", {
      method: "POST",
      body: JSON.stringify({
        node_ids: draggedNodeIds.map((nodeId) => Number(nodeId)),
        parent_id: Number(targetNode.dataset.nodeId),
      }),
    });
    reloadWithCurrentState();
  }

  function clearDragState() {
    browser.querySelectorAll(".storage-row").forEach(clearRowDropState);
    browser.querySelectorAll(".storage-node.is-dragging").forEach((node) => node.classList.remove("is-dragging"));
    draggedId = null;
    draggedNodeIds = [];
  }

  function clearRowDropState(row) {
    row.classList.remove("drop-valid");
  }

  function isValidDrop(targetNode) {
    if (!targetNode || !draggedNodeIds.length) return false;
    const targetType = targetNode.dataset.nodeType;
    return draggedNodeIds.every((nodeId) => {
      if (targetNode.dataset.nodeId === nodeId) return false;
      const draggedNode = browser.querySelector(`.storage-node[data-node-id="${nodeId}"]`);
      if (!draggedNode) return false;
      if (draggedNode.querySelector(`.storage-node[data-node-id="${targetNode.dataset.nodeId}"]`)) return false;
      return (allowedChildren[targetType] || []).includes(draggedNode.dataset.nodeType);
    });
  }

  function selectRange(anchorId, targetId, additive) {
    const visibleNodeIds = listVisibleNodeIds();
    const anchorIndex = visibleNodeIds.indexOf(anchorId);
    const targetIndex = visibleNodeIds.indexOf(targetId);
    if (anchorIndex === -1 || targetIndex === -1) {
      selectedNodeIds.clear();
      selectedNodeIds.add(targetId);
      return;
    }
    if (!additive) {
      selectedNodeIds.clear();
    }
    const start = Math.min(anchorIndex, targetIndex);
    const end = Math.max(anchorIndex, targetIndex);
    visibleNodeIds.slice(start, end + 1).forEach((nodeId) => selectedNodeIds.add(nodeId));
  }

  function listVisibleNodeIds() {
    return Array.from(browser.querySelectorAll(".storage-node[data-node-id]"))
      .filter((node) => node.getClientRects().length > 0)
      .map((node) => node.dataset.nodeId)
      .filter(Boolean);
  }

  function renderSelectionState() {
    browser.querySelectorAll(".storage-node[data-node-id]").forEach((node) => {
      node.classList.toggle("storage-node-selected", selectedNodeIds.has(node.dataset.nodeId));
    });
    if (moveSelectedButton) {
      const count = selectedNodeIds.size;
      moveSelectedButton.hidden = count === 0;
      moveSelectedButton.classList.toggle("hidden", count === 0);
      moveSelectedButton.textContent = count > 0 ? `Move selected (${count})` : "Move selected";
      moveSelectedButton.disabled = count === 0;
    }
    if (clearSelectedButton) {
      const count = selectedNodeIds.size;
      clearSelectedButton.hidden = count === 0;
      clearSelectedButton.classList.toggle("hidden", count === 0);
      clearSelectedButton.disabled = count === 0;
    }
  }

  function clearSelection() {
    selectedNodeIds.clear();
    lastSelectedNodeId = null;
    renderSelectionState();
  }

  function selectedNodeDetails() {
    return Array.from(selectedNodeIds)
      .map((nodeId) => browser.querySelector(`.storage-node[data-node-id="${nodeId}"]`))
      .filter(Boolean)
      .map((node) => ({
        id: node.dataset.nodeId,
        type: node.dataset.nodeType,
        name: node.dataset.nodeDisplayName || node.dataset.nodeName || "",
        path: node.dataset.nodePath || node.dataset.nodeDisplayName || "",
      }));
  }

  function summarizeSelection(selectedNodes) {
    if (selectedNodes.length === 1) {
      return `Selected: ${selectedNodes[0].path}`;
    }
    const preview = selectedNodes.slice(0, 3).map((node) => node.name).join(", ");
    const remaining = selectedNodes.length - Math.min(selectedNodes.length, 3);
    return remaining > 0
      ? `Selected ${selectedNodes.length} items: ${preview}, +${remaining} more`
      : `Selected ${selectedNodes.length} items: ${preview}`;
  }

  function buildMoveTargetOptions(selectedNodes) {
    const options = [];
    if (isValidSelectionTarget(null, selectedNodes)) {
      options.push({ value: "__root__", label: "Root" });
    }
    Array.from(browser.querySelectorAll('.storage-node[data-node-id][data-can-accept-children="true"]'))
      .map((node) => ({
        value: node.dataset.nodeId,
        label: node.dataset.nodePath || node.dataset.nodeDisplayName || node.dataset.nodeName || "",
      }))
      .filter((option) => isValidSelectionTarget(option.value, selectedNodes))
      .sort((left, right) => left.label.localeCompare(right.label))
      .forEach((option) => options.push(option));
    return options;
  }

  function isValidSelectionTarget(targetNodeId, selectedNodes) {
    const targetNode = targetNodeId ? browser.querySelector(`.storage-node[data-node-id="${targetNodeId}"]`) : null;
    const targetType = targetNode ? targetNode.dataset.nodeType : "root";
    return selectedNodes.every((selectedNode) => {
      if (targetNodeId && targetNodeId === selectedNode.id) {
        return false;
      }
      if (!(allowedChildren[targetType] || []).includes(selectedNode.type)) {
        return false;
      }
      const selectedNodeElement = browser.querySelector(`.storage-node[data-node-id="${selectedNode.id}"]`);
      if (!selectedNodeElement) {
        return false;
      }
      if (targetNode && selectedNodeElement.querySelector(`.storage-node[data-node-id="${targetNodeId}"]`)) {
        return false;
      }
      return true;
    });
  }

  function numberOrNull(value) {
    if (!value) return null;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function openBulkDialog() {
    bulkDialog?.showModal();
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
    if (bulkRefreshButton) {
      bulkRefreshButton.hidden = true;
      bulkRefreshButton.classList.add("hidden");
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
    if (bulkRefreshButton) {
      bulkRefreshButton.hidden = true;
      bulkRefreshButton.classList.add("hidden");
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
      const response = await fetch("/api/storage/bulk/preview-upload", {
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
    setBulkStatus("Importing boxes...", "info");
    if (bulkCommitButton) {
      bulkCommitButton.disabled = true;
      bulkCommitButton.textContent = "Importing...";
    }
    try {
      const response = await fetch("/api/storage/bulk/commit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          raw_payload: bulkPreviewPayload.raw_payload,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to import workbook");
      }
      renderBulkResult(payload);
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
    if (bulkRefreshButton && Number(result.imported_rows || 0) > 0) {
      bulkRefreshButton.hidden = false;
      bulkRefreshButton.classList.remove("hidden");
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
              <th>Parent</th>
              <th>Box</th>
              <th>Rack Pos.</th>
              <th>Grid</th>
              <th>Status</th>
              <th>Errors</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr class="bulk-row-${escapeHtml(row.status || "invalid")}">
                <td>${escapeHtml(String(row.row_number ?? "--"))}</td>
                <td>${escapeHtml(row.parent || "--")}</td>
                <td>${escapeHtml(row.box || "--")}</td>
                <td>${escapeHtml(row.rack_slot || "--")}</td>
                <td>${escapeHtml(renderGridSummary(row))}</td>
                <td><span class="status-pill">${escapeHtml(row.status || "--")}</span></td>
                <td>${escapeHtml((row.errors || []).join("; ") || "--")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderGridSummary(row) {
    if (!row.rows && !row.cols) {
      return "--";
    }
    return `${row.rows || "--"} x ${row.cols || "--"}`;
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

  function rackSlotFromFields(rowFieldId, colFieldId, mode) {
    const rowField = document.getElementById(rowFieldId);
    const colField = document.getElementById(colFieldId);
    if (!rowField || !colField || rowField.disabled || colField.disabled) return null;
    const row = rowField.value.trim();
    const col = colField.value.trim().toUpperCase();
    if (!row && !col) return null;
    if (!row || !col) {
      window.alert("Enter both rack row and rack column, or leave both blank.");
      return undefined;
    }
    if (!/^[A-Z]+$/.test(col)) {
      window.alert("Rack column must use letters, such as A or C.");
      return undefined;
    }
    const rowNumber = Number(row);
    const colNumber = columnLabelToNumber(col);
    const parentNode = parentRackForDialog(mode);
    const maxRows = Number(parentNode?.dataset.rackLayoutRows || 0);
    const maxCols = Number(parentNode?.dataset.rackLayoutCols || 0);
    if (!Number.isInteger(rowNumber) || rowNumber < 1) {
      window.alert("Rack row must be a whole number greater than zero.");
      return undefined;
    }
    if (maxRows && rowNumber > maxRows) {
      window.alert(`Rack row must be ${maxRows} or less for this rack.`);
      return undefined;
    }
    if (maxCols && colNumber > maxCols) {
      window.alert(`Rack column must fit within ${maxCols} column${maxCols === 1 ? "" : "s"} for this rack.`);
      return undefined;
    }
    return `${col}${row}`;
  }

  function parentRackForDialog(mode) {
    if (mode === "add") {
      const parentId = document.getElementById("add-parent-id")?.value || "";
      return parentId ? browser.querySelector(`.storage-node[data-node-id="${parentId}"]`) : null;
    }
    const nodeId = document.getElementById("edit-node-id")?.value || "";
    const node = nodeId ? browser.querySelector(`.storage-node[data-node-id="${nodeId}"]`) : null;
    const parentId = node?.dataset.parentId || "";
    return parentId ? browser.querySelector(`.storage-node[data-node-id="${parentId}"]`) : null;
  }

  function columnLabelToNumber(label) {
    return label.split("").reduce((total, character) => (total * 26) + character.charCodeAt(0) - 64, 0);
  }

  function columnNumberToLabel(value) {
    let current = value;
    let label = "";
    while (current > 0) {
      const remainder = (current - 1) % 26;
      label = String.fromCharCode(65 + remainder) + label;
      current = Math.floor((current - 1) / 26);
    }
    return label || "A";
  }

  function uppercaseInput(event) {
    const cursor = event.target.selectionStart;
    event.target.value = event.target.value.toUpperCase();
    if (cursor !== null) {
      event.target.setSelectionRange(cursor, cursor);
    }
  }

  function loadCollapsedState(root) {
    try {
      const raw = window.sessionStorage.getItem(storageStateKey);
      if (!raw) {
        return Array.from(root.querySelectorAll(".storage-node[data-node-id]"), (node) => String(node.dataset.nodeId));
      }
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return Array.from(root.querySelectorAll(".storage-node[data-node-id]"), (node) => String(node.dataset.nodeId));
    }
  }

  function saveCollapsedState() {
    window.sessionStorage.setItem(storageStateKey, JSON.stringify([...collapsed]));
  }

  function reloadWithCurrentState() {
    saveCollapsedState();
    window.location.reload();
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
      },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "Request failed" }));
      window.alert(payload.detail || "Request failed");
      throw new Error(payload.detail || "Request failed");
    }
    return response.status === 204 ? null : response.json();
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
