"use strict";
const errorBox = document.getElementById("login-error");
async function submit(path, data) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result;
}
document
  .getElementById("login-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("d-none");
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const setup = form.dataset.setup === "true";
    try {
      const result = await submit(
        `/api/v1/auth/${setup ? "setup" : "login"}`,
        data,
      );
      if (result.mfa_required) {
        form.classList.add("d-none");
        document.getElementById("mfa-form").classList.remove("d-none");
        document.getElementById("code").focus();
      } else location.assign("/");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("d-none");
    }
  });
document
  .getElementById("mfa-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await submit(
        "/api/v1/auth/mfa/verify",
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      location.assign("/");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("d-none");
    }
  });
document.querySelectorAll(".language").forEach((button) =>
  button.addEventListener("click", () => {
    document.cookie = `apm_language=${button.dataset.language}; Path=/; SameSite=Strict`;
    location.reload();
  }),
);
if (new URLSearchParams(location.search).get("mfa") === "1") {
  document.getElementById("login-form").classList.add("d-none");
  document.getElementById("mfa-form").classList.remove("d-none");
  document.getElementById("code").focus();
}
