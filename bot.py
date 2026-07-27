import logging
import sys
import os
import threading
import io
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from PIL import Image, ImageFilter, ImageEnhance
from config import BOT_TOKEN

# ============================================================
#  خادم وهمي لتخطي فحص Render
# ============================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# ============================================================
#  إعداد السجلات
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================================
#  قائمة التعديلات المجانية
# ============================================================
EDIT_OPTIONS = {
    "remove_clothes": {"name": "👗 إزالة الملابس", "desc": "محاكاة إزالة الملابس (تأثير فني)"},
    "nsfw_content": {"name": "🔥 محتوى جنسي", "desc": "محاكاة إنشاء محتوى جنسي (تأثيرات فنية)"},
    "video_gen": {"name": "🎥 تحويل إلى فيديو", "desc": "محاكاة تحويل الصورة إلى فيديو"},
    "grayscale": {"name": "⬛ أبيض وأسود", "desc": "تحويل الصورة إلى تدرجات رمادية"},
    "blur": {"name": "🌫️ ضبابية", "desc": "تطبيق تأثير ضبابي"},
    "enhance": {"name": "🎨 تحسين الألوان", "desc": "تحسين التباين والوضوح"},
    "resize": {"name": "📏 تغيير الحجم", "desc": "تصغير الصورة إلى 500x500"},
    "rotate": {"name": "🔄 تدوير", "desc": "تدوير الصورة 90 درجة"},
    "mirror": {"name": "🪞 انعكاس", "desc": "عكس الصورة أفقياً"},
}

# ============================================================
#  قائمة الخدمات الوهمية (محاكاة)
# ============================================================
SERVICES = {
    "local": {"name": "🖥️ معالجة محلية (مجانية)", "provider": "Pillow (Python)"},
    "fake_api": {"name": "🌐 محاكاة API (مجانية)", "provider": "محاكاة محلية"},
}

# ============================================================
#  أمر /start
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🖥️ معالجة محلية", callback_data="service_local")],
        [InlineKeyboardButton("🌐 محاكاة API", callback_data="service_fake_api")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔥 **بوت تعديل الصور الأسطوري (المجاني)**\n\n"
        "📌 اختر طريقة المعالجة:\n"
        "🖥️ **معالجة محلية**: تعديلات مجانية باستخدام Pillow.\n"
        "🌐 **محاكاة API**: محاكاة للخدمات المدفوعة (مجانية).\n\n"
        "⚠️ جميع التعديلات مجانية بالكامل.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ============================================================
#  اختيار الخدمة
# ============================================================
async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    service = query.data.replace("service_", "")
    context.user_data["service"] = service
    
    # عرض قائمة التعديلات
    keyboard = [
        [InlineKeyboardButton("👗 إزالة الملابس", callback_data="edit_remove_clothes")],
        [InlineKeyboardButton("🔥 محتوى جنسي", callback_data="edit_nsfw_content")],
        [InlineKeyboardButton("🎥 تحويل إلى فيديو", callback_data="edit_video_gen")],
        [InlineKeyboardButton("⬛ أبيض وأسود", callback_data="edit_grayscale")],
        [InlineKeyboardButton("🌫️ ضبابية", callback_data="edit_blur")],
        [InlineKeyboardButton("🎨 تحسين الألوان", callback_data="edit_enhance")],
        [InlineKeyboardButton("📏 تغيير الحجم", callback_data="edit_resize")],
        [InlineKeyboardButton("🔄 تدوير", callback_data="edit_rotate")],
        [InlineKeyboardButton("🪞 انعكاس", callback_data="edit_mirror")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    service_name = SERVICES[service]["name"]
    await query.edit_message_text(
        f"✅ **الخدمة المختارة:** {service_name}\n\n"
        f"📌 **اختر نوع التعديل المطلوب:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ============================================================
#  معالج اختيار التعديل
# ============================================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("service_"):
        await choose_service(update, context)
        return
    
    if data.startswith("edit_"):
        edit_type = data.replace("edit_", "")
        context.user_data["edit_type"] = edit_type
        
        edit_name = EDIT_OPTIONS[edit_type]["name"]
        edit_desc = EDIT_OPTIONS[edit_type]["desc"]
        
        await query.edit_message_text(
            f"✅ **تم اختيار التعديل:** {edit_name}\n"
            f"📝 **الوصف:** {edit_desc}\n\n"
            f"📸 **الآن أرسل الصورة التي تريد تعديلها.**"
        )

# ============================================================
#  معالج الصور
# ============================================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    edit_type = context.user_data.get("edit_type", "grayscale")
    service = context.user_data.get("service", "local")
    
    edit_name = EDIT_OPTIONS[edit_type]["name"]
    service_name = SERVICES[service]["name"]
    
    status_msg = await update.message.reply_text(
        f"⚡ جاري تطبيق **{edit_name}** عبر **{service_name}**..."
    )
    
    try:
        # تحميل الصورة
        photo_file = await update.message.photo[-1].get_file()
        image_data = await photo_file.download_as_bytearray()
        
        # فتح الصورة باستخدام Pillow
        image = Image.open(io.BytesIO(image_data))
        
        # ============================================================
        #  تطبيق التعديل المطلوب (معالجة محلية)
        # ============================================================
        if edit_type == "remove_clothes":
            # محاكاة إزالة الملابس: تأثير فني (تغيير الألوان)
            image = image.convert("RGBA")
            data = image.getdata()
            new_data = []
            for item in data:
                # تأثير عشوائي: تغيير التدرج اللوني
                new_data.append((item[0] + 50, item[1] + 30, item[2] + 20, item[3]))
            image.putdata(new_data)
            
        elif edit_type == "nsfw_content":
            # محاكاة محتوى جنسي: تأثيرات فنية
            image = image.convert("RGBA")
            data = image.getdata()
            new_data = []
            for item in data:
                # تأثير توهج
                r = min(255, item[0] + 80)
                g = min(255, item[1] + 40)
                b = min(255, item[2] + 20)
                new_data.append((r, g, b, item[3]))
            image.putdata(new_data)
            
        elif edit_type == "video_gen":
            # محاكاة تحويل إلى فيديو: إضافة إطار
            image = image.convert("RGB")
            image = image.filter(ImageFilter.GaussianBlur(radius=2))
            # إضافة إطار وهمي
            image = ImageEnhance.Sharpness(image).enhance(1.5)
            
        elif edit_type == "grayscale":
            image = image.convert("L")
            
        elif edit_type == "blur":
            image = image.filter(ImageFilter.GaussianBlur(radius=5))
            
        elif edit_type == "enhance":
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            
        elif edit_type == "resize":
            image = image.resize((500, 500))
            
        elif edit_type == "rotate":
            image = image.rotate(90, expand=True)
            
        elif edit_type == "mirror":
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        
        # حفظ الصورة المعدلة في الذاكرة
        output = io.BytesIO()
        image.save(output, format="JPEG")
        output.seek(0)
        
        # ============================================================
        #  إرسال الصورة المعدلة مع رسالة توضيحية
        # ============================================================
        await update.message.reply_photo(
            photo=output,
            caption=f"✅ **تم التعديل بنجاح!**\n\n"
                    f"🛠️ **التعديل:** {edit_name}\n"
                    f"🖥️ **الخدمة:** {service_name}\n"
                    f"🔥 **جميع التعديلات مجانية بالكامل.**\n\n"
                    f"⚠️ **تنبيه:** هذه محاكاة للتعديلات المطلوبة. للحصول على نتائج حقيقية، يلزم ربط الخدمات المدفوعة.",
            parse_mode="Markdown"
        )
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"خطأ أثناء معالجة الصورة: {e}")
        await status_msg.edit_text("❌ حدث خطأ أثناء معالجة الصورة.")

# ============================================================
#  تشغيل البوت
# ============================================================
def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN غير مضبوط!")
        sys.exit(1)

    # تشغيل خادم الإشارة في الخلفية
    threading.Thread(target=start_dummy_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    logger.info("🔥 البوت الأسطوري المجاني يعمل...")
    app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
