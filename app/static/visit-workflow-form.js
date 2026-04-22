(() => {
  const list = document.getElementById("quick-link-list");
  const addButton = document.getElementById("add-quick-link");
  if (!list || !addButton) {
    return;
  }

  addButton.addEventListener("click", () => {
    list.insertAdjacentHTML(
      "beforeend",
      `
        <div class="workflow-link-row">
          <label>Title
            <input type="text" name="quick_link_label" value="" />
          </label>
          <label>URL
            <input type="url" name="quick_link_url" value="" />
          </label>
          <button type="button" class="ghost-button workflow-link-remove">Remove</button>
        </div>
      `
    );
    syncRemoveButtons();
  });

  list.addEventListener("click", (event) => {
    const button = event.target.closest(".workflow-link-remove");
    if (!button) {
      return;
    }
    const row = button.closest(".workflow-link-row");
    if (!row) {
      return;
    }
    row.remove();
    if (!list.children.length) {
      addButton.click();
    }
    syncRemoveButtons();
  });

  syncRemoveButtons();

  function syncRemoveButtons() {
    const rows = Array.from(list.querySelectorAll(".workflow-link-row"));
    rows.forEach((row) => {
      const button = row.querySelector(".workflow-link-remove");
      if (button) {
        button.disabled = rows.length === 1;
      }
    });
  }
})();
