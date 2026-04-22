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
  const moveTargetSelect = document.getElementById("storage-move-target");
  const moveSummary = document.getElementById("storage-move-summary");
  const moveHelp = document.getElementById("storage-move-help");
  const moveSubmitButton = document.getElementById("storage-move-submit");
  const deleteButton = document.getElementById("storage-delete-button");
  const collapsed = new Set(loadCollapsedState(browser));
  const selectedNodeIds = new Set();
  let lastSelectedNodeId = null;
  let draggedId = null;
  let draggedNodeIds = [];

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
    document.getElementById("add-node-type")?.addEventListener("change", toggleBoxDimensions);
    moveSelectedButton?.addEventListener("click", openMoveDialog);
    moveForm?.addEventListener("submit", handleMoveSubmit);
    renderSelectionState();
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

    const parentType = node ? node.dataset.nodeType : "root";
    const types = allowedChildren[parentType] || [];
    parentIdField.value = node ? node.dataset.nodeId : "";
    parentLabelField.value = node ? node.dataset.nodeDisplayName : "Root";
    typeSelect.innerHTML = types.map((type) => `<option value="${type}">${type}</option>`).join("");
    nameField.value = "";
    notesField.value = "";
    document.getElementById("add-box-rows").value = "";
    document.getElementById("add-box-cols").value = "";
    toggleBoxDimensions();
    addDialog.showModal();
  }

  function openEditDialog(node) {
    if (!editDialog || !editForm) return;
    document.getElementById("edit-node-id").value = node.dataset.nodeId;
    document.getElementById("edit-node-type").value = node.dataset.nodeType;
    document.getElementById("edit-node-name").value = node.dataset.nodeName;
    document.getElementById("edit-node-notes").value = node.dataset.nodeNotes || "";
    document.getElementById("edit-node-path").textContent = node.dataset.nodeDisplayName;
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

  function toggleBoxDimensions() {
    const typeSelect = document.getElementById("add-node-type");
    const boxDimensions = document.getElementById("box-dimensions");
    if (!typeSelect || !boxDimensions) return;
    boxDimensions.classList.toggle("hidden", typeSelect.value !== "box");
  }

  async function handleAddSubmit(event) {
    event.preventDefault();
    const payload = {
      name: document.getElementById("add-node-name").value,
      notes: document.getElementById("add-node-notes").value || null,
      node_type: document.getElementById("add-node-type").value,
      parent_id: numberOrNull(document.getElementById("add-parent-id").value),
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
    await fetchJson(`/api/storage/node/${nodeId}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: document.getElementById("edit-node-name").value,
        notes: document.getElementById("edit-node-notes").value || null,
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
