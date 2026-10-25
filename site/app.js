(() => {
  "use strict";

  const cards = Array.from(document.querySelectorAll(".gcard"));
  const filters = Array.from(document.querySelectorAll("[data-filter]"));
  const countEl = document.querySelector("[data-gallery-count]");
  const lightbox = document.querySelector("#lightbox");
  const lightboxImg = document.querySelector("#lightbox-img");
  const lightboxTitle = document.querySelector("#lightbox-title");
  const lightboxMeta = document.querySelector("#lightbox-meta");
  const lightboxLink = document.querySelector("#lightbox-link");
  const closeBtn = document.querySelector("[data-lightbox-close]");
  const prevBtn = document.querySelector("[data-lightbox-prev]");
  const nextBtn = document.querySelector("[data-lightbox-next]");

  let activeFilter = "all";
  let visibleCards = cards.slice();
  let currentIndex = 0;
  let lastFocused = null;

  const filterLabels = {
    all: "全部",
    characters: "角色",
    props: "道具",
    "scenes-916": "場景 9:16",
    "scenes-169": "場景 16:9",
    "shots-916": "鏡頭 9:16",
    "shots-169": "鏡頭 16:9"
  };

  function updateGallery() {
    visibleCards = cards.filter((card) => {
      const show = activeFilter === "all" || card.dataset.group === activeFilter;
      card.hidden = !show;
      return show;
    });

    if (countEl) {
      const label = filterLabels[activeFilter] || "全部";
      countEl.textContent = `${label} · ${visibleCards.length} / ${cards.length}`;
    }
  }

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter || "all";
      filters.forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      closeLightbox();
      updateGallery();
    });
  });

  function openLightbox(card) {
    lastFocused = document.activeElement;
    currentIndex = visibleCards.indexOf(card);
    if (currentIndex < 0) currentIndex = 0;
    renderLightbox();
    lightbox.hidden = false;
    lightbox.setAttribute("aria-hidden", "false");
    document.body.classList.add("lightbox-open");
    closeBtn.focus();
  }

  function renderLightbox() {
    const card = visibleCards[currentIndex];
    if (!card) return;

    const full = card.dataset.full;
    const title = card.dataset.title || "";
    const meta = card.dataset.meta || "";

    lightboxImg.src = full;
    lightboxImg.alt = `${title}，原圖`;
    lightboxTitle.textContent = title;
    lightboxMeta.textContent = meta;
    lightboxLink.href = full;
    lightboxLink.setAttribute("download", "");

    const position = `${String(currentIndex + 1).padStart(2, "0")} / ${String(visibleCards.length).padStart(2, "0")}`;
    const positionEl = document.querySelector("[data-lightbox-position]");
    if (positionEl) positionEl.textContent = position;

    prevBtn.disabled = visibleCards.length < 2;
    nextBtn.disabled = visibleCards.length < 2;
  }

  function closeLightbox() {
    if (lightbox.hidden) return;
    lightbox.hidden = true;
    lightbox.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lightbox-open");
    lightboxImg.removeAttribute("src");
    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
  }

  function stepLightbox(direction) {
    if (visibleCards.length < 2) return;
    currentIndex = (currentIndex + direction + visibleCards.length) % visibleCards.length;
    renderLightbox();
  }

  cards.forEach((card) => {
    card.addEventListener("click", () => openLightbox(card));
  });

  closeBtn.addEventListener("click", closeLightbox);
  prevBtn.addEventListener("click", () => stepLightbox(-1));
  nextBtn.addEventListener("click", () => stepLightbox(1));

  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });

  document.addEventListener("keydown", (event) => {
    if (lightbox.hidden) return;

    if (event.key === "Escape") {
      event.preventDefault();
      closeLightbox();
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepLightbox(-1);
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      stepLightbox(1);
      return;
    }

    if (event.key === "Tab") {
      const focusable = [closeBtn, prevBtn, nextBtn, lightboxLink].filter(
        (element) => element && !element.disabled
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  // Copy-ready document prompts.
  const copyToast = document.querySelector(".copy-toast");
  let toastTimer = null;

  function showToast(message) {
    if (!copyToast) return;
    copyToast.textContent = message;
    copyToast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      copyToast.classList.remove("is-visible");
    }, 1800);
  }

  async function writeClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-9999px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    if (!ok) throw new Error("copy failed");
  }

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    const original = button.textContent;
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;

      try {
        await writeClipboard(target.textContent || "");
        button.textContent = "已複製";
        button.classList.add("is-copied");
        showToast("已複製，可直接貼到 LLM");
        window.setTimeout(() => {
          button.textContent = original;
          button.classList.remove("is-copied");
        }, 1800);
      } catch (error) {
        showToast("複製失敗，請手動選取文字");
      }
    });
  });

  // Printing should include every prompt, even the collapsed ones.
  const promptDetails = Array.from(document.querySelectorAll(".prompt-details"));
  window.addEventListener("beforeprint", () => {
    promptDetails.forEach((details) => {
      details.dataset.wasOpen = details.open ? "1" : "";
      details.open = true;
    });
  });
  window.addEventListener("afterprint", () => {
    promptDetails.forEach((details) => {
      if (!details.dataset.wasOpen) details.open = false;
    });
  });

  // Reveal sections on scroll.
  const revealItems = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.08 }
    );
    revealItems.forEach((item) => revealObserver.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("in"));
  }

  // Active chapter in the top bar.
  const navLinks = Array.from(document.querySelectorAll(".chapters a"));
  const sections = navLinks
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    const navObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        navLinks.forEach((link) => {
          const active = link.getAttribute("href") === `#${visible.target.id}`;
          link.classList.toggle("is-active", active);
          if (active) {
            link.setAttribute("aria-current", "true");
          } else {
            link.removeAttribute("aria-current");
          }
        });
      },
      { rootMargin: "-35% 0px -55% 0px", threshold: [0, 0.2, 0.5] }
    );
    sections.forEach((section) => navObserver.observe(section));
  }

  // Shot list: scene filter, ratio switch, live count.
  const shotCards = Array.from(document.querySelectorAll("[data-shot-cards] .shot-item"));
  const shotRows = Array.from(document.querySelectorAll("[data-shot-rows] tr"));
  const shotCount = document.querySelector("[data-shot-count]");

  function applySceneFilter(scene) {
    let visible = 0;
    shotCards.forEach((card) => {
      const show = scene === "all" || card.dataset.scene === scene;
      card.hidden = !show;
      if (show) {
        visible += 1;
        card.classList.add("in");
      }
    });
    shotRows.forEach((row) => {
      row.hidden = !(scene === "all" || row.dataset.scene === scene);
    });
    if (shotCount) {
      shotCount.textContent = `顯示 ${visible} / ${shotCards.length} 鏡`;
    }
  }

  document.querySelectorAll("[data-scene-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-scene-filter]").forEach((other) => {
        other.classList.toggle("is-active", other === button);
      });
      applySceneFilter(button.dataset.sceneFilter);
    });
  });

  // Visual assets filter (人物)
  const visCards = Array.from(document.querySelectorAll(".asset-grid [data-visual-group]"));
  document.querySelectorAll("[data-visual-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-visual-filter]").forEach((other) => {
        other.classList.toggle("is-active", other === button);
      });
      const group = button.dataset.visualFilter;
      visCards.forEach((card) => {
        card.hidden = !(group === "all" || card.dataset.visualGroup === group);
      });
    });
  });

  // Clip table: scene filter for the 16:9 clip index.
  const clipRows = Array.from(document.querySelectorAll("[data-clip-rows] tbody tr"));

  document.querySelectorAll("[data-clip-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-clip-filter]").forEach((other) => {
        other.classList.toggle("is-active", other === button);
      });
      const scene = button.dataset.clipFilter;
      clipRows.forEach((row) => {
        row.hidden = !(scene === "all" || row.dataset.scene === scene);
      });
    });
  });

  function applyRatio(ratio) {
    const wide = ratio === "169";
    document.querySelectorAll("[data-shot-frame]").forEach((frame) => {
      const portrait = frame.querySelector("[data-shot-img-916]");
      const landscape = frame.querySelector("[data-shot-img-169]");
      const caption = frame.querySelector("[data-shot-cap]");
      if (portrait) portrait.hidden = wide;
      if (landscape) landscape.hidden = !wide;
      if (caption) {
        caption.textContent = wide ? "首幀 · 16:9" : "首幀 · 9:16";
      }
    });
  }

  document.querySelectorAll("[data-ratio]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-ratio]").forEach((other) => {
        other.classList.toggle("is-active", other === button);
      });
      applyRatio(button.dataset.ratio);
    });
  });

  // Print button.
  document.querySelectorAll("[data-print]").forEach((button) => {
    button.addEventListener("click", () => window.print());
  });

  updateGallery();
})();
