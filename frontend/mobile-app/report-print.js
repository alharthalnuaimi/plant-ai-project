/**
 * Printable scan report (browser "Save as PDF").
 *
 * `pvBuildPrintableReport(report)` turns the JSON report built by
 * `_pvBuildScanReport` (app.js) into a standalone HTML document in the
 * report's language: English left-to-right, or Arabic right-to-left with
 * an Arabic font. Gemini's Arabic block (`report.localized`) is used for the
 * Arabic text when present; scientific names, units and IDs stay LTR.
 * Missing values print as "—"; nothing is filled in.
 */
(function () {
  "use strict";

  const AR = {
    "PlantVision — Plant Scan Report": "PlantVision — تقرير فحص النبتة",
    "Generated": "تاريخ الإنشاء",
    "Scanned": "وقت الفحص",
    "Source": "المصدر",
    "Plant Identification": "التعرّف على النبتة",
    "Plant": "النبتة",
    "Scientific name": "الاسم العلمي",
    "Family": "الفصيلة",
    "Genus": "الجنس",
    "Identification confidence": "ثقة التعرّف",
    "Diagnosis": "التشخيص",
    "Health status": "الحالة الصحية",
    "Condition": "الحالة المرضية",
    "Category": "الفئة",
    "Severity": "الشدة",
    "AI diagnosis confidence": "ثقة التشخيص بالذكاء الاصطناعي",
    "Summary": "الملخص",
    "Visible signs": "العلامات الظاهرة",
    "Alternative diagnoses": "تشخيصات بديلة",
    "Uncertainties": "نقاط غير مؤكدة",
    "Recommendations": "التوصيات",
    "Recommended action": "الإجراء الموصى به",
    "AI analysis": "تحليل الذكاء الاصطناعي",
    "Environment at scan time": "البيئة وقت الفحص",
    "Air temperature": "حرارة الهواء",
    "Air humidity": "رطوبة الهواء",
    "Light": "الإضاءة",
    "Soil moisture": "رطوبة التربة",
    "Soil pH": "حموضة التربة (pH)",
    "Soil EC": "موصلية التربة (EC)",
    "Context": "السياق",
    "Zone": "المنطقة",
    "Device": "الجهاز",
    "AI model": "نموذج الذكاء الاصطناعي",
    "AI confidence values are the model's own estimate, not a lab result.":
      "قيم الثقة هي تقدير النموذج نفسه وليست نتيجة مختبرية.",
    "Print / Save as PDF": "طباعة / حفظ بصيغة PDF",
    // enum values
    healthy: "سليمة",
    possible_disease: "مرض محتمل",
    possible_water_stress: "إجهاد مائي محتمل",
    other_problem: "مشكلة ظاهرة أخرى",
    uncertain: "غير مؤكد — الصورة غير كافية",
    fungal: "فطري", bacterial: "بكتيري", viral: "فيروسي", pest: "آفات",
    nutrient_deficiency: "نقص المغذيات", environmental_stress: "إجهاد بيئي",
    physical_damage: "ضرر مادي", unknown: "غير معروف",
    none: "لا يوجد", mild: "خفيفة", moderate: "متوسطة", severe: "شديدة",
    upload: "رفع صورة", camera: "الكاميرا", chat_camera: "كاميرا المحادثة",
    possible: "محتمل", confirmed: "مؤكد",
  };

  const EN_ENUM = {
    healthy: "Healthy", possible_disease: "Possible disease", possible_water_stress: "Possible water stress",
    other_problem: "Other visible problem", uncertain: "Uncertain — image insufficient",
  };

  function esc(v) {
    return String(v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function has(v) {
    return v !== null && v !== undefined && String(v).trim() !== "" && String(v).trim() !== "—";
  }

  function pvBuildPrintableReport(report) {
    report = report || {};
    const pageLang = window.pvI18n ? window.pvI18n.getLang() : "en";
    const lang = report.language === "ar" || report.language === "en" ? report.language : pageLang;
    const ar = lang === "ar";
    const T = (s) => (ar && AR[s]) || s;
    const E = (v) => (has(v) ? (ar && AR[v]) || (EN_ENUM[v] || v) : null);
    const loc = (ar && report.localized) || {};
    const plant = report.plant_identification || {};
    const dx = report.diagnosis || {};
    const rec = report.recommendations || {};
    const env = report.environment || {};
    const ctx = report.context || {};
    const model = report.ai_model || {};
    const dash = "—";
    const txt = (v) => (has(v) ? esc(v) : dash);
    const ltr = (v, cls) => (has(v) ? `<bdi dir="ltr"${cls ? ` class="${cls}"` : ""}>${esc(v)}</bdi>` : dash);
    const fmtDate = (iso) => {
      if (!has(iso)) return dash;
      try {
        return esc(new Date(iso).toLocaleString(ar ? "ar-u-nu-latn" : "en-US", { dateStyle: "medium", timeStyle: "short" }));
      } catch (_) {
        return esc(iso);
      }
    };
    const pct = (v) => (has(v) ? `<bdi dir="ltr">${esc(v)}%</bdi>` : dash);
    const row = (label, value) => `<tr><th>${esc(T(label))}</th><td>${value}</td></tr>`;
    const list = (items) => {
      const clean = (items || []).filter(has);
      return clean.length ? `<ul>${clean.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : `<p>${dash}</p>`;
    };

    // Arabic text from Gemini's localized block when available; otherwise known
    // names go through the Arabic dictionary (scans without a block: older,
    // English-made or demo scans). Unknown names are shown as given.
    const dict = (v) => (ar && has(v) && window.pvI18n && window.pvI18n.toArabic ? window.pvI18n.toArabic(v) : v);
    const plantName = loc.plant_common_name || dict(plant.common_name);
    const condition = loc.condition || dict(dx.condition);
    const summary = loc.summary || dx.summary;
    const action = loc.recommended_action || rec.gemini_recommended_action;
    const signs = (loc.observations && loc.observations.length)
      ? loc.observations
      : (dx.symptoms || []).map((s) => s && s.finding + (s.certainty === "possible" ? ` (${ar ? AR.possible : "possible"})` : ""));
    const uncertainties = (loc.uncertainties && loc.uncertainties.length) ? loc.uncertainties : dx.uncertainties;
    const alternatives = (loc.alternative_diagnoses && loc.alternative_diagnoses.length)
      ? loc.alternative_diagnoses
      : (dx.alternative_diagnoses || []).map((a) => (a && a.condition ? `${a.condition}${a.reason ? " — " + a.reason : ""}` : null));
    const status = E(dx.health_category) || dx.health_status;

    const font = ar
      ? '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;600;700&display=swap" rel="stylesheet">'
      : '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&display=swap" rel="stylesheet">';
    const family = ar ? "'IBM Plex Sans Arabic', 'Segoe UI', Tahoma, sans-serif" : "'Space Grotesk', 'Segoe UI', sans-serif";

    return `<!DOCTYPE html>
<html lang="${lang}" dir="${ar ? "rtl" : "ltr"}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(T("PlantVision — Plant Scan Report"))}</title>
${font}
<style>
  :root { --ink:#1d2420; --muted:#5d6b62; --line:#d9e0da; --accent:#4f7a55; --bg:#ffffff; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font-family: ${family};
         font-size: 13px; line-height: ${ar ? 1.85 : 1.55}; }
  main { max-width: 780px; margin: 0 auto; padding: 32px 28px 48px; }
  header { border-block-end: 3px solid var(--accent); padding-block-end: 12px; margin-block-end: 20px; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  h2 { font-size: 15px; color: var(--accent); margin: 24px 0 8px; padding-block-end: 4px; border-block-end: 1px solid var(--line); }
  .meta { color: var(--muted); font-size: 12px; display: flex; flex-wrap: wrap; gap: 4px 18px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: start; vertical-align: top; padding: 6px 8px; border-block-end: 1px solid var(--line); }
  th { width: 38%; color: var(--muted); font-weight: 600; }
  .status { display: inline-block; padding: 2px 10px; border-radius: 999px; background: #eef4ef; color: var(--accent); font-weight: 700; }
  .sci { font-style: italic; }
  ul { margin: 4px 0; padding-inline-start: 22px; }
  p { margin: 4px 0; }
  .note { color: var(--muted); font-size: 11px; margin-block-start: 28px; }
  .print-btn { position: fixed; inset-block-start: 14px; inset-inline-end: 14px; padding: 8px 14px; border: 0;
               border-radius: 6px; background: var(--accent); color: #fff; font: inherit; cursor: pointer; }
  @media print { .print-btn { display: none; } main { padding: 0; } }
</style>
</head>
<body>
<button class="print-btn" type="button" onclick="window.print()">${esc(T("Print / Save as PDF"))}</button>
<main>
  <header>
    <h1>${esc(T("PlantVision — Plant Scan Report"))}</h1>
    <div class="meta">
      <span>${esc(T("Generated"))}: ${fmtDate(report.generated_at)}</span>
      <span>${esc(T("Scanned"))}: ${fmtDate(report.scan && report.scan.result_received_at)}</span>
      <span>${esc(T("Source"))}: ${txt(E(report.scan && report.scan.scan_source))}</span>
    </div>
  </header>

  <h2>${esc(T("Diagnosis"))}</h2>
  <table>
    ${row("Health status", has(status) ? `<span class="status">${esc(status)}</span>` : dash)}
    ${row("Condition", txt(condition))}
    ${row("Category", txt(E(dx.condition_category)))}
    ${row("Severity", txt(E(dx.severity)))}
    ${row("AI diagnosis confidence", pct(dx.ai_diagnosis_confidence_pct))}
  </table>
  <h2>${esc(T("Summary"))}</h2>
  <p>${txt(summary)}</p>
  <h2>${esc(T("Visible signs"))}</h2>
  ${list(signs)}
  <h2>${esc(T("Alternative diagnoses"))}</h2>
  ${list(alternatives)}
  <h2>${esc(T("Uncertainties"))}</h2>
  ${list(uncertainties)}

  <h2>${esc(T("Recommendations"))}</h2>
  <table>
    ${row("Recommended action", txt(action))}
    ${row("AI analysis", txt(rec.ai_analysis))}
  </table>

  <h2>${esc(T("Plant Identification"))}</h2>
  <table>
    ${row("Plant", txt(plantName))}
    ${row("Scientific name", ltr(plant.scientific_name, "sci"))}
    ${row("Family", ltr(plant.family))}
    ${row("Genus", ltr(plant.genus, "sci"))}
    ${row("Identification confidence", pct(plant.plant_id_confidence_pct))}
  </table>

  <h2>${esc(T("Environment at scan time"))}</h2>
  <table>
    ${row("Air temperature", ltr(env.air_temperature))}
    ${row("Air humidity", ltr(env.air_humidity))}
    ${row("Light", ltr(env.light))}
    ${row("Soil moisture", ltr(env.soil_humidity))}
    ${row("Soil pH", ltr(env.soil_ph))}
    ${row("Soil EC", ltr(env.soil_ec))}
  </table>

  <h2>${esc(T("Context"))}</h2>
  <table>
    ${row("Zone", ltr(ctx.zone_id))}
    ${row("Device", ltr(ctx.device_id))}
    ${row("AI model", ltr([model.model, model.prompt_version].filter(has).join(" / ")))}
  </table>

  <p class="note">${esc(T("AI confidence values are the model's own estimate, not a lab result."))}</p>
</main>
</body>
</html>`;
  }

  /** Open the report in a new tab, ready to print / save as PDF. */
  function pvOpenPrintableReport(report) {
    const html = pvBuildPrintableReport(report);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return !!win;
  }

  window.pvBuildPrintableReport = pvBuildPrintableReport;
  window.pvOpenPrintableReport = pvOpenPrintableReport;
})();
