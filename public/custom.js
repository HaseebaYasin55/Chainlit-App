console.log("%c[imagineAI custom.js] file loaded and running \u2014 build 2026-08-08i (removed conflicting hero centering hack, fixed in custom.css instead)", "color:#F80061;font-weight:bold;font-size:14px;");

/**
 * imagineAI — UI cleanup script
 * -----------------------------
 * Chainlit does not (as of this writing) expose a config.toml flag that
 * fully removes the README/help button or the theme-toggle button from
 * the DOM (see github.com/Chainlit/chainlit/issues/2286 and #1805) — the
 * documented workarounds only hide them with CSS. To satisfy "removed,
 * not just hidden", this script actually deletes those nodes from the
 * page whenever Chainlit (re)renders its header, on top of the CSS rules
 * in custom.css which act as an instant first line of defense.
 */
(function () {
  "use strict";

  // Lucide icon components render as <svg class="lucide lucide-sun">, etc.
  // Chainlit's header icons (theme toggle, readme/help) are almost always
  // one of these shapes even when the button itself has no aria-label.
  const ICON_NAME_PATTERN =
  /lucide-(sun|moon|moon-star|book|book-open|book-open-text|help-circle|circle-help|life-buoy|info)/i;

  const NEW_CHAT_ICON_PATTERN =
  /lucide-(square-pen|pencil|file-pen-line|notebook-pen)/i;

  function svgIconMatches(el) {
    const svg = el.querySelector ? el.querySelector("svg") : null;
    if (!svg) return false;
    const cls = (svg.getAttribute("class") || "") + " " + (svg.className && svg.className.baseVal || "");
    return ICON_NAME_PATTERN.test(cls);
  }

  function looksLikeReadmeOrThemeButton(el) {
    const label = (
     (el.getAttribute &&
       (el.getAttribute("aria-label") || el.getAttribute("title"))) ||
    ""
  ).toLowerCase();

  // Remove README / Help
    if (
       /readme|help|documentation/.test(label)
  ) {
     return true;
  }

  // Remove theme / mode switch
    if (
      /dark mode|light mode|^theme$|toggle theme|switch theme/.test(label)
  ) {
      return true;
  }

  // Remove New Chat / Compose button
    if (
     /new chat|new conversation|compose/.test(label)
  ) {
    return true;
  }

    if (el.id && /readme|theme-toggle|new-chat/i.test(el.id)) {
     return true;
  }

    if (el.dataset) {
     const testId = el.dataset.testid || "";

    if (/readme|theme|new-chat|newchat/i.test(testId)) {
      return true;
    }
  }

  // README / theme icons
    if (!label && svgIconMatches(el)) {
     return true;
  }

  // Left pencil/new-chat icon
    const svg = el.querySelector ? el.querySelector("svg") : null;

    if (svg) {
     const cls =
      (svg.getAttribute("class") || "") +
      " " +
      ((svg.className && svg.className.baseVal) || "");

    if (NEW_CHAT_ICON_PATTERN.test(cls)) {
      return true;
    }
  }

  return false;
}

  function looksLikeBrandingImage(el) {
    const src = (el.getAttribute && el.getAttribute("src")) || "";
    const alt = ((el.getAttribute && el.getAttribute("alt")) || "").toLowerCase();
    return /logo|chainlit/i.test(src) || /logo|chainlit/i.test(alt);
  }

  function cleanup() {
    // README/help + theme toggle: search the whole top bar area, not just
    // <header>/<nav>, since Chainlit may wrap it in a plain <div>.
    document
      .querySelectorAll(
        "header button, nav button, [class*='header' i] button, [class*='navbar' i] button, [class*='topbar' i] button, [class*='top-bar' i] button, body > div > div:first-child button"
      )
      .forEach((btn) => {
        if (looksLikeReadmeOrThemeButton(btn)) {
          btn.remove();
        }
      });

    // Any stray Chainlit logo / branding images.
    document.querySelectorAll("img").forEach((img) => {
      if (looksLikeBrandingImage(img)) {
        img.remove();
      }
    });
  }

  // Run once immediately, then keep watching, since Chainlit is a
  // client-rendered SPA that (re)builds the header after our script loads.
  cleanup();
  const observer = new MutationObserver(() => cleanup());
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();

/**
 * imagineAI — download button for generated images
 * --------------------------------------------------
 * Chainlit's image action row only exposes copy / thumbs-up / thumbs-down
 * icon buttons, not a download button. This finds that row per generated
 * image using several independent heuristics (icon name, aria-label/title
 * text, and a structural fallback), since no single one of these is
 * guaranteed to match across Chainlit versions/builds. It logs what it
 * finds to the console (prefixed "[imagineAI download-btn]") so it's
 * possible to see exactly why a button was or wasn't added, by opening
 * DevTools after a generated image appears.
 */
(function () {
  "use strict";

  const ICON_PATTERN = /lucide-(copy|thumbs-up|thumbs-down)/i;
  const LABEL_PATTERN =
    /copy|thumb|like|dislike|good response|bad response|feedback|upvote|downvote/i;

  function svgClasses(svg) {
    return (
      (svg.getAttribute("class") || "") +
      " " +
      ((svg.className && svg.className.baseVal) || "")
    );
  }

  function buttonLabel(btn) {
    return (
      (btn.getAttribute("aria-label") ||
        btn.getAttribute("title") ||
        btn.dataset.testid ||
        "") + ""
    );
  }

  function isActionButton(btn) {
    if (LABEL_PATTERN.test(buttonLabel(btn))) return true;
    const svg = btn.querySelector("svg[class*='lucide' i]");
    return !!svg && ICON_PATTERN.test(svgClasses(svg));
  }

  // Strategy 1: any parent element whose buttons include at least one
  // recognizable copy/thumbs action button.
  function findToolbarsByRecognizedButtons() {
    const toolbars = new Set();
    document.querySelectorAll("button").forEach((btn) => {
      if (!isActionButton(btn)) return;
      if (btn.parentElement) toolbars.add(btn.parentElement);
    });
    return toolbars;
  }

  // Strategy 2 (fallback): within a message that contains an image, the
  // "toolbar" is whichever parent element holds the most sibling buttons
  // -- action rows are reliably a cluster of 2+ buttons sharing one
  // parent, which nothing else in a message typically looks like.
  function findToolbarByButtonCluster(container) {
    const buttons = Array.from(container.querySelectorAll("button"));
    if (buttons.length === 0) return null;
    const counts = new Map();
    buttons.forEach((btn) => {
      const parent = btn.parentElement;
      if (!parent) return;
      counts.set(parent, (counts.get(parent) || 0) + 1);
    });
    let best = null;
    let bestCount = 0;
    counts.forEach((count, parent) => {
      if (count > bestCount) {
        bestCount = count;
        best = parent;
      }
    });
    return bestCount >= 2 ? best : null;
  }

  function findImageMessages() {
    return Array.from(document.querySelectorAll("img"))
      .map((img) => ({
        img,
        container: img.closest("[data-testid='message'], .step"),
      }))
      .filter((entry) => entry.container);
  }

  function buildDownloadButton(sampleBtn, img) {
    const downloadBtn = sampleBtn.cloneNode(true);
    downloadBtn.classList.add("imagineai-download-btn");
    downloadBtn.removeAttribute("aria-pressed");
    downloadBtn.setAttribute("aria-label", "Download image");
    downloadBtn.setAttribute("title", "Download image");

    const downloadIconSvg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-download"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';

    const existingSvg = downloadBtn.querySelector("svg");
    if (existingSvg) {
      existingSvg.outerHTML = downloadIconSvg;
    } else {
      downloadBtn.innerHTML = downloadIconSvg;
    }

    downloadBtn.onclick = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const filename =
        (img.alt || "image").replace(/[^a-zA-Z0-9]+/g, "_") + ".png";
      try {
        // Fetch-as-blob downloads immediately even when img.src is a
        // cross-origin or otherwise non-trivial URL, unlike a plain
        // <a download> link which browsers can silently just navigate to.
        const response = await fetch(img.src);
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(blobUrl);
      } catch (err) {
        // Fallback for same-origin URLs if the fetch above is blocked.
        const link = document.createElement("a");
        link.href = img.src;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
    };

    return downloadBtn;
  }

  function addDownloadButtons() {
    const recognizedToolbars = findToolbarsByRecognizedButtons();
    const imageMessages = findImageMessages();

    imageMessages.forEach(({ img, container }) => {
      if (container.querySelector(".imagineai-download-btn")) return;

      let toolbar = Array.from(recognizedToolbars).find((t) =>
        container.contains(t)
      );
      let strategy = "recognized-button";

      if (!toolbar) {
        toolbar = findToolbarByButtonCluster(container);
        strategy = "button-cluster";
      }

      if (!toolbar) {
        console.warn(
          "[imagineAI download-btn] no toolbar found for image:",
          (img.src || "").slice(0, 60)
        );
        return;
      }

      const sampleBtn = toolbar.querySelector("button");
      if (!sampleBtn) {
        console.warn(
          "[imagineAI download-btn] toolbar found but has no button to clone",
          toolbar
        );
        return;
      }

      toolbar.appendChild(buildDownloadButton(sampleBtn, img));
      console.log(
        `[imagineAI download-btn] added via "${strategy}" strategy`,
        toolbar
      );
    });
  }

  addDownloadButtons();
  new MutationObserver(addDownloadButtons).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
/**
 * imagineAI — force robot image above the "imagineAI" heading
 * -------------------------------------------------------------
 * Earlier attempts used CSS flexbox `order`, which assumes the image and
 * heading are direct flex-item siblings under a flex container -- an
 * assumption about Chainlit's internal DOM that didn't hold (or the
 * browser's :has() support wasn't cooperating). This does it directly in
 * the DOM instead: find the actual <img> and heading elements, find their
 * lowest common ancestor, and physically move the image's branch to
 * before the heading's branch. Works regardless of the exact nesting
 * Chainlit uses, and re-runs on every re-render via MutationObserver.
 */
(function () {
  "use strict";

  function getHeroContainer() {
    return document.querySelector(
      '.step:first-of-type, [data-testid="message"]:first-of-type'
    );
  }

  function getHeroImg(container) {
    // The robot element is created with name="imagineAI" in app.py, so
    // Chainlit should render it with a matching alt attribute. Fall back
    // to "first img inside the hero container" if that assumption is off.
    return (
      document.querySelector('img[alt="imagineAI" i]') ||
      (container && container.querySelector("img")) ||
      document.querySelector("img")
    );
  }

  function getHeroHeading(container) {
    if (container) {
      const h = container.querySelector("h1, h2, h3");
      if (h) return h;
    }
    let heading = null;
    document.querySelectorAll("h1, h2, h3").forEach((h) => {
      if (!heading && h.textContent.trim().toLowerCase() === "imagineai") {
        heading = h;
      }
    });
    return heading;
  }

  // Given two nodes, find their lowest common ancestor, plus each node's
  // direct child-of-that-ancestor branch (the node to actually move).
  function findLcaBranches(a, b) {
    const chain = new Set();
    for (let n = a; n; n = n.parentElement) chain.add(n);

    let lca = null;
    let bBranch = b;
    for (let n = b; n; n = n.parentElement) {
      if (chain.has(n)) {
        lca = n;
        break;
      }
      bBranch = n;
    }
    if (!lca) return null;

    let aBranch = a;
    for (let n = a; n && n !== lca; n = n.parentElement) aBranch = n;

    return { lca, aBranch, bBranch };
  }

  function reorderRobotAboveHeading() {
    const container = getHeroContainer();
    const img = getHeroImg(container);
    const heading = getHeroHeading(container);
    if (!img || !heading) return;

    const result = findLcaBranches(img, heading);
    if (!result) return;
    const { lca, aBranch: imgBranch, bBranch: headingBranch } = result;
    if (!imgBranch || !headingBranch || imgBranch === headingBranch) return;

    const position = headingBranch.compareDocumentPosition(imgBranch);
    const imgIsAfterHeading = !!(position & Node.DOCUMENT_POSITION_FOLLOWING);

    if (imgIsAfterHeading) {
      lca.insertBefore(imgBranch, headingBranch);
    }
  }

  reorderRobotAboveHeading();
  new MutationObserver(reorderRobotAboveHeading).observe(
    document.documentElement,
    { childList: true, subtree: true }
  );
})();

/**
 * imagineAI — hero centering
 * -----------------------------------------------------------
 * REMOVED (build 2026-08-08h): this used to be a requestAnimationFrame
 * loop that measured the composer's center and force-applied
 * transform: translateX(...) to the robot image and each hero text node
 * every frame. It's gone now because it was fighting custom.css instead
 * of fixing the actual problem:
 *
 *   - custom.css already centers the hero correctly (align-items:center
 *     + width:100%/margin:0 auto on .step:first-of-type, its image, its
 *     <h2>, and now its subheading elements too).
 *   - This script's own delta calc, applied on TOP of already-centered
 *     elements, is what produced the visible offset on the second
 *     subheading line -- two centering systems disagreeing, not one
 *     system failing.
 *   - The real reason the subheadings looked uncentered was that
 *     custom.css's old selector (".markdown-body p") didn't match this
 *     Chainlit build's actual markup (`div[role="article"]`, no
 *     .markdown-body wrapper) -- fixed directly in custom.css instead.
 *
 * If a future Chainlit upgrade reintroduces a genuine centering gap,
 * fix it in custom.css against the real DOM structure first; reach for
 * a JS transform hack only if CSS truly cannot express the fix.
 */