document.addEventListener("DOMContentLoaded", () => {
  const dataNode = document.getElementById("activity-events-data");
  const feed = document.getElementById("activity-feed");
  const overlay = document.getElementById("activity-detail-overlay");
  const body = document.getElementById("activity-detail-body");
  const title = document.getElementById("activity-detail-title");

  if (!dataNode || !feed) {
    return;
  }

  let events = [];
  try {
    events = JSON.parse(dataNode.textContent || "[]");
  } catch (error) {
    console.error("Failed to parse activity event data.", error);
    return;
  }
  const eventMap = new Map(events.map((event) => [String(event.id), event]));

  feed.querySelectorAll("[data-group-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleGroup(feed, button);
    });
    const isExpanded = button.getAttribute("aria-expanded") === "true";
    syncGroupRows(feed, button.dataset.groupToggle, isExpanded);
  });

  feed.querySelectorAll("[data-event-id]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!overlay || !body || !title) {
        return;
      }
      const event = eventMap.get(button.dataset.eventId);
      if (!event) {
        return;
      }
      try {
        renderDrawerTitle(title, event);
        body.innerHTML = renderDetail(event);
        openDrawer();
      } catch (error) {
        console.error("Failed to render activity detail.", error);
        renderDrawerTitle(title, event);
        body.innerHTML =
          '<div class="activity-detail-notice">This event could not be rendered fully. Stored event data is shown below.</div>' +
          `<details class="activity-raw-payload" open><summary>Stored event data</summary><pre>${escapeHtml(
            JSON.stringify(event.raw_payload || event.payload || {}, null, 2),
          )}</pre></details>`;
        openDrawer();
      }
    });
  });

  if (overlay && body && title) {
    document.querySelectorAll("[data-close-activity-detail]").forEach((element) => {
      element.addEventListener("click", closeDrawer);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !overlay.hidden) {
        closeDrawer();
      }
    });
  }

  function openDrawer() {
    if (!overlay) {
      return;
    }
    overlay.hidden = false;
    overlay.classList.remove("hidden");
    document.body.classList.add("activity-drawer-open");
  }

  function closeDrawer() {
    if (!overlay) {
      return;
    }
    overlay.hidden = true;
    overlay.classList.add("hidden");
    document.body.classList.remove("activity-drawer-open");
  }
});

function renderDetail(event) {
  const parts = [];

  parts.push('<section class="activity-detail-priority">');
  parts.push(`<span class="activity-detail-action">${escapeHtml(event.action_label || event.event_type || "Action")}</span>`);
  if (event.drawer_context_line) {
    parts.push(`<p class="activity-detail-subtitle">${escapeHtml(event.drawer_context_line)}</p>`);
  }
  if (Array.isArray(event.pill_items) && event.pill_items.length) {
    parts.push('<div class="activity-detail-pills">');
    for (const item of event.pill_items) {
      parts.push(
        `<span class="activity-entry-meta-pill"><span class="activity-entry-meta-label">${escapeHtml(item.label)}</span><span class="activity-entry-meta-value">${escapeHtml(item.value)}</span></span>`,
      );
    }
    parts.push("</div>");
  }
  parts.push("</section>");

  if (event.has_legacy_detail_gap) {
    parts.push(
      '<div class="activity-detail-notice">Detailed change tracking was not available when this event was recorded.</div>',
    );
  }

  if (Array.isArray(event.change_items) && event.change_items.length) {
    parts.push('<section class="activity-detail-section"><h3>What changed</h3><div class="activity-change-table">');
    for (const change of event.change_items) {
      parts.push(
        `<div class="activity-change-row"><div class="activity-change-field">${escapeHtml(change.label)}</div><div class="activity-change-before">${escapeHtml(change.before)}</div><div class="activity-change-arrow">&rarr;</div><div class="activity-change-after">${escapeHtml(change.after)}</div></div>`,
      );
    }
    parts.push("</div></section>");
  }

  if (event.metadata_section) {
    parts.push(renderSection(event.metadata_section));
  }

  const visibleSections = Array.isArray(event.detail_sections) ? event.detail_sections : [];
  for (const section of visibleSections) {
    parts.push(renderSection(section));
  }

  const hasRawPayload = Object.keys(event.raw_payload || {}).length > 0;
  if (hasRawPayload) {
    parts.push(
      `<details class="activity-raw-payload"><summary>Stored event data</summary><pre>${escapeHtml(
        JSON.stringify(event.raw_payload || {}, null, 2),
      )}</pre></details>`,
    );
  }

  return parts.join("");
}

function renderDrawerTitle(titleNode, event) {
  const label = event.title || "Activity detail";
  if (event.related_url && event.sample_identifier) {
    titleNode.innerHTML = `<a class="activity-detail-title-link" href="${escapeAttribute(event.related_url)}">${escapeHtml(label)}<span class="activity-detail-title-icon" aria-hidden="true">&#8599;</span></a>`;
    return;
  }
  titleNode.textContent = label;
}

function renderSection(section) {
  if (!section || !Array.isArray(section.items) || !section.items.length) {
    return "";
  }
  if (section.layout === "single_value" || (section.items.length === 1 && !section.items[0].label)) {
    return `<section class="activity-detail-section"><h3>${escapeHtml(section.title || "Details")}</h3><p class="activity-detail-section-value">${escapeHtml(section.items[0].value)}</p></section>`;
  }
  const layoutClass = section.layout === "compact" ? "activity-detail-grid--compact" : "activity-detail-grid--full";
  const parts = [`<section class="activity-detail-section"><h3>${escapeHtml(section.title || "Details")}</h3><div class="activity-detail-grid ${layoutClass}">`];
  for (const item of section.items) {
    parts.push(
      `<div class="activity-detail-grid-item"><div class="activity-detail-grid-term">${escapeHtml(item.label)}</div><div class="activity-detail-grid-value">${escapeHtml(item.value)}</div></div>`,
    );
  }
  parts.push("</div></section>");
  return parts.join("");
}

function appendGroupField(parts, label, value) {
  if (!value || value === "--") {
    return;
  }
  parts.push(
    `<div class="activity-detail-grid-item"><div class="activity-detail-grid-term">${escapeHtml(label)}</div><div class="activity-detail-grid-value">${escapeHtml(value)}</div></div>`,
  );
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}

function toggleGroup(feed, toggle) {
  const groupId = toggle.dataset.groupToggle;
  if (!groupId) {
    return;
  }
  const isExpanded = toggle.getAttribute("aria-expanded") === "true";
  const nextExpanded = !isExpanded;
  toggle.setAttribute("aria-expanded", nextExpanded ? "true" : "false");
  toggle.classList.toggle("activity-entry--expanded", nextExpanded);
  syncGroupRows(feed, groupId, nextExpanded);
}

function syncGroupRows(feed, groupId, isExpanded) {
  feed.querySelectorAll("[data-group-child]").forEach((row) => {
    if (row.dataset.groupChild === groupId) {
      row.hidden = !isExpanded;
    }
  });
}
