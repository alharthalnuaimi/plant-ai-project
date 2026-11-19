"""Arabic copies of the backend's rule-based English text.

The backend builds some user-facing sentences without an LLM (care
templates, the disease catalog, health/report narratives, analytics
insights, alert and event messages). This module holds the Arabic copy
of every one of them and translates them only at the response boundary,
when the client asks for ``lang=ar``. Nothing stored is changed, and an
English request is never touched.

Translation is deliberately conservative:

* only exact known sentences (``_EXACT``) or known sentence templates
  (``_PATTERNS``) are translated; anything else (IDs, Gemini prose, user
  data) is returned unchanged;
* identifier and enum fields (``_SKIP_KEYS``) are never rewritten, so
  frontend logic that compares ``status`` / ``disease`` / ``category``
  values keeps working.
"""

from __future__ import annotations

import re
from typing import Any, Callable

# --------------------------------------------------------------------------
# Exact sentences
# --------------------------------------------------------------------------

_EXACT: dict[str, str] = {
    # ---- disease catalog (services.disease_taxonomy) ---------------------
    "Healthy": "سليمة",
    "Powdery Mildew": "البياض الدقيقي",
    "Downy Mildew": "البياض الزغبي",
    "Bacterial Wilt": "الذبول البكتيري",
    "Leaf Spot": "تبقّع الأوراق",
    "Diseased": "مصابة",
    "Unknown": "غير معروف",
    "Uncertain": "غير مؤكد",
    "Not assessable": "غير قابلة للتقييم",
    "Maintain current irrigation and monitor weekly.": "حافظ على نظام الري الحالي وراقب النبتة أسبوعياً.",
    "Improve airflow, reduce leaf wetness, and apply fungicide if spread continues.":
        "حسّن التهوية وقلّل بلل الأوراق، واستخدم مبيداً فطرياً إذا استمر الانتشار.",
    "Remove affected foliage, avoid overhead watering, and treat with appropriate fungicide.":
        "أزل الأوراق المصابة وتجنّب الري من الأعلى، وعالج بمبيد فطري مناسب.",
    "Isolate affected plants immediately; bacterial wilt often requires removal of infected stock.":
        "اعزل النباتات المصابة فوراً؛ فالذبول البكتيري يتطلب غالباً إزالة النباتات المصابة.",
    "Prune infected leaves and avoid splashing water on foliage.":
        "قلّم الأوراق المصابة وتجنّب رشّ الماء على المجموع الخضري.",
    "Inspect affected leaves and increase monitoring; consider targeted treatment.":
        "افحص الأوراق المصابة وزِد المراقبة، وفكّر في علاج موجّه.",
    "Capture another angle with better lighting for a clearer diagnosis.":
        "التقط صورة من زاوية أخرى وبإضاءة أفضل للحصول على تشخيص أوضح.",
    # ---- plant health (services.plant_health) ----------------------------
    "Environment stress detected — check humidity, soil moisture, and temperature.":
        "تم رصد إجهاد بيئي — تحقّق من الرطوبة ورطوبة التربة ودرجة الحرارة.",
    # ---- care engine (services.care_engine) ------------------------------
    "Soil moisture": "رطوبة التربة",
    "Light intensity": "شدة الإضاءة",
    "Air temperature": "حرارة الهواء",
    "Air humidity": "رطوبة الهواء",
    "Soil pH": "حموضة التربة (pH)",
    "Soil EC": "الموصلية الكهربائية للتربة (EC)",
    "Soil too dry — water now (within target range).": "التربة جافة جداً — اسقِ الآن (ضمن النطاق المستهدف).",
    "Soil too wet — pause watering and improve drainage.": "التربة رطبة جداً — أوقف الري مؤقتاً وحسّن التصريف.",
    "Soil moisture optimal; stick to the configured schedule.": "رطوبة التربة مثالية؛ التزم بالجدول المحدد.",
    "Light below preferred range — consider supplemental grow lights.":
        "الإضاءة أقل من النطاق المفضّل — فكّر في إضاءة نمو إضافية.",
    "Light intensity exceeds preferred range — risk of leaf scorch.":
        "شدة الإضاءة تتجاوز النطاق المفضّل — خطر احتراق الأوراق.",
    "Light intensity within preferred range.": "شدة الإضاءة ضمن النطاق المفضّل.",
    "Air temperature below preferred range — risk of cold stress.":
        "حرارة الهواء أقل من النطاق المفضّل — خطر الإجهاد بسبب البرد.",
    "Air temperature above preferred range — increase ventilation.":
        "حرارة الهواء أعلى من النطاق المفضّل — زِد التهوية.",
    "Air temperature within preferred range.": "حرارة الهواء ضمن النطاق المفضّل.",
    "Humidity low — consider misting or a humidifier.": "الرطوبة منخفضة — فكّر في الرذاذ أو جهاز ترطيب.",
    "Humidity high — improve airflow to deter fungal disease.":
        "الرطوبة مرتفعة — حسّن التهوية للحدّ من الأمراض الفطرية.",
    "Humidity within preferred range.": "الرطوبة ضمن النطاق المفضّل.",
    "Soil too acidic — apply a small amount of lime.": "التربة حمضية جداً — أضف كمية صغيرة من الجير.",
    "Soil too alkaline — top-dress with sulfur or compost.": "التربة قلوية جداً — أضف الكبريت أو السماد العضوي على السطح.",
    "Soil pH within preferred range.": "حموضة التربة ضمن النطاق المفضّل.",
    "Nutrient salts low — schedule fertilization.": "أملاح المغذيات منخفضة — حدّد موعداً للتسميد.",
    "Nutrient salts high — flush soil with plain water.": "أملاح المغذيات مرتفعة — اغسل التربة بماء عادي.",
    "Soil EC within preferred range.": "الموصلية الكهربائية للتربة ضمن النطاق المفضّل.",
    # ---- report narratives (services.report_builder) ---------------------
    "Low — no concerning visual symptoms detected.": "منخفض — لم تُرصد أعراض ظاهرة مقلقة.",
    "Medium — early signs of disease; act early to prevent spread.":
        "متوسط — علامات مبكرة للمرض؛ تصرّف مبكراً لمنع انتشاره.",
    "High — clear disease indicators; isolate plant and treat immediately.":
        "مرتفع — مؤشرات واضحة للمرض؛ اعزل النبتة وعالجها فوراً.",
    "Critical — severe disease detected; remove affected tissue today.":
        "حرج — تم رصد مرض شديد؛ أزل الأنسجة المصابة اليوم.",
    "Medium — monitor closely.": "متوسط — راقب عن كثب.",
    "No live sensor reading available — environmental stress could not be evaluated.":
        "لا تتوفر قراءة حساس مباشرة — تعذّر تقييم الإجهاد البيئي.",
    "Environmental conditions are within target ranges.": "الظروف البيئية ضمن النطاقات المستهدفة.",
    "One or more environmental readings are drifting from target — adjust within 24h.":
        "قراءة بيئية واحدة أو أكثر تنحرف عن الهدف — عدّلها خلال 24 ساعة.",
    "Multiple environmental readings are out of range — environment is the primary stressor.":
        "عدة قراءات بيئية خارج النطاق — البيئة هي مصدر الإجهاد الرئيسي.",
    "Environment partially out of range.": "البيئة خارج النطاق جزئياً.",
    "Survival chance is excellent under current conditions.": "فرصة البقاء ممتازة في الظروف الحالية.",
    "Survival chance is good provided you act on the recommendations below.":
        "فرصة البقاء جيدة بشرط تنفيذ التوصيات أدناه.",
    "Survival chance is moderate — fix the highest-severity warning first.":
        "فرصة البقاء متوسطة — عالج التحذير الأشد خطورة أولاً.",
    "Survival chance is low — intervene now to prevent further decline.":
        "فرصة البقاء منخفضة — تدخّل الآن لمنع مزيد من التدهور.",
    # ---- analytics (services.analytics_store) ----------------------------
    "Awaiting scans": "بانتظار عمليات الفحص",
    "Diseased / at risk": "مصابة / معرّضة للخطر",
    "Scans recorded": "عمليات فحص مسجّلة",
    "Demo — no scans": "عرض تجريبي — لا توجد عمليات فحص",
    "No issues detected": "لم تُرصد مشكلات",
    "Awaiting sensor data": "بانتظار بيانات الحساس",
    "Environmental stress": "إجهاد بيئي",
    "Monitor closely": "راقب عن كثب",
    "Stable readings": "قراءات مستقرة",
    "Scan data only — awaiting sensor": "بيانات الفحص فقط — بانتظار الحساس",
    "Inspect affected leaves and isolate the zone if symptoms spread.":
        "افحص الأوراق المصابة واعزل المنطقة إذا انتشرت الأعراض.",
    "Increase ventilation or shade and monitor EC over the next hour.":
        "زِد التهوية أو التظليل وراقب الموصلية الكهربائية خلال الساعة القادمة.",
    "Increase irrigation and recheck humidity within 30 minutes.":
        "زِد الري وأعد فحص الرطوبة خلال 30 دقيقة.",
    "Adjust nutrient solution and retest pH after the next watering cycle.":
        "عدّل محلول المغذيات وأعد قياس الحموضة بعد دورة الري التالية.",
    "All monitored zones are within normal parameters.": "جميع المناطق المراقَبة ضمن المعايير الطبيعية.",
    "Continue scheduled scans and sensor polling.": "واصل عمليات الفحص المجدولة وقراءة الحساسات.",
    "Humidity low": "الرطوبة منخفضة",
    "Humidity high": "الرطوبة مرتفعة",
    "Humidity normal": "الرطوبة طبيعية",
    "Soil dry": "التربة جافة",
    "Soil moisture low": "رطوبة التربة منخفضة",
    "Soil moisture OK": "رطوبة التربة جيدة",
    "pH acidic": "الحموضة مرتفعة (حمضية)",
    "pH alkaline": "التربة قلوية",
    "pH optimal": "الحموضة مثالية",
    "EC elevated": "الموصلية مرتفعة",
    "EC low": "الموصلية منخفضة",
    "EC normal": "الموصلية طبيعية",
    "Heat stress": "إجهاد حراري",
    "AI recommendation generated": "تم إنشاء توصية بالذكاء الاصطناعي",
    "Awaiting live sensor stream": "بانتظار بث الحساس المباشر",
    "Zone Alpha": "المنطقة ألفا",
    "Zone Beta": "المنطقة بيتا",
    "Zone Gamma": "المنطقة غاما",
    # ---- care templates (configs/care_templates.yaml) --------------------
    "Avoid heavy fertilizer — burns tender leaves.": "تجنّب التسميد الكثيف — فهو يحرق الأوراق الطرية.",
    "Avoid heavy nitrogen — degrades flavor.": "تجنّب النيتروجين الزائد — فهو يُضعف النكهة.",
    "Avoid overhead watering — wet leaves invite powdery mildew.":
        "تجنّب الري من الأعلى — الأوراق المبللة تشجّع البياض الدقيقي.",
    "Avoid overhead watering, encourage pollinators": "تجنّب الري من الأعلى، وشجّع الملقّحات",
    "Balanced feed, support stems": "تغذية متوازنة، ودعم السيقان",
    "Bolting (avoid)": "الإزهار المبكر (تجنّبه)",
    "Bright direct light; basil flavor intensifies in full sun.":
        "إضاءة مباشرة ساطعة؛ تزداد نكهة الريحان في الشمس الكاملة.",
    "Bright indirect light, thin to 6 inches apart": "إضاءة ساطعة غير مباشرة، وخفّف الشتلات لمسافة 15 سم تقريباً",
    "Bright light, gentle watering, harden off before transplant":
        "إضاءة ساطعة وري لطيف، وأقلِم الشتلات قبل نقلها",
    "Calcium-deficiency causes blossom-end rot.": "نقص الكالسيوم يسبب تعفّن طرف الثمرة.",
    "Compost tea works well between feedings.": "شاي السماد العضوي مفيد بين مرات التسميد.",
    "Constant moisture, soil temperature 21-29°C": "رطوبة ثابتة، وحرارة تربة 21-29°م",
    "Constant moisture, warm soil": "رطوبة ثابتة، وتربة دافئة",
    "Cool 15-21°C, surface-sown, kept moist": "جو بارد 15-21°م، بذر سطحي مع الحفاظ على الرطوبة",
    "Cool, even moisture prevents bolting and bitterness.": "الرطوبة الباردة المنتظمة تمنع الإزهار المبكر والمرارة.",
    "Daily light watering; never let it wilt": "ري خفيف يومي؛ لا تدعها تذبل أبداً",
    "Deep watering every 2-3 days; daily during fruiting heat":
        "ري عميق كل 2-3 أيام؛ ويومياً أثناء حرّ فترة الإثمار",
    "Drip irrigation preferred — wet leaves invite gray mold.":
        "يُفضّل الري بالتنقيط — الأوراق المبللة تشجّع العفن الرمادي.",
    "Establishment": "التثبيت",
    "Every 1-2 days during fruiting; every 2-3 days otherwise": "كل 1-2 يوم أثناء الإثمار؛ وكل 2-3 أيام في غير ذلك",
    "Every 1-2 days during fruiting; every 2-3 otherwise": "كل 1-2 يوم أثناء الإثمار؛ وكل 2-3 أيام في غير ذلك",
    "Every 1-2 days; keep evenly moist": "كل 1-2 يوم؛ حافظ على رطوبة منتظمة",
    "Every 10-14 days; calcium foliar once weekly during fruit set":
        "كل 10-14 يوماً؛ ورشّ ورقي بالكالسيوم مرة أسبوعياً أثناء عقد الثمار",
    "Every 14 days during fruiting": "كل 14 يوماً أثناء الإثمار",
    "Every 14 days during vegetative + fruiting": "كل 14 يوماً خلال النمو الخضري والإثمار",
    "Every 2-3 days": "كل 2-3 أيام",
    "Every 2-3 days; let top inch of soil dry between waterings":
        "كل 2-3 أيام؛ دع الطبقة العليا من التربة (نحو 2.5 سم) تجف بين الريّات",
    "Every 7-10 days during vegetative + fruiting stages": "كل 7-10 أيام خلال مرحلتي النمو الخضري والإثمار",
    "Every 7-10 days": "كل 7-10 أيام",
    "Flowering (pinch)": "الإزهار (اقطف الأزهار)",
    "Flowering": "الإزهار",
    "Fruiting": "الإثمار",
    "Full sun maximizes berry sweetness.": "الشمس الكاملة تزيد حلاوة الثمار إلى أقصى حد.",
    "Full sun preferred; tolerates partial shade in afternoon.":
        "تُفضّل الشمس الكاملة؛ وتتحمّل الظل الجزئي بعد الظهر.",
    "Full sun; minimum 6h direct light for fruit set.": "شمس كاملة؛ 6 ساعات على الأقل من الضوء المباشر لعقد الثمار.",
    "Full sun; struggles below 6h direct light.": "شمس كاملة؛ يضعف نموها بأقل من 6 ساعات من الضوء المباشر.",
    "Germination": "الإنبات",
    "Harvest at color change for sweetness": "احصد عند تغيّر اللون للحصول على الحلاوة",
    "Harvest daily, net against birds, watch for gray mold": "احصد يومياً، وغطِّ بشبكة ضد الطيور، وراقب العفن الرمادي",
    "Harvest every 1-2 days, watch for powdery mildew": "احصد كل 1-2 يوم، وراقب البياض الدقيقي",
    "Heavy feeding, vertical training, prune lower leaves": "تغذية كثيفة، وتربية رأسية، وتقليم الأوراق السفلية",
    "High nitrogen delays fruit set.": "النيتروجين المرتفع يؤخّر عقد الثمار.",
    "Inconsistent moisture causes blossom-end rot — keep it steady.":
        "تذبذب الرطوبة يسبب تعفّن طرف الثمرة — حافظ على ثباتها.",
    "Light feed every 14 days": "تسميد خفيف كل 14 يوماً",
    "Loamy, well-drained": "طميية، جيدة التصريف",
    "Loose, fertile, well-drained loam with high organic matter":
        "تربة طميية مفككة وخصبة وجيدة التصريف وغنية بالمادة العضوية",
    "Loose, moisture-retentive loam": "تربة طميية مفككة تحتفظ بالرطوبة",
    "Lower nitrogen, encourage pollination": "قلّل النيتروجين، وشجّع التلقيح",
    "Mulch heavily, train runners or remove": "غطِّ التربة بطبقة كثيفة، ووجّه المدادات أو أزلها",
    "Nitrogen-heavy feeding, ample light": "تغذية غنية بالنيتروجين، وإضاءة وافرة",
    "Once temperatures stay above 24°C, harvest immediately": "بمجرد أن تبقى الحرارة فوق 24°م، احصد فوراً",
    "Partial shade in hot climates extends harvest window.": "الظل الجزئي في المناخات الحارة يطيل فترة الحصاد.",
    "Peppers dislike wet feet — drainage matters more than frequency.":
        "الفلفل لا يحب تشبّع الجذور بالماء — التصريف أهم من عدد مرات الري.",
    "Pinch first flowers to build root mass": "اقطف الأزهار الأولى لبناء كتلة جذرية",
    "Pinch flowers immediately to keep leaves productive": "اقطف الأزهار فوراً لتبقى الأوراق منتجة",
    "Pinch top leaves to encourage bushier growth.": "اقطف الأوراق العلوية لتشجيع نمو أكثف.",
    "Pinch tops every 2 weeks for bushier plants": "اقطف القمم كل أسبوعين لنباتات أكثف",
    "Reduce nitrogen at fruit set to favor fruit development.": "قلّل النيتروجين عند عقد الثمار لدعم نموها.",
    "Reduce nitrogen, encourage pollinators, maintain even moisture":
        "قلّل النيتروجين، وشجّع الملقّحات، وحافظ على رطوبة منتظمة",
    "Reduce nitrogen, hand-pollinate if indoors": "قلّل النيتروجين، ولقّح يدوياً إذا كانت النبتة في الداخل",
    "Rich, well-drained loam; tolerates slight acidity": "تربة طميية غنية جيدة التصريف؛ تتحمّل حموضة خفيفة",
    "Rich, well-drained potting mix": "خليط زراعة غني جيد التصريف",
    "Sandy loam, raised beds, well-mulched": "تربة طميية رملية، وأحواض مرتفعة، مع تغطية جيدة",
    "Sandy loam, well-drained, organic-rich": "تربة طميية رملية، جيدة التصريف، غنية بالمادة العضوية",
    "Seedling": "الشتلة",
    "Soil temperature 21-27°C, even moisture": "حرارة التربة 21-27°م، ورطوبة منتظمة",
    "Stake or cage, prune suckers, balanced feed": "ادعم بالأوتاد أو الأقفاص، وقلّم الفروع الجانبية، وغذِّ بتوازن",
    "Steady moisture, calcium foliar, harvest at first blush": "رطوبة ثابتة، ورشّ ورقي بالكالسيوم، واحصد عند أول تلوّن",
    "Steady moisture, harvest outer leaves continuously": "رطوبة ثابتة، واحصد الأوراق الخارجية باستمرار",
    "Strong direct light, gentle airflow, weak fertilizer": "إضاءة مباشرة قوية، وتهوية لطيفة، وسماد خفيف",
    "Strong light, gentle airflow": "إضاءة قوية، وتهوية لطيفة",
    "Strong light, slow hardening": "إضاءة قوية، وأقلمة تدريجية",
    "Vegetative": "النمو الخضري",
    "Warm soil 21-27°C, surface-sown": "تربة دافئة 21-27°م، بذر سطحي",
    "Warm soil 25-29°C, constant moisture": "تربة دافئة 25-29°م، ورطوبة ثابتة",
    "Harvest": "الحصاد",
    # ---- AI service errors (services.gemini.errors) ----------------------
    "The AI service returned an error. Please try again.": "أعادت خدمة الذكاء الاصطناعي خطأً. يرجى المحاولة مرة أخرى.",
    "AI diagnosis is not configured on the server (GEMINI_API_KEY is missing).":
        "التشخيص بالذكاء الاصطناعي غير مُعدّ على الخادم (مفتاح GEMINI_API_KEY مفقود).",
    "The server's Gemini API key was rejected. Check GEMINI_API_KEY.":
        "تم رفض مفتاح Gemini الخاص بالخادم. تحقّق من GEMINI_API_KEY.",
    "The Gemini API quota is used up. Try again later.": "تم استنفاد حصة Gemini. حاول مرة أخرى لاحقاً.",
    "The AI service is busy (rate limited). Please retry in a moment.":
        "خدمة الذكاء الاصطناعي مشغولة (تجاوز حد الطلبات). يرجى إعادة المحاولة بعد قليل.",
    "The AI service is temporarily unavailable. Please retry.":
        "خدمة الذكاء الاصطناعي غير متاحة مؤقتاً. يرجى إعادة المحاولة.",
    "The AI service took too long to respond. Please retry.":
        "استغرقت خدمة الذكاء الاصطناعي وقتاً طويلاً للرد. يرجى إعادة المحاولة.",
    "Could not reach the AI service. Check the server's network and retry.":
        "تعذّر الوصول إلى خدمة الذكاء الاصطناعي. تحقّق من شبكة الخادم وأعد المحاولة.",
    "The AI service declined to analyse this request for safety reasons. Try a different photo of the plant.":
        "رفضت خدمة الذكاء الاصطناعي تحليل هذا الطلب لأسباب تتعلق بالسلامة. جرّب صورة أخرى للنبتة.",
    "The AI service returned an unusable answer. Please retry.":
        "أعادت خدمة الذكاء الاصطناعي إجابة غير صالحة للاستخدام. يرجى إعادة المحاولة.",
    "The AI model configured on the server is not available right now. Please try again later.":
        "نموذج الذكاء الاصطناعي المُعدّ على الخادم غير متاح حالياً. يرجى المحاولة لاحقاً.",
    "The AI service could not process this request (invalid input).":
        "تعذّر على خدمة الذكاء الاصطناعي معالجة هذا الطلب (مدخلات غير صالحة).",
    "Expected an image upload": "يُتوقع رفع صورة",
    "Image too small or empty": "الصورة صغيرة جداً أو فارغة",
    "Uploaded file is not a readable image": "الملف المرفوع ليس صورة قابلة للقراءة",
    # plant names used as sentence subjects (e.g. report summaries)
    "cucumber": "الخيار",
    "Cucumber": "الخيار",
    "tomato": "الطماطم",
    "Tomato": "الطماطم",
    "pepper": "الفلفل",
    "Pepper": "الفلفل",
    "bell pepper": "الفلفل الحلو",
    "Bell Pepper": "الفلفل الحلو",
    "pepper_bell": "الفلفل الحلو",
    "Pepper_Bell": "الفلفل الحلو",
    "lettuce": "الخس",
    "Lettuce": "الخس",
    "basil": "الريحان",
    "Basil": "الريحان",
    "strawberry": "الفراولة",
    "Strawberry": "الفراولة",
    "rose": "الورد",
    "Rose": "الورد",
    "money plant": "نبتة المال",
    "Money Plant": "نبتة المال",
    "money_plant": "نبتة المال",
    "Money_Plant": "نبتة المال",
    "plant": "النبتة",
    "Plant": "النبتة",
    "10-10-10 vegetative; 5-10-10 fruiting": "10-10-10 للنمو الخضري؛ 5-10-10 للإثمار",
    "20-20-20 vegetative; 10-30-20 once flowering": "20-20-20 للنمو الخضري؛ 10-30-20 عند بدء الإزهار",
    "5-10-10 once flowering begins": "5-10-10 عند بدء الإزهار",
    "Mature": "النضج",
    "Bolting": "الإزهار المبكر",
}


def _t(text: str) -> str:
    """Translate a fragment if known, else keep it (e.g. a Gemini-named disease)."""

    return _EXACT.get(text.strip(), text.strip())


def plural_ar(n: int | str, one: str, two: str, few: str, many: str) -> str:
    """Arabic counted noun: 1 → "<one>", 2 → "<two>", 3-10 → "N <few>", else "N <many>"."""

    k = int(n)
    if k == 1:
        return one
    if k == 2:
        return two
    if 3 <= k % 100 <= 10:
        return f"{k} {few}"
    return f"{k} {many}"


def _issue_counts(crit: str | None, warn_extra: str | None, warn_only: str | None) -> str:
    if crit:
        out = plural_ar(crit, "مشكلة بيئية حرجة واحدة", "مشكلتان بيئيتان حرجتان", "مشكلات بيئية حرجة", "مشكلة بيئية حرجة")
        if warn_extra:
            out += " و" + plural_ar(warn_extra, "تحذير إضافي واحد", "تحذيران إضافيان", "تحذيرات إضافية", "تحذيراً إضافياً")
        return out + ". "
    if warn_only:
        return plural_ar(warn_only, "تحذير بيئي واحد", "تحذيران بيئيان", "تحذيرات بيئية", "تحذيراً بيئياً") + ". "
    return ""


_Pattern = tuple[re.Pattern[str], Callable[[re.Match[str]], str]]

_PATTERNS: list[_Pattern] = [
    # services.gemini.errors.ImageTooLargeError
    (re.compile(r"^Image is larger than the (\d+) MB upload limit\.$"),
     lambda m: f"حجم الصورة أكبر من حد الرفع البالغ {m[1]} ميغابايت."),
    # services.report_builder._explanation
    (re.compile(r"^Plant looks healthy \((\d+)/100\)\. Continue monitoring; no immediate action required\.$"),
     lambda m: f"تبدو النبتة سليمة ({m[1]}/100). واصل المراقبة؛ لا يلزم أي إجراء فوري."),
    (re.compile(r"^Plant health is (\d+)/100 due to (.+) indicators in the image\.$"),
     lambda m: f"صحة النبتة {m[1]}/100 بسبب مؤشرات {_t(m[2].replace('_', ' ').title())} في الصورة."),
    (re.compile(r"^(.+) \(Detection confidence (\d+)% — re-scan recommended\.\)$"),
     lambda m: f"{translate_text(m[1], 'ar')} (ثقة الكشف {m[2]}% — يُنصح بإعادة الفحص.)"),
    # services.plant_health — catalog tip + environment note
    (re.compile(r"^(.+) Also address environment stress \(humidity, soil moisture, or temperature\)\.$"),
     lambda m: f"{translate_text(m[1], 'ar')} وعالج أيضاً الإجهاد البيئي (الرطوبة أو رطوبة التربة أو الحرارة)."),
    # services.report_builder._summarise
    (re.compile(r"^(.+): the last photo could not be assessed\. Retake a clear, close photo of the affected leaves\.$"),
     lambda m: f"{_t(m[1])}: تعذّر تقييم الصورة الأخيرة. أعد التقاط صورة واضحة وقريبة للأوراق المصابة."),
    (re.compile(r"^(.+) looks healthy\. Plant health (\d+)/100, survival chance (\d+)/100\. No action required right now\.$"),
     lambda m: f"{_t(m[1])} تبدو سليمة. صحة النبتة {m[2]}/100، وفرصة البقاء {m[3]}/100. لا يلزم أي إجراء حالياً."),
    (re.compile(
        r"^(.+?): (?:(.+) suspected( \(low-confidence detection\))?\. )?"
        r"(?:(\d+) critical environmental issue\(s\)(?: and (\d+) additional warning\(s\))?\. |(\d+) environmental warning\(s\)\. )?"
        r"Plant health (\d+)/100, survival chance (\d+)/100\.$"
    ),
     lambda m: (
         f"{_t(m[1])}: "
         + (f"يُشتبه في {_t(m[2])}" + (" (كشف منخفض الثقة)" if m[3] else "") + ". " if m[2] else "")
         + _issue_counts(m[4], m[5], m[6])
         + f"صحة النبتة {m[7]}/100، وفرصة البقاء {m[8]}/100."
     )),
    # services.care_engine
    (re.compile(r"^Watering schedule: (.+)$"), lambda m: f"جدول الري: {_t(m[1])}"),
    (re.compile(r"^Fertilizer schedule: (.+?) — NPK (.+)$"),
     lambda m: f"جدول التسميد: {_t(m[1])} — NPK ‎{m[2]}"),
    (re.compile(r"^Fertilizer schedule: (.+)$"), lambda m: f"جدول التسميد: {_t(m[1])}"),
    (re.compile(r"^Preferred soil: (.+)$"), lambda m: f"التربة المفضّلة: {_t(m[1])}"),
    (re.compile(r"^(.+) below target \((.+), want (.+)\)$"),
     lambda m: f"{_t(m[1])} أقل من الهدف ({m[2]}، المطلوب {m[3]})"),
    (re.compile(r"^(.+) above target \((.+), want (.+)\)$"),
     lambda m: f"{_t(m[1])} أعلى من الهدف ({m[2]}، المطلوب {m[3]})"),
    (re.compile(r"^(.+) within target \((.+)\)\.$"), lambda m: f"{_t(m[1])} ضمن الهدف ({m[2]})."),
    # services.analytics_store — events, alerts and insights
    (re.compile(r"^Scan complete — (.+) \(([\d.]+%)\)$"), lambda m: f"اكتمل الفحص — {_t(m[1])} ({m[2]})"),
    (re.compile(r"^High-risk detection in (.+)$"), lambda m: f"رصد عالي الخطورة في {_t(m[1])}"),
    (re.compile(r"^Plant health score (\d+)% — (.+)$"),
     lambda m: f"مؤشر صحة النبتة {m[1]}% — {translate_text(m[2], 'ar')}"),
    (re.compile(r"^Low humidity warning — (.+) \((.+)\)$"), lambda m: f"تحذير رطوبة منخفضة — {_t(m[1])} ({m[2]})"),
    (re.compile(r"^Soil moisture low — (.+) \((.+)\)$"), lambda m: f"رطوبة التربة منخفضة — {_t(m[1])} ({m[2]})"),
    (re.compile(r"^Temperature stress — (.+) \((.+)\)$"), lambda m: f"إجهاد حراري — {_t(m[1])} ({m[2]})"),
    (re.compile(r"^Soil humidity warning — (.+)$"), lambda m: f"تحذير رطوبة التربة — {_t(m[1])}"),
    (re.compile(r"^Device (\S+) connected$"), lambda m: f"تم توصيل الجهاز {m[1]}"),
    (re.compile(r"^(.+) sensor updated$"), lambda m: f"تم تحديث حساس {_t(m[1])}"),
    (re.compile(r"^(.+) shows (.+) with ([\d.]+)% confidence\.$"),
     lambda m: f"تُظهر {_t(m[1])} {_t(m[2])} بثقة {m[3]}%."),
    (re.compile(r"^(.+) shows increasing temperature stress \((.+)\)\.$"),
     lambda m: f"تُظهر {_t(m[1])} إجهاداً حرارياً متزايداً ({m[2]})."),
    (re.compile(r"^(.+) soil moisture is low \((.+)\)\.$"), lambda m: f"رطوبة التربة في {_t(m[1])} منخفضة ({m[2]})."),
    (re.compile(r"^(.+) soil pH is ([\d.]+) \(outside optimal (.+)\)\.$"),
     lambda m: f"حموضة التربة في {_t(m[1])} هي {m[2]} (خارج النطاق المثالي {m[3]})."),
]


def translate_text(text: str, lang: str | None) -> str:
    """Return the Arabic copy of a known backend sentence; anything else unchanged."""

    if lang != "ar" or not isinstance(text, str) or not text.strip():
        return text
    exact = _EXACT.get(text) or _EXACT.get(text.strip())
    if exact:
        return exact
    for pattern, build in _PATTERNS:
        m = pattern.match(text.strip())
        if m:
            return build(m)
    return text


# Identifier / enum fields the frontend compares against — never rewritten.
_SKIP_KEYS = frozenset({
    "id", "disease", "status", "class_name", "disease_type", "category", "severity", "tone",
    "source", "event_type", "raw_disease_label", "species", "species_id", "common_name",
    "scientific_name", "family", "genus", "plant_name", "model", "model_name", "model_version",
    "timestamp", "created_at", "updated_at", "image_url", "image_public_url", "saved_path",
    "gemini_verdict", "gemini_diagnosis", "gemini", "localized", "risk_level", "urgency",
})


def localize_payload(node: Any, lang: str | None, _key: str | None = None) -> Any:
    """Recursively translate known backend sentences inside a JSON-like payload."""

    if lang != "ar":
        return node
    if _key is not None and (_key in _SKIP_KEYS or _key.endswith("_id")):
        return node
    if isinstance(node, str):
        return translate_text(node, lang)
    if isinstance(node, dict):
        return {k: localize_payload(v, lang, k) for k, v in node.items()}
    if isinstance(node, list):
        return [localize_payload(v, lang, _key) for v in node]
    return node
