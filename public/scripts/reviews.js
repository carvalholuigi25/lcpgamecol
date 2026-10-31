// Reviews and comments in the game details dialog (routes/games/reviews.py), with
// reporting (routes/games/moderation.py). Needs shelf.js loaded first; shelf.js calls
// loadGameDiscussion() when the dialog shows a game or the game's library copy changes.
// Text is written in a Quill editor; the hidden textareas hold its HTML for the forms.

const reviewForm = document.getElementById("review-form");
const reviewFormStatus = document.getElementById("review-form-status");
const reviewDeleteButton = document.getElementById("review-delete");
const reviewsList = document.getElementById("details-reviews-list");
const reviewsStatus = document.getElementById("details-reviews-status");
const commentForm = document.getElementById("comment-form");
const commentFormStatus = document.getElementById("comment-form-status");
const commentsList = document.getElementById("details-comments-list");
const commentsStatus = document.getElementById("details-comments-status");
// The details game the sections belong to (an IGDB id on the releases page).
let discussionGameId = null;
let myReview = null;
// Live updates must not overwrite a review the user is still editing.
let reviewDraft = false;
const DISCUSSION_TOOLBAR = [
  ["bold", "italic", "underline", "strike"],
  [{ list: "ordered" }, { list: "bullet" }],
  ["blockquote", "link"],
  ["clean"],
];
const REPORT_REASONS = { spam: "Spam", offensive: "Offensive", spoilers: "Spoilers", off_topic: "Off topic", other: "Other" };
const hasMarkup = (value) => /<[a-z][\s\S]*>/i.test(value);

// Returns null when Quill could not load; the plain textarea is shown instead.
function initDiscussionEditor(textarea) {
  if (typeof Quill === "undefined") {
    textarea.hidden = false;
    return null;
  }
  const container = document.createElement("div");
  container.className = "discussion-editor";
  container.setAttribute("translate", "no");
  textarea.after(container);
  const editor = new Quill(container, {
    theme: "snow",
    placeholder: window.i18n.t(textarea.placeholder),
    modules: { toolbar: DISCUSSION_TOOLBAR },
  });
  editor.root.setAttribute("aria-labelledby", textarea.getAttribute("aria-labelledby"));
  editor.root.setAttribute("role", "textbox");
  editor.root.setAttribute("aria-multiline", "true");
  editor.on("text-change", () => {
    textarea.value = editor.getText().trim() ? editor.root.innerHTML : "";
  });
  document.addEventListener("languagechange", () => {
    editor.root.dataset.placeholder = window.i18n.t(textarea.placeholder);
  });
  return editor;
}

const reviewEditor = initDiscussionEditor(document.getElementById("review-body"));
const commentEditor = initDiscussionEditor(document.getElementById("comment-body"));

function setDiscussionText(editor, textarea, value) {
  textarea.value = value || "";
  if (!editor) return;
  if (!value) {
    editor.setText("", "silent");
  } else if (hasMarkup(value)) {
    editor.setContents([], "silent");
    editor.clipboard.dangerouslyPasteHTML(0, sanitizeRichText(value), "silent");
  } else {
    editor.setText(value, "silent");
  }
}

function postBody(body) {
  if (!body) return "";
  return hasMarkup(body)
    ? `<div class="discussion-body rich-text" translate="no">${sanitizeRichText(body)}</div>`
    : `<p class="discussion-body" translate="no">${escapeHtml(body)}</p>`;
}

function discussionDate(value) {
  return new Date(value).toLocaleDateString(document.documentElement.lang || "en", { dateStyle: "medium" });
}

function isOwnPost(post) {
  return Boolean(currentProfile) && post.username.toLowerCase() === currentProfile.username.toLowerCase();
}

function starsHtml(rating) {
  const stars = [1, 2, 3, 4, 5]
    .map((star) => `<i class="bi ${star <= rating ? "bi-star-fill" : "bi-star"}" aria-hidden="true"></i>`)
    .join("");
  return `<span class="review-rating" role="img" aria-label="${rating} out of 5" title="${rating} out of 5">${stars}</span>`;
}

// User-written names and text are marked translate="no" so i18n.js leaves them alone.
function postItem(kind, post) {
  const deleteButton = isOwnPost(post) || isAdmin()
    ? `<button class="details-action details-action-danger discussion-delete" type="button" data-delete-kind="${kind}" data-delete-id="${escapeHtml(post.id)}" aria-label="Delete" title="Delete"><i class="bi bi-trash3" aria-hidden="true"></i></button>`
    : "";
  let reportButton = "";
  if (currentProfile && !isOwnPost(post)) {
    reportButton = post.reported
      ? `<span class="discussion-badge" data-status="reported">${escapeHtml(window.i18n.t("Reported"))}</span>`
      : `<button class="details-action discussion-report" type="button" data-report-kind="${kind}" data-report-id="${escapeHtml(post.id)}" aria-label="Report" title="Report"><i class="bi bi-flag" aria-hidden="true"></i></button>`;
  }
  const badges = [];
  if (post.status === "pending") badges.push(["pending", "Waiting for review"]);
  if (post.status === "hidden") badges.push(["hidden", "Hidden"]);
  if (post.open_reports) {
    badges.push(["reported", window.i18n.t(post.open_reports === 1 ? "{count} report" : "{count} reports", { count: post.open_reports })]);
  }
  return `<li class="discussion-item${isOwnPost(post) ? " is-mine" : ""}" data-status="${escapeHtml(post.status || "visible")}">
    <div class="discussion-meta">
      <strong translate="no">${escapeHtml(post.display_name || post.username)}</strong>
      ${post.display_name ? `<span translate="no">@${escapeHtml(post.username)}</span>` : ""}
      ${kind === "reviews" ? starsHtml(post.rating) : ""}
      <time datetime="${escapeHtml(post.updated_at || post.created_at)}" translate="no">${escapeHtml(discussionDate(post.updated_at || post.created_at))}</time>
      ${badges.map(([status, label]) => `<span class="discussion-badge" data-status="${status}">${escapeHtml(window.i18n.t(label))}</span>`).join("")}
      <span class="discussion-tools">${reportButton}${deleteButton}</span>
    </div>
    ${postBody(post.body)}
  </li>`;
}

function fillReviewForm() {
  reviewForm.reset();
  if (myReview) reviewForm.elements.namedItem("rating").value = String(myReview.rating);
  setDiscussionText(reviewEditor, reviewForm.elements.namedItem("body"), myReview?.body);
  reviewForm.querySelector('[type="submit"]').textContent = myReview ? "Update review" : "Post review";
  reviewDeleteButton.hidden = !myReview;
  reviewDraft = false;
}

function activeLibraryId() {
  const game = detailsDialog.open ? activeGame() : null;
  return game ? libraryIdOf(game) : null;
}

async function loadReviews(gameId, libraryId) {
  try {
    const response = await fetch(`/games/${encodeURIComponent(libraryId)}/reviews`, { cache: "no-store" });
    if (!response.ok) throw new Error("Reviews could not be loaded.");
    const result = await response.json();
    if (String(activeDetailsGameId) !== String(gameId)) return;
    myReview = result.mine;
    if (!reviewDraft) fillReviewForm();
    reviewsList.innerHTML = result.items.map((review) => postItem("reviews", review)).join("");
    reviewsStatus.textContent = result.count
      ? window.i18n.t(result.count === 1 ? "{average} out of 5 from {count} review" : "{average} out of 5 from {count} reviews", {
        average: result.average.toLocaleString(document.documentElement.lang || "en"),
        count: result.count,
      })
      : window.i18n.t("No reviews yet.");
  } catch (error) {
    if (String(activeDetailsGameId) !== String(gameId)) return;
    reviewsStatus.textContent = window.i18n.t(error.message);
  }
}

async function loadComments(gameId, libraryId) {
  try {
    const response = await fetch(`/games/${encodeURIComponent(libraryId)}/comments`, { cache: "no-store" });
    if (!response.ok) throw new Error("Comments could not be loaded.");
    const result = await response.json();
    if (String(activeDetailsGameId) !== String(gameId)) return;
    commentsList.innerHTML = result.items.map((comment) => postItem("comments", comment)).join("");
    commentsStatus.textContent = result.count
      ? window.i18n.t(result.count === 1 ? "{count} comment" : "{count} comments", { count: result.count })
      : window.i18n.t("No comments yet.");
  } catch (error) {
    if (String(activeDetailsGameId) !== String(gameId)) return;
    commentsStatus.textContent = window.i18n.t(error.message);
  }
}

function resetCommentForm() {
  commentForm.reset();
  setDiscussionText(commentEditor, commentForm.elements.namedItem("body"), "");
}

function loadGameDiscussion(gameId) {
  if (discussionGameId !== gameId) {
    discussionGameId = gameId;
    myReview = null;
    reviewDraft = false;
    fillReviewForm();
    resetCommentForm();
    reviewFormStatus.textContent = "";
    commentFormStatus.textContent = "";
    reviewsList.replaceChildren();
    commentsList.replaceChildren();
    reviewsStatus.textContent = window.i18n.t("Loading reviews...");
    commentsStatus.textContent = window.i18n.t("Loading comments...");
  }
  reviewForm.hidden = !currentProfile;
  commentForm.hidden = !currentProfile;
  const game = games.find((item) => item.id === gameId);
  const libraryId = game ? libraryIdOf(game) : null;
  if (libraryId === null) {
    // A release that is not in the library yet; posting imports it first.
    myReview = null;
    if (!reviewDraft) fillReviewForm();
    reviewsList.replaceChildren();
    commentsList.replaceChildren();
    reviewsStatus.textContent = window.i18n.t("No reviews yet.");
    commentsStatus.textContent = window.i18n.t("No comments yet.");
    return;
  }
  loadReviews(gameId, libraryId);
  loadComments(gameId, libraryId);
}

async function sendDiscussion(url, method, body, fallback) {
  const response = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(await readActionError(response, fallback));
  return response.status === 204 ? null : response.json();
}

reviewForm.addEventListener("input", () => {
  reviewDraft = true;
});

reviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const game = activeGame();
  if (!game) return;
  const submitButton = reviewForm.querySelector('[type="submit"]');
  const updating = Boolean(myReview);
  const data = new FormData(reviewForm);
  submitButton.disabled = true;
  reviewFormStatus.textContent = "";
  try {
    const libraryId = await ensureLibraryGame(game);
    myReview = await sendDiscussion(
      `/games/${encodeURIComponent(libraryId)}/reviews/mine`,
      "PUT",
      { rating: Number(data.get("rating")), body: data.get("body") },
      "Your review could not be saved.",
    );
    reviewDraft = false;
    if (myReview.status === "pending") {
      reviewFormStatus.textContent = window.i18n.t("Thanks! Your review will show once an administrator approves it.");
    } else {
      reviewFormStatus.textContent = window.i18n.t(updating ? "Your review was updated." : "Thanks for your review!");
    }
    await loadReviews(game.id, libraryId);
  } catch (error) {
    reviewFormStatus.textContent = window.i18n.t(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

async function deletePost(kind, id, button) {
  const libraryId = activeLibraryId();
  if (libraryId === null) return;
  const question = kind === "reviews" ? "Delete this review?" : "Delete this comment?";
  if (!window.confirm(window.i18n.t(question))) return;
  const status = kind === "reviews" ? reviewFormStatus : commentFormStatus;
  button.disabled = true;
  try {
    await sendDiscussion(
      `/games/${encodeURIComponent(libraryId)}/${kind}/${encodeURIComponent(id)}`,
      "DELETE",
      null,
      kind === "reviews" ? "The review could not be deleted." : "The comment could not be deleted.",
    );
    if (kind === "reviews" && String(myReview?.id) === String(id)) {
      myReview = null;
      reviewDraft = false;
    }
    status.textContent = window.i18n.t(kind === "reviews" ? "The review was deleted." : "The comment was deleted.");
    await (kind === "reviews" ? loadReviews : loadComments)(activeDetailsGameId, libraryId);
  } catch (error) {
    status.textContent = window.i18n.t(error.message);
  } finally {
    button.disabled = false;
  }
}

reviewDeleteButton.addEventListener("click", () => {
  if (myReview) deletePost("reviews", myReview.id, reviewDeleteButton);
});

function reportForm(kind, id) {
  const form = document.createElement("form");
  form.className = "report-form";
  form.innerHTML = `
    <label>Why are you reporting this?
      <select name="reason" required>
        ${Object.entries(REPORT_REASONS).map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`).join("")}
      </select>
    </label>
    <input name="details" maxlength="300" placeholder="Details (optional)" aria-label="Details (optional)" />
    <div class="discussion-form-actions">
      <button type="submit">Send report</button>
      <button class="link-button" type="button" data-report-cancel>Cancel</button>
    </div>`;
  const status = kind === "reviews" ? reviewFormStatus : commentFormStatus;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const libraryId = activeLibraryId();
    if (libraryId === null) return;
    const data = new FormData(form);
    form.querySelector('[type="submit"]').disabled = true;
    try {
      await sendDiscussion(
        `/games/${encodeURIComponent(libraryId)}/${kind}/${encodeURIComponent(id)}/report`,
        "POST",
        { reason: data.get("reason"), details: data.get("details") || null },
        "Your report could not be sent.",
      );
      status.textContent = window.i18n.t("Thanks for the report. An administrator will take a look.");
      await (kind === "reviews" ? loadReviews : loadComments)(activeDetailsGameId, libraryId);
    } catch (error) {
      status.textContent = window.i18n.t(error.message);
      form.querySelector('[type="submit"]').disabled = false;
    }
  });
  form.querySelector("[data-report-cancel]").addEventListener("click", () => form.remove());
  return form;
}

for (const list of [reviewsList, commentsList]) {
  list.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-id]");
    if (button) deletePost(button.dataset.deleteKind, button.dataset.deleteId, button);
    const report = event.target.closest("[data-report-id]");
    if (report) {
      const item = report.closest(".discussion-item");
      if (item.querySelector(".report-form")) return;
      const form = reportForm(report.dataset.reportKind, report.dataset.reportId);
      item.append(form);
      form.elements.namedItem("reason").focus();
    }
  });
}

commentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const game = activeGame();
  if (!game) return;
  const submitButton = commentForm.querySelector('[type="submit"]');
  const body = commentForm.elements.namedItem("body").value;
  if (!body.trim()) {
    commentFormStatus.textContent = window.i18n.t("Write a comment before posting it.");
    return;
  }
  submitButton.disabled = true;
  commentFormStatus.textContent = "";
  try {
    const libraryId = await ensureLibraryGame(game);
    const posted = await sendDiscussion(
      `/games/${encodeURIComponent(libraryId)}/comments`,
      "POST",
      { body },
      "Your comment could not be posted.",
    );
    resetCommentForm();
    if (posted.status === "pending") {
      commentFormStatus.textContent = window.i18n.t("Thanks! Your comment will show once an administrator approves it.");
    }
    await loadComments(game.id, libraryId);
  } catch (error) {
    commentFormStatus.textContent = window.i18n.t(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

detailsDialog.addEventListener("close", () => {
  discussionGameId = null;
});

if (window.realtime) {
  window.realtime.on("reviewsChanged", (change) => {
    if (activeLibraryId() === change.game_id) loadReviews(activeDetailsGameId, change.game_id);
  });
  window.realtime.on("commentsChanged", (change) => {
    if (activeLibraryId() === change.game_id) loadComments(activeDetailsGameId, change.game_id);
  });
  window.realtime.onReconnected(() => {
    if (activeLibraryId() !== null) loadGameDiscussion(activeDetailsGameId);
  });
}
