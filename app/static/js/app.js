(function () {
  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async function () {
      await fetch("/api/v1/auth/logout", { method: "POST" });
      window.location.href = "/";
    });
  }

  document.querySelectorAll("[data-tutorial]").forEach(function (root) {
    const steps = Array.from(root.querySelectorAll("[data-step]"));
    const shots = Array.from(root.querySelectorAll("[data-shot]"));
    if (!steps.length) return;
    let i = 0;
    let paused = false;

    function show(n) {
      i = n % steps.length;
      steps.forEach((el, idx) => el.classList.toggle("is-on", idx === i));
      shots.forEach((el, idx) => el.classList.toggle("hidden", idx !== i));
    }

    steps.forEach((el, idx) => {
      el.addEventListener("click", function () {
        show(idx);
      });
    });

    root.addEventListener("mouseenter", function () { paused = true; });
    root.addEventListener("mouseleave", function () { paused = false; });
    root.addEventListener("focusin", function () { paused = true; });
    root.addEventListener("focusout", function () { paused = false; });

    show(0);
    setInterval(function () {
      if (!paused) show(i + 1);
    }, 3000);
  });
})();
