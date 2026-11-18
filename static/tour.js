// Job Portal · built by JAI SHARMA
// The laptop tour (home page and docs): real screenshots cross-fade inside a laptop, a pointer moves to what each
// step clicks, and the step list beside it follows along. Plays when it scrolls into view; clicking a step stops it.
(() => {
  const laptop = document.querySelector("[data-tour]");
  if (!laptop) return;
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const shots = [...laptop.querySelectorAll(".screen img")];
  const steps = [...document.querySelectorAll(laptop.dataset.tour + " button")];
  const cur = laptop.querySelector(".cursor"), tap = laptop.querySelector(".tap");
  // Where the pointer goes on each screenshot (percent of the screen) before it "clicks".
  const POINTS = [[20, 3], [18, 32], [64, 16], [7, 31], [80, 3]];
  const STEP_MS = 4200;
  let step = 0, timer = null, seen = false;
  laptop.style.setProperty("--step-ms", STEP_MS + "ms");
  steps.forEach((b) => b.style.setProperty("--step-ms", STEP_MS + "ms"));
  function go(n, auto = true) {
    step = (n + shots.length) % shots.length;
    shots.forEach((img, i) => img.classList.toggle("on", i === step));
    steps.forEach((b, i) => {
      if (i === step) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
      const bar = b.querySelector(".bar i");
      bar.classList.remove("run"); void bar.offsetWidth;
      if (i === step && auto && !calm) bar.classList.add("run");
    });
    const [x, y] = POINTS[step] || [50, 50];
    cur.style.left = x + "%"; cur.style.top = y + "%";
    if (!calm) setTimeout(() => { tap.style.left = x + "%"; tap.style.top = y + "%"; tap.classList.remove("go"); void tap.offsetWidth; tap.classList.add("go"); }, 950);
  }
  const play = () => { clearInterval(timer); timer = calm ? null : setInterval(() => go(step + 1), STEP_MS); };
  const stop = () => { clearInterval(timer); timer = null; };
  steps.forEach((b, i) => b.addEventListener("click", () => { go(i, false); stop(); seen = "manual"; }));
  new IntersectionObserver(([e]) => {
    if (!e.isIntersecting) return stop();
    if (!seen) { seen = true; go(0); play(); } else if (seen === true && !timer) play();
  }, { threshold: 0.35 }).observe(laptop);
  go(0, false);
})();
