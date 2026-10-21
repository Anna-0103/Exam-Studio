export default function ({ parentElement, data, setStateValue }) {
  const status = parentElement.querySelector("#vault-status");
  const prefix = "exam-studio:v1:attempt:";
  const send = (event) => setStateValue("event", event);
  const readAll = () => Object.keys(localStorage)
    .filter(k => k.startsWith(prefix))
    .map(k => JSON.parse(localStorage.getItem(k)).attempt)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const fail = (id, message) => {
    status.textContent = message;
    status.style.color = "#9e3f27";
    send({id, type: "error", message});
  };
  if (data.phase === "load") {
    if (status.dataset.loaded === data.session) return;
    status.dataset.loaded = data.session;
    try {
      const attempts = readAll();
      status.textContent = "Saved attempts loaded from this browser.";
      send({id: data.session, type: "loaded", attempts});
    } catch (_) {
      fail(data.session, "Browser saving is unavailable or a saved record is damaged. You can still practise and download a backup.");
    }
    return;
  }
  const operation = data.operation;
  status.textContent = data.status || "Ready to save in this browser.";
  if (!operation || status.dataset.operation === operation.id) return;
  status.dataset.operation = operation.id;
  try {
    const key = prefix + operation.attempt.id;
    const existing = JSON.parse(localStorage.getItem(key) || "null");
    if (existing?.token === operation.id) {
      send({id: operation.id, type: "saved", attempt: existing.attempt});
      return;
    }
    // Do not silently overwrite changes made in another browser tab.
    if (existing && existing.owner !== data.session &&
        existing.attempt.revision !== operation.base_revision) {
      fail(operation.id, "This attempt changed in another tab. Download your current backup before refreshing to load the newer saved copy.");
      return;
    }
    localStorage.setItem(key, JSON.stringify({
      attempt: operation.attempt, token: operation.id, owner: data.session
    }));
    status.textContent = "Saved in this browser · " + new Date().toLocaleTimeString();
    send({id: operation.id, type: "saved", attempt: operation.attempt});
  } catch (_) {
    fail(operation.id, "Could not save in this browser. Storage may be full or disabled. Download a backup to keep this attempt.");
  }
}
