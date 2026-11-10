const statusMessage = document.getElementById("permissions-status");
const usersContainer = document.getElementById("permissions-users");
const accountName = document.getElementById("account-name");

function showError(message) {
  statusMessage.textContent = message;
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "The request could not be completed.");
  }
  return response.json();
}

function renderUser(user, permissions) {
  const card = document.createElement("section");
  card.className = "permissions-user";
  const heading = document.createElement("div");
  heading.className = "permissions-user-heading";
  const title = document.createElement("h2");
  title.textContent = user.username;
  const role = document.createElement("span");
  role.className = "role-badge";
  role.textContent = user.role;
  heading.append(title, role);
  if (user.role === "admin") {
    const note = document.createElement("p");
    note.className = "permissions-note";
    note.textContent = "Administrators already have all permissions.";
    card.append(heading, note);
    return card;
  }

  const form = document.createElement("form");
  form.className = "permissions-form";
  for (const permission of permissions) {
    const label = document.createElement("label");
    label.className = "permissions-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "permission";
    checkbox.value = permission.key;
    checkbox.checked = user.permissions.includes(permission.key);
    const description = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = permission.label;
    const detail = document.createElement("small");
    detail.textContent = permission.description;
    description.append(name, detail);
    label.append(checkbox, description);
    form.append(label);
  }
  const actions = document.createElement("div");
  actions.className = "permissions-actions";
  const save = document.createElement("button");
  save.className = "primary-button";
  save.type = "submit";
  save.textContent = "Save permissions";
  actions.append(save);
  form.append(actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    statusMessage.textContent = "";
    try {
      await requestJson(`/admin/permissions/api/${encodeURIComponent(user.username)}`, {
        method: "PUT",
        body: JSON.stringify({
          permissions: [...form.querySelectorAll('input[name="permission"]:checked')].map((input) => input.value),
        }),
      });
      statusMessage.textContent = `Permissions saved for ${user.username}.`;
    } catch (error) {
      showError(error.message);
    } finally {
      save.disabled = false;
    }
  });
  card.append(heading, form);
  return card;
}

async function loadPermissions() {
  statusMessage.textContent = "Loading accounts…";
  try {
    const result = await requestJson("/admin/permissions/api");
    usersContainer.replaceChildren(...result.users.map((user) => renderUser(user, result.permissions)));
    accountName.textContent = "Administrator";
    window.adminSidebar?.setAvailable(true, "admin");
    statusMessage.textContent = result.users.length ? "" : "No accounts are available.";
  } catch (error) {
    window.adminSidebar?.setAvailable(false);
    showError(error.message);
  }
}

loadPermissions();
