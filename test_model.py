import os
from ultralytics import YOLO

# 1. حدد مسار الأوزان الجديدة الخاصة بنبتة الروز بعد نقلها وتسميتها
# (تم تحديث الاسم إلى rose_best.pt بناءً على طلبك)
weights_path = r"C:\Users\sasuki\Desktop\project\plant-ai-project\backend\rose_best.pt"

# ضع هنا مسار أي صورة تريد اختبارها
image_path = r"C:\Users\sasuki\Desktop\project\plant-ai-project\test_image.jpg"

print("⏳ جاري تحميل موديل YOLOv8 والأوزان الجديدة للروز...")

if not os.path.exists(weights_path):
    print(f"❌ خطأ: ملف الأوزان غير موجود في المسار المحدد: {weights_path}")
elif not os.path.exists(image_path):
    print(f"❌ خطأ: صورة الاختبار غير موجودة في المسار المحدد: {image_path}")
else:
    # تحميل الموديل
    model = YOLO(weights_path)

    print("🚀 جاري فحص الصورة وتشغيل التوقع...")
    # تشغيل التوقع
    results = model(image_path, conf=0.5, iou=0.4)

    print("\n🍏 --- نتائج الفحص المباشرة --- 🍏")
    # طباعة النتائج المكتشفة في التيرمنال
    for result in results:
        for box in result.boxes:
            class_id = int(box.cls[0])
            label = model.names[class_id]
            confidence = float(box.conf[0])
            print(f"📍 الكلاس المكتشف: {label} | نسبة التأكد : {confidence:.2%}")