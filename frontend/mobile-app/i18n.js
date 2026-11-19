/**
 * PlantVision i18n — English (default) / Arabic.
 *
 * English source strings are the translation keys (gettext style), so the
 * existing markup and modules keep writing English and stay the source of
 * truth. In Arabic mode:
 *
 *  - every text node and the title / placeholder / aria-label / data-tip /
 *    alt attributes are translated from `window.PV_AR` (i18n-ar.js), both on
 *    the initial page and whenever a module re-renders (MutationObserver);
 *  - `<html lang dir>` switch to `ar` / `rtl` (CSS handles the mirrored layout);
 *  - requests to the backend's text-producing routes carry `lang=ar`, so
 *    rule-based backend text comes back in Arabic (sensor routes never do).
 *
 * Switching back to English restores every original string. The choice is
 * stored in localStorage (`pv-lang`) and survives reloads.
 *
 * Elements (or ancestors) marked `data-i18n-skip` are never translated —
 * used for user-entered text such as chat messages.
 */
(function () {
  "use strict";

  const STORAGE_KEY = "pv-lang";
  const SUPPORTED = ["en", "ar"];
  const ATTRS = ["title", "placeholder", "aria-label", "data-tip", "alt"];
  // Backend routes whose responses contain rule-based text (see backend main.py).
  const LOCALIZED_PATHS = /^\/(report|analytics|scans|care|predict|health\/plant|chat)(\/|$|\?)/;

  const AR = window.PV_AR || { exact: {}, patterns: [], technical: [] };
  const exact = AR.exact || {};
  const patterns = (AR.patterns || []).map(([re, fn]) => [re, fn]);
  const technical = new Set(AR.technical || []);

  function readStored() {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      return SUPPORTED.includes(v) ? v : "en";
    } catch (_) {
      return "en";
    }
  }

  let lang = readStored();

  function fill(str, vars) {
    if (!vars) return str;
    return str.replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? String(vars[k]) : m));
  }

  /** Arabic for a known English string, or `null`. */
  function lookup(core) {
    if (Object.prototype.hasOwnProperty.call(exact, core)) return exact[core];
    for (const [re, build] of patterns) {
      const m = core.match(re);
      if (m) {
        const out = build(m, translateCore);
        if (out != null) return out;
      }
    }
    return null;
  }

  /** Translate a trimmed fragment (used recursively by patterns). Unknown → unchanged. */
  function translateCore(core) {
    if (core == null) return core;
    const s = String(core).trim();
    if (!s) return s;
    const hit = lookup(s);
    return hit == null ? s : hit;
  }

  /**
   * `t(english, vars?)` — the display string for the current language.
   * Placeholders like `{n}` are filled after translation.
   */
  function t(str, vars) {
    if (str == null) return str;
    str = String(str);
    if (lang !== "ar") return fill(str, vars);
    const m = str.match(/^(\s*)([\s\S]*?)(\s*)$/);
    const core = m[2];
    if (!core) return str;
    const hit = lookup(core);
    if (hit == null) {
      // A filled-in template may be registered as e.g. "{n} scans".
      return fill(str, vars);
    }
    return m[1] + fill(hit, vars) + m[3];
  }

  function locale() {
    return lang === "ar" ? "ar-u-nu-latn" : "en-US";
  }

  /** Locale for toLocale*String: Arabic (Latin digits) or the browser default in English. */
  function dateLocale() {
    return lang === "ar" ? "ar-u-nu-latn" : undefined;
  }

  function isTechnical(s) {
    return technical.has(String(s).trim());
  }

  /** Arabic for a known English string whatever the UI language (reports). Unknown → unchanged. */
  function toArabic(str) {
    return str == null ? str : translateCore(String(str));
  }

  /**
   * `pick(record, "disease")` — in Arabic, the stored Arabic copy
   * (`disease_localized`) when the record has one; otherwise the canonical
   * English value (which the DOM translator still translates if it is known).
   */
  function pick(record, field) {
    if (!record) return undefined;
    if (lang !== "ar") return record[field];
    const meta = record.metadata || {};
    const loc = (meta.gemini_diagnosis && meta.gemini_diagnosis.localized) || {};
    const fromMeta = {
      disease: meta.localized_condition || loc.condition,
      plant_name: meta.localized_plant_name || loc.plant_common_name,
      recommendation: meta.guidance_localized,
    }[field];
    return record[field + "_localized"] || fromMeta || record[field];
  }

  // ----------------------------------------------------------------------
  // Backend requests
  // ----------------------------------------------------------------------

  function withLang(url) {
    if (lang !== "ar" || !url) return url;
    const base = (window.PLANT_API_BASE || "").replace(/\/$/, "");
    const s = String(url);
    if (!base || s.indexOf(base) !== 0) return url;
    const rest = s.slice(base.length);
    if (!LOCALIZED_PATHS.test(rest) || /[?&]lang=/.test(rest)) return url;
    return s + (s.indexOf("?") >= 0 ? "&" : "?") + "lang=ar";
  }

  if (typeof window.fetch === "function") {
    const nativeFetch = window.fetch;
    window.fetch = function (input, init) {
      if (typeof input === "string") return nativeFetch.call(this, withLang(input), init);
      return nativeFetch.call(this, input, init);
    };
  }

  // ----------------------------------------------------------------------
  // DOM translation
  // ----------------------------------------------------------------------

  const originals = new WeakMap(); // Text node → English source
  const attrOriginals = new WeakMap(); // Element → { attr: English }
  let observer = null;
  let applying = false;

  function skipped(el) {
    return !!(el && el.closest && el.closest("[data-i18n-skip], script, style, textarea, code"));
  }

  function translateTextNode(node) {
    const parent = node.parentElement;
    if (!parent || skipped(parent)) return;
    const cur = node.nodeValue;
    if (!cur || !/[A-Za-z]/.test(cur)) return;
    const next = t(cur);
    if (next !== cur) {
      originals.set(node, cur);
      node.nodeValue = next;
    }
  }

  function translateAttrs(el) {
    if (skipped(el)) return;
    for (const a of ATTRS) {
      const cur = el.getAttribute(a);
      if (!cur || !/[A-Za-z]/.test(cur)) continue;
      const next = t(cur);
      if (next !== cur) {
        const saved = attrOriginals.get(el) || {};
        saved[a] = cur;
        attrOriginals.set(el, saved);
        el.setAttribute(a, next);
      }
    }
  }

  function translateTree(root) {
    if (!root || lang !== "ar") return;
    if (root.nodeType === 3) return translateTextNode(root);
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) translateAttrs(root);
    const walker = document.createTreeWalker(root, 5 /* ELEMENT | TEXT */);
    let n = walker.nextNode();
    while (n) {
      if (n.nodeType === 3) translateTextNode(n);
      else translateAttrs(n);
      n = walker.nextNode();
    }
  }

  function restoreTree(root) {
    const walker = document.createTreeWalker(root, 5);
    let n = walker.nextNode();
    while (n) {
      if (n.nodeType === 3) {
        if (originals.has(n)) {
          n.nodeValue = originals.get(n);
          originals.delete(n);
        }
      } else {
        const saved = attrOriginals.get(n);
        if (saved) {
          for (const a of Object.keys(saved)) n.setAttribute(a, saved[a]);
          attrOriginals.delete(n);
        }
      }
      n = walker.nextNode();
    }
  }

  function onMutations(list) {
    if (applying) return;
    applying = true;
    try {
      for (const m of list) {
        if (m.type === "characterData") translateTextNode(m.target);
        else if (m.type === "attributes") translateAttrs(m.target);
        else m.addedNodes.forEach(translateTree);
      }
    } finally {
      applying = false;
    }
  }

  function startObserver() {
    if (observer || typeof MutationObserver === "undefined" || !document.body) return;
    observer = new MutationObserver(onMutations);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRS,
    });
  }

  function stopObserver() {
    if (observer) observer.disconnect();
    observer = null;
  }

  let englishTitle = document.title;

  function applyDocument() {
    const root = document.documentElement;
    root.setAttribute("lang", lang);
    root.setAttribute("dir", lang === "ar" ? "rtl" : "ltr");
    if (lang === "ar") {
      document.title = t(englishTitle);
    } else if (englishTitle) {
      document.title = englishTitle;
    }
    const toggles = document.querySelectorAll("[data-lang-toggle]");
    for (const btn of toggles) {
      btn.setAttribute("aria-pressed", lang === "ar" ? "true" : "false");
      const lbl = btn.querySelector("[data-lang-label]");
      if (lbl) lbl.textContent = lang === "ar" ? "EN" : "ع";
    }
    const selects = document.querySelectorAll("[data-lang-select]");
    for (const sel of selects) sel.value = lang;
  }

  function applyDom() {
    if (!document.body) return;
    if (lang === "ar") {
      translateTree(document.body);
      startObserver();
    } else {
      stopObserver();
      restoreTree(document.body);
    }
  }

  function setLang(next) {
    next = SUPPORTED.includes(next) ? next : "en";
    const changed = next !== lang;
    if (lang === "en") englishTitle = document.title;
    lang = next;
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (_) {
      /* private mode: the choice just won't persist */
    }
    applyDocument();
    applyDom();
    if (changed) {
      try {
        window.dispatchEvent(new CustomEvent("plantvision:lang-changed", { detail: { lang } }));
      } catch (_) {
        /* old browsers */
      }
    }
    return lang;
  }

  function bindControls() {
    document.querySelectorAll("[data-lang-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => setLang(lang === "ar" ? "en" : "ar"));
    });
    document.querySelectorAll("[data-lang-select]").forEach((sel) => {
      sel.addEventListener("change", () => setLang(sel.value));
    });
  }

  applyDocument();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      englishTitle = lang === "en" ? document.title : englishTitle;
      applyDocument();
      applyDom();
      bindControls();
    });
  } else {
    applyDom();
    bindControls();
  }

  window.pvI18n = {
    t,
    getLang: () => lang,
    setLang,
    isRTL: () => lang === "ar",
    locale,
    dateLocale,
    withLang,
    isTechnical,
    translateTree,
    toArabic,
    pick,
  };
})();
