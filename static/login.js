// Job Portal · built by JAI SHARMA
// Spotlight-style sign-in: one field asks for the username, then the same field asks for the password.
const form = document.getElementById("login"), user = document.getElementById("username"), pass = document.getElementById("password");
const field = document.getElementById("spot-field"), msg = document.getElementById("msg"), go = document.getElementById("go");

function step(name) {  // "user" or "pass"
  const toPass = name === "pass";
  user.hidden = toPass;
  pass.hidden = !toPass;
  go.setAttribute("aria-label", toPass ? "Sign in" : "Continue");
  (toPass ? pass : user).focus();
}
function shake(text) {
  msg.textContent = text;
  field.classList.remove("shake");
  void field.offsetWidth;  // restart the animation
  field.classList.add("shake");
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "";
  if (!pass.hidden || pass.value) {
    if (!pass.value) return shake("Type your password");
  } else {
    if (!user.value.trim()) return shake("Type your username");
    return step("pass");
  }
  go.disabled = true;
  try {
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Portal": "1" },
      body: JSON.stringify({ username: user.value.trim(), password: pass.value }),
    });
    if (r.ok) { location.href = "/"; return; }
    pass.value = "";
    shake((await r.json().catch(() => ({}))).detail || "Sign-in failed");
  } catch { shake("Can't reach the portal"); }
  go.disabled = false;
});

// Backspace in an empty password field goes back to the username; Escape too.
pass.addEventListener("keydown", (e) => {
  if ((e.key === "Backspace" && !pass.value) || e.key === "Escape") { e.preventDefault(); msg.textContent = ""; step("user"); }
});
