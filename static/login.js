// Job Portal · built by JAI SHARMA
// Spotlight-style sign-in: one field asks for the username, then the same field asks for the password.
// The same field creates an account (#signup): email first, then a password.
const $ = (id) => document.getElementById(id);
const form = $("login"), user = $("username"), pass = $("password"), field = $("spot-field"), msg = $("msg"), go = $("go");
let mode = "signin";

function setMode(m) {
  mode = m;
  const up = m === "signup";
  $("title").textContent = up ? "Create your free account" : "Sign in";
  document.title = (up ? "Create account" : "Sign in") + " · SharmaJai Job Portal";
  user.placeholder = up ? "Your email" : "Email or username";
  user.setAttribute("aria-label", user.placeholder);
  user.type = up ? "email" : "text";
  user.autocomplete = up ? "email" : "username";
  pass.placeholder = up ? "Choose a password (8+ characters)" : "Password";
  pass.autocomplete = up ? "new-password" : "current-password";
  $("to-signup").hidden = up;
  $("to-signin").hidden = !up;
  msg.textContent = "";
  pass.value = "";
  step("user");
}
function step(name) {  // "user" or "pass"
  const toPass = name === "pass";
  user.hidden = toPass;
  pass.hidden = !toPass;
  go.setAttribute("aria-label", toPass ? (mode === "signup" ? "Create account" : "Sign in") : "Continue");
  (toPass ? pass : user).focus();
}
function shake(text) {
  msg.textContent = text;
  field.classList.remove("shake");
  void field.offsetWidth;  // restart the animation
  field.classList.add("shake");
}
const looksLikeEmail = (v) => /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "";
  const up = mode === "signup";
  if (!pass.hidden || pass.value) {
    if (!pass.value) return shake(up ? "Choose a password" : "Type your password");
    if (up && pass.value.length < 8) return shake("Use at least 8 characters");
  } else {
    const v = user.value.trim();
    if (!v) return shake(up ? "Type your email" : "Type your email or username");
    if (up && !looksLikeEmail(v)) return shake("That email doesn't look right");
    return step("pass");
  }
  go.disabled = true;
  try {
    const r = await fetch(up ? "/api/signup" : "/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Portal": "1" },
      body: JSON.stringify(up ? { email: user.value.trim(), password: pass.value, website: $("website").value }
                              : { username: user.value.trim(), password: pass.value }),
    });
    if (r.ok) { location.href = "/"; return; }
    pass.value = "";
    const detail = (await r.json().catch(() => ({}))).detail;
    shake(detail || (up ? "Couldn't create the account" : "Sign-in failed"));
    if (up && /email/i.test(detail || "")) step("user");
  } catch { shake("Can't reach the portal"); }
  go.disabled = false;
});

// Backspace in an empty password field goes back to the first step; Escape too.
pass.addEventListener("keydown", (e) => {
  if ((e.key === "Backspace" && !pass.value) || e.key === "Escape") { e.preventDefault(); msg.textContent = ""; step("user"); }
});
$("to-signup").addEventListener("click", (e) => { e.preventDefault(); history.replaceState(null, "", "#signup"); setMode("signup"); });
$("to-signin").addEventListener("click", (e) => { e.preventDefault(); history.replaceState(null, "", "#"); setMode("signin"); });
if (location.hash === "#signup") setMode("signup");
