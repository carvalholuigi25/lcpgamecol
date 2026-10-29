const accessView = document.getElementById("access-view");
const featuresView = document.getElementById("features-view");
const accountName = document.getElementById("account-name");
const logoutButton = document.getElementById("logout-button");
const uploadForm = document.getElementById("upload-form");
const uploadInput = document.getElementById("upload-input");
const uploadDropzone = document.getElementById("upload-dropzone");
const uploadSelection = document.getElementById("upload-selection");
const uploadProgress = document.getElementById("upload-progress");
const uploadSubmit = document.getElementById("upload-submit");
const uploadClear = document.getElementById("upload-clear");
const uploadStatus = document.getElementById("upload-status");
const uploadRows = document.getElementById("upload-rows");
const toastRegion = document.getElementById("toast-region");
const typeLabels = {
  "image/png": "PNG image",
  "image/jpeg": "JPEG image",
  "image/gif": "GIF image",
  "image/webp": "WebP image",
  "application/pdf": "PDF document",
};
let uploadLimits = { max_bytes: 5 * 1024 * 1024, allowed_types: {} };
let selectedFile = null;
let toastTimer = null;

function showToast(message) {
  toastRegion.textContent = message;
  toastRegion.classList.add("is-visible");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastRegion.classList.remove("is-visible"), 3600);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showAccess(message) {
  featuresView.hidden = true;
  accessView.hidden = false;
  document.getElementById("access-message").textContent = message;
  accountName.textContent = "";
  logoutButton.hidden = true;
  window.adminSidebar?.setAvailable(false);
}

function showFeatures(username, role) {
  accessView.hidden = true;
  featuresView.hidden = false;
  accountName.textContent = username;
  logoutButton.hidden = false;
  window.adminSidebar?.setAvailable(true, role);
}

async function readError(response, fallback) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

// Mirrors the server's signature check so obviously wrong files are caught early.
async function detectFileType(file) {
  const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const startsWith = (...values) => values.every((value, index) => bytes[index] === value);
  const ascii = (start, end) => String.fromCharCode(...bytes.slice(start, end));
  if (startsWith(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return "image/png";
  if (startsWith(0xff, 0xd8, 0xff)) return "image/jpeg";
  if (["GIF87a", "GIF89a"].includes(ascii(0, 6))) return "image/gif";
  if (ascii(0, 4) === "RIFF" && ascii(8, 12) === "WEBP") return "image/webp";
  if (ascii(0, 5) === "%PDF-") return "application/pdf";
  return null;
}

async function fileProblem(file) {
  const extension = file.name.includes(".") ? `.${file.name.split(".").pop().toLowerCase()}` : "";
  const allowedExtensions = Object.values(uploadLimits.allowed_types).flat();
  if (!allowedExtensions.includes(extension)) return "Only PNG, JPEG, GIF, WebP, and PDF files can be uploaded.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > uploadLimits.max_bytes) {
    return window.i18n.t("Files must be {size} or smaller.", { size: formatBytes(uploadLimits.max_bytes) });
  }
  const detectedType = await detectFileType(file);
  if (!detectedType || !uploadLimits.allowed_types[detectedType]?.includes(extension)) {
    return "The file contents do not match an allowed file type.";
  }
  return "";
}

function resetSelection() {
  selectedFile = null;
  uploadForm.reset();
  uploadSelection.hidden = true;
  uploadClear.hidden = true;
  uploadSubmit.disabled = true;
  uploadProgress.hidden = true;
  uploadProgress.value = 0;
}

async function selectFile(file) {
  resetSelection();
  if (!file) return;
  uploadStatus.textContent = "";
  const problem = await fileProblem(file);
  document.getElementById("upload-file-name").textContent = file.name;
  document.getElementById("upload-file-size").textContent = formatBytes(file.size);
  uploadSelection.hidden = false;
  uploadClear.hidden = false;
  if (problem) {
    uploadStatus.textContent = problem;
    return;
  }
  selectedFile = file;
  uploadSubmit.disabled = false;
}

function uploadWithProgress(file) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const body = new FormData();
    body.append("file", file, file.name);
    request.open("POST", "/admin/uploads");
    request.responseType = "json";
    request.setRequestHeader("Accept", "application/json");
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) uploadProgress.value = Math.round((event.loaded / event.total) * 100);
    });
    request.addEventListener("load", () => {
      if (request.status === 201) {
        resolve(request.response);
        return;
      }
      const detail = request.response?.detail;
      reject(new Error(typeof detail === "string" ? detail : "The file could not be uploaded."));
    });
    request.addEventListener("error", () => reject(new Error("The server could not be reached.")));
    request.send(body);
  });
}

function actionLink(label, href, options = {}) {
  const link = document.createElement("a");
  link.className = "secondary-button upload-action";
  link.href = href;
  link.textContent = label;
  if (options.download) link.setAttribute("download", "");
  if (options.newTab) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  return link;
}

function renderUploads(uploads) {
  uploadRows.replaceChildren();
  document.getElementById("upload-empty").hidden = uploads.length > 0;
  document.getElementById("upload-count").textContent = window.i18n.t("{count} FILES", { count: uploads.length });
  const locale = { en: "en-GB", pt: "pt-PT", de: "de-DE", fr: "fr-FR" }[window.i18n.language];

  for (const upload of uploads) {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.className = "recent-title upload-name";
    name.setAttribute("translate", "no");
    name.textContent = upload.original_name;
    name.title = `SHA-256 ${upload.sha256}`;
    const type = document.createElement("td");
    type.textContent = typeLabels[upload.content_type] || upload.content_type;
    const size = document.createElement("td");
    size.textContent = formatBytes(upload.size_bytes);
    const uploaded = document.createElement("td");
    uploaded.textContent = window.i18n.t("{date} by {user}", {
      date: new Date(upload.created_at).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }),
      user: upload.uploaded_by,
    });
    const actions = document.createElement("td");
    actions.className = "upload-actions-cell";
    const fileUrl = `/admin/uploads/${encodeURIComponent(upload.id)}`;
    if (upload.previewable) actions.append(actionLink("Preview", `${fileUrl}?inline=true`, { newTab: true }));
    actions.append(actionLink("Download", fileUrl, { download: true }));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "danger-button upload-action";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => deleteUpload(upload));
    actions.append(deleteButton);
    row.append(name, type, size, uploaded, actions);
    uploadRows.append(row);
  }
}

async function loadUploads() {
  const response = await fetch("/admin/uploads", { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(await readError(response, "Uploaded files could not be loaded."));
  renderUploads(await response.json());
}

async function deleteUpload(upload) {
  if (!window.confirm(window.i18n.t("Delete {name}?", { name: upload.original_name }))) return;
  uploadStatus.textContent = "Deleting file...";
  try {
    const response = await fetch(`/admin/uploads/${encodeURIComponent(upload.id)}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(await readError(response, "The file could not be deleted."));
    showToast("File deleted.");
    uploadStatus.textContent = "";
    await loadUploads();
  } catch (error) {
    uploadStatus.textContent = error.message;
  }
}

uploadInput.addEventListener("change", () => selectFile(uploadInput.files[0]));
uploadClear.addEventListener("click", () => {
  resetSelection();
  uploadStatus.textContent = "";
});
for (const eventName of ["dragenter", "dragover"]) {
  uploadDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadDropzone.classList.add("is-dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  uploadDropzone.addEventListener(eventName, () => uploadDropzone.classList.remove("is-dragging"));
}
uploadDropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  const files = event.dataTransfer?.files;
  if (!files?.length) return;
  if (files.length > 1) {
    uploadStatus.textContent = "Upload one file at a time.";
    return;
  }
  selectFile(files[0]);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) return;
  uploadSubmit.disabled = true;
  uploadClear.disabled = true;
  uploadProgress.hidden = false;
  uploadProgress.value = 0;
  uploadStatus.textContent = "Uploading file...";
  window.setStatusLoading(uploadStatus, true);
  try {
    const saved = await uploadWithProgress(selectedFile);
    resetSelection();
    uploadStatus.textContent = "";
    showToast(window.i18n.t("{name} uploaded.", { name: saved.original_name }));
    await loadUploads();
  } catch (error) {
    uploadStatus.textContent = error.message;
    uploadSubmit.disabled = !selectedFile;
  } finally {
    window.setStatusLoading(uploadStatus, false);
    uploadClear.disabled = false;
  }
});

logoutButton.addEventListener("click", async () => {
  try {
    await fetch("/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/admin");
  }
});

async function initSpecialFeatures() {
  try {
    const profileResponse = await fetch("/users");
    if (!profileResponse.ok) {
      showAccess("Sign in with an administrator account to use special features.");
      return;
    }
    const profile = await profileResponse.json();
    const limitsResponse = await fetch("/admin/uploads/limits");
    if (limitsResponse.status === 403) {
      showAccess("This account does not have administrator access.");
      return;
    }
    if (!limitsResponse.ok) throw new Error(await readError(limitsResponse, "Upload settings could not be loaded."));
    uploadLimits = await limitsResponse.json();
    document.getElementById("upload-rules").textContent = window.i18n.t(
      "PNG, JPEG, GIF, WebP, or PDF up to {size}",
      { size: formatBytes(uploadLimits.max_bytes) },
    );
    showFeatures(profile.username, profile.role);
    await loadUploads();
  } catch (error) {
    if (featuresView.hidden) showAccess("The server could not be reached.");
    else uploadStatus.textContent = error.message;
  }
}

initSpecialFeatures();
