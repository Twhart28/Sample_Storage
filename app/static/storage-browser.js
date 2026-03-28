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
  const deleteButton = document.getElementById("storage-delete-button");
  const collapsed = new Set(loadCollapsedState(browser));
  let draggedId = null;

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
    const nicknameField = document.getElementById("add-node-nickname");
    const notesField = document.getElementById("add-node-notes");

    const parentType = node ? node.dataset.nodeType : "root";
    const types = allowedChildren[parentType] || [];
    parentIdField.value = node ? node.dataset.nodeId : "";
    parentLabelField.value = node ? node.dataset.nodeDisplayName : "Root";
    typeSelect.innerHTML = types.map((type) => `<option value="${type}">${type}</option>`).join("");
    nameField.value = "";
    nicknameField.value = "";
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
    document.getElementById("edit-node-nickname").value = node.dataset.nodeNickname || "";
    document.getElementById("edit-node-notes").value = node.dataset.nodeNotes || "";
    document.getElementById("edit-node-path").textContent = node.dataset.nodeDisplayName;
    editDialog.showModal();
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
      nickname: document.getElementById("add-node-nickname").value || null,
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
        nickname: document.getElementById("edit-node-nickname").value || null,
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

  function handleDragStart(event) {
    const node = event.currentTarget.closest(".storage-node");
    draggedId = node?.dataset.nodeId || null;
    node?.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
  }

  function handleDragOver(event) {
    if (!draggedId) return;
    const row = event.currentTarget;
    const targetNode = row.closest(".storage-node");
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
    const targetNode = row.closest(".storage-node");
    clearRowDropState(row);
    if (!isValidDrop(targetNode)) return;
    await fetchJson(`/api/storage/node/${draggedId}/move`, {
      method: "POST",
      body: JSON.stringify({ parent_id: Number(targetNode.dataset.nodeId) }),
    });
    reloadWithCurrentState();
  }

  function clearDragState() {
    browser.querySelectorAll(".storage-row").forEach(clearRowDropState);
    browser.querySelectorAll(".storage-node.is-dragging").forEach((node) => node.classList.remove("is-dragging"));
    draggedId = null;
  }

  function clearRowDropState(row) {
    row.classList.remove("drop-valid");
  }

  function isValidDrop(targetNode) {
    if (!targetNode || !draggedId) return false;
    if (targetNode.dataset.nodeId === draggedId) return false;
    if (targetNode.querySelector(`[data-node-id="${draggedId}"]`)) return false;
    const draggedNode = browser.querySelector(`[data-node-id="${draggedId}"]`);
    if (!draggedNode) return false;
    const draggedType = draggedNode.dataset.nodeType;
    const targetType = targetNode.dataset.nodeType;
    return (allowedChildren[targetType] || []).includes(draggedType);
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
})();
