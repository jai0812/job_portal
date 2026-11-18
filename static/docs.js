// Job Portal · built by JAI SHARMA
// Documentation: live totals, the contents list follows your place on the page, and folds away on phones.
(() => {
  const $$ = (s) => [...document.querySelectorAll(s)];
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");

  // live totals (the same feed as the home page's board)
  fetch("/api/public/board").then((r) => r.json()).then(({ stats: s = {} }) => {
    const set = (k, v) => $$(`[data-stat="${k}"]`).forEach((el) => (el.textContent = v));
    if (s.total) set("total", fmt(s.total));
    if (s.career_sites) set("career_sites", fmt(s.career_sites));
    if (s.github_lists) set("github_lists", fmt(s.github_lists));
    if (s.last_fetch) {
      const m = Math.max(1, Math.round((Date.now() / 1000 - s.last_fetch) / 60));
      document.getElementById("last-check").textContent = m < 120 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
    }
  }).catch(() => {});

  // contents: highlight the section you're reading
  const links = new Map($$(".toc a").map((a) => [a.getAttribute("href").slice(1), a]));
  const sections = $$(".doc section[id]");
  const mark = (id) => links.forEach((a, k) => (k === id ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current")));
  const spy = () => {
    let current = sections[0] && sections[0].id;
    for (const s of sections) if (s.getBoundingClientRect().top < 140) current = s.id;
    mark(current);
  };
  addEventListener("scroll", spy, { passive: true });
  spy();

  // phones: the contents fold into a button
  const toc = document.getElementById("toc"), btn = document.getElementById("toc-toggle");
  btn.addEventListener("click", () => {
    const open = toc.classList.toggle("open");
    btn.setAttribute("aria-expanded", String(open));
  });
  links.forEach((a) => a.addEventListener("click", () => { toc.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); }));
})();
