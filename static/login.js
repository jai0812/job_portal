// Job Portal · built by JAI SHARMA
document.getElementById("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("msg"), go = document.getElementById("go");
  msg.textContent = "";
  go.disabled = true;
  try {
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Portal": "1" },
      body: JSON.stringify({ username: document.getElementById("username").value, password: document.getElementById("password").value }),
    });
    if (r.ok) { location.href = "/"; return; }
    msg.textContent = (await r.json().catch(() => ({}))).detail || "Sign-in failed.";
  } catch { msg.textContent = "Can't reach the portal."; }
  go.disabled = false;
});
