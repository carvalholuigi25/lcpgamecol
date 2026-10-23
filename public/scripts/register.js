// Account registration shared by the admin and library sign-in panels.
// The checks here mirror the server's password policy so people get feedback
// while typing; the server still validates every request.
const passwordMinLength = 12;
const usernamePattern = /^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$/;
const strengthLabels = ["Too weak", "Weak", "Fair", "Good", "Strong"];

function registrationPasswordProblem(password, username) {
  if (password.length < passwordMinLength) return `Use at least ${passwordMinLength} characters.`;
  if (password.length > 128) return "Use 128 characters or fewer.";
  if (password !== password.trim()) return "The password must not start or end with spaces.";
  if (username && password.toLowerCase().includes(username.toLowerCase())) {
    return "The password must not contain the username.";
  }
  if (new Set(password.toLowerCase()).size < 5) return "This password is too common or predictable.";
  if (!/\p{L}/u.test(password) || !/[^\p{L}]/u.test(password)) {
    return "Mix letters with numbers, spaces, or symbols.";
  }
  return "";
}

function passwordStrength(password, username) {
  if (!password) return 0;
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z\d]/].filter((pattern) => pattern.test(password)).length;
  let score = 1;
  if (password.length >= passwordMinLength) score += 1;
  if (password.length >= 16) score += 1;
  if (classes >= 3 || password.length >= 20) score += 1;
  if (registrationPasswordProblem(password, username)) score = Math.min(score, 1);
  return Math.min(score, 4);
}

window.initRegistration = ({ loginForm, registerForm, switchButton, onRegistered }) => {
  if (!loginForm || !registerForm || !switchButton) return;
  const status = registerForm.parentElement.querySelector("[data-register-status]");
  const meter = registerForm.querySelector("[data-password-meter]");
  const strengthLabel = registerForm.querySelector("[data-password-strength]");
  const usernameField = registerForm.elements.namedItem("username");
  const passwordField = registerForm.elements.namedItem("password");
  const confirmField = registerForm.elements.namedItem("confirm_password");
  const loginExtras = [...loginForm.parentElement.querySelectorAll("[data-login-only]")];

  function showRegister(visible, focus = true) {
    registerForm.hidden = !visible;
    loginForm.hidden = visible;
    for (const element of loginExtras) element.hidden = visible;
    if (status) status.textContent = "";
    switchButton.textContent = visible ? "Already have an account? Sign in" : "New here? Create an account";
    if (focus) (visible ? usernameField : loginForm.querySelector("input"))?.focus();
  }

  function validate() {
    const username = usernameField.value.trim();
    const password = passwordField.value;
    usernameField.setCustomValidity(
      username && !usernamePattern.test(username)
        ? window.i18n.t("Use 3 to 32 letters, numbers, dots, hyphens, or underscores, starting with a letter or number.")
        : "",
    );
    // Validity messages are shown by the browser, outside the DOM that i18n.js translates.
    passwordField.setCustomValidity(password ? window.i18n.t(registrationPasswordProblem(password, username)) : "");
    confirmField.setCustomValidity(
      confirmField.value && confirmField.value !== password ? window.i18n.t("The passwords do not match.") : "",
    );

    const score = passwordStrength(password, username);
    if (meter) meter.value = score;
    if (strengthLabel) {
      strengthLabel.textContent = password
        ? window.i18n.t("Strength: {label}", { label: window.i18n.t(strengthLabels[score]) })
        : "";
    }
  }

  switchButton.addEventListener("click", () => showRegister(registerForm.hidden));
  registerForm.addEventListener("input", validate);
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    validate();
    if (!registerForm.reportValidity()) return;

    const submitButton = registerForm.querySelector('[type="submit"]');
    const username = usernameField.value.trim();
    const password = passwordField.value;
    submitButton.disabled = true;
    status.textContent = "Creating account...";
    window.setStatusLoading(status, true);
    try {
      const response = await fetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        let message = "The account could not be created.";
        try {
          const body = await response.json();
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // Keep the fallback message when the server returns no JSON body.
        }
        status.textContent = message;
        return;
      }
      registerForm.reset();
      validate();
      showRegister(false, false);
      await onRegistered?.(username, password);
    } catch {
      status.textContent = "The server could not be reached.";
    } finally {
      window.setStatusLoading(status, false);
      submitButton.disabled = false;
    }
  });

  showRegister(false, false);
};
