import os
import json
import time
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)

# -------------------------
# 1)  گرفتن توکن از متغیر محیطی
# -------------------------
# توکن رو دیگه اینجا نمی‌نویسیم!
# بعداً روی Render متغیر محیطی BOT_TOKEN رو ست می‌کنی.
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "متغیر محیطی BOT_TOKEN تنظیم نشده. "
        "لطفاً در محیط اجرا (مثلاً روی Render) متغیر BOT_TOKEN را ست کنید."
    )

# -------------------------
# 2)  تنظیمات تماس با دامپزشک
# -------------------------
VET_PHONE_NUMBER = os.getenv("VET_PHONE_NUMBER", "09xxxxxxxxx")
VET_CHAT_LINK = os.getenv("VET_CHAT_LINK", "@YourVetUsername")

# -------------------------
# منوی اصلی با دکمه «شروع»
# -------------------------
MAIN_MENU = ReplyKeyboardMarkup(
    [["شروع"]],
    resize_keyboard=True
)

# منوی بعد از نتیجه تریاژ
POST_RESULT_MENU = ReplyKeyboardMarkup(
    [
        ["شروع مجدد"],
        ["درخواست تماس با دامپزشک", "درخواست چت آنلاین با دامپزشک"],
    ],
    resize_keyboard=True
)

# -------------------------
# 3)  تعریف استیت‌ها
# -------------------------
(
    PET_SPECIES,
    PET_NAME,
    PET_AGE,
    PET_WEIGHT,
    PET_CONDITIONS,
    CHIEF_COMPLAINT,
    FOLLOWUP_1,
    FOLLOWUP_2,
    FOLLOWUP_3,
) = range(9)

# -------------------------
# 4)  پوشه‌های ذخیره‌سازی
# -------------------------
BASE_DIR = "data"
PETS_DIR = os.path.join(BASE_DIR, "pets")
CASES_DIR = os.path.join(BASE_DIR, "cases")

os.makedirs(PETS_DIR, exist_ok=True)
os.makedirs(CASES_DIR, exist_ok=True)


# -------------------------
# ذخیره پروفایل حیوان
# -------------------------
def save_pet_profile(user_id: int, pet_data: dict) -> str:
    timestamp = int(time.time())
    pet_id = f"{user_id}_{timestamp}"
    pet_data_with_meta = {
        "pet_id": pet_id,
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        **pet_data,
    }
    filename = os.path.join(PETS_DIR, f"{pet_id}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(pet_data_with_meta, f, ensure_ascii=False, indent=2)
    return pet_id


# -------------------------
# ذخیره کیس تریاژ
# -------------------------
def save_case(user_id: int, pet_id: str, case_data: dict) -> str:
    timestamp = int(time.time())
    case_id = f"{user_id}_{timestamp}"
    case_data_with_meta = {
        "case_id": case_id,
        "user_id": user_id,
        "pet_id": pet_id,
        "created_at": datetime.utcnow().isoformat(),
        **case_data,
    }
    filename = os.path.join(CASES_DIR, f"{case_id}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(case_data_with_meta, f, ensure_ascii=False, indent=2)
    return case_id


# -------------------------
# دسته‌بندی خودکار شکایت (Rule-based)
# -------------------------
def classify_complaint(text: str) -> str:
    """
    متن شکایت را بر اساس کلمات کلیدی ساده، به یکی از دسته‌های:
    GI, RESP, GENERAL نگاشت می‌کند.
    """
    t = text.replace("‌", " ").lower()

    gi_keywords = [
        "استفراغ", "بالا میاره", "بالا آورد", "بالا آوردن", "تهوع",
        "اسهال", "دل درد", "دل‌درد", "شکم درد", "شکم", "یبوست",
        "نفخ", "بی اشتها", "بی‌اشتهایی", "اشتهاش کم", "مدفوع"
    ]

    resp_keywords = [
        "سرفه", "سرفه می کند", "سرفه می‌کند",
        "نفس نفس", "نفس‌نفس", "نفس تند", "تنگی نفس",
        "خس خس", "خس‌خس", "صدای سینه", "تنفس سخت", "دهان باز"
    ]

    general_keywords = [
        "بی حال", "بی‌حال", "بیحاله", "کسل",
        "کم انرژی", "بی انرژی", "بی‌انرژی",
        "تب", "داغه", "لرزش", "می لرزه", "میلرزه",
        "نمی خوره", "نمی‌خوره", "اشتها نداره", "اشتهاش قطع شده",
        "خواب آلود", "خواب‌آلود", "زیاد می خوابه", "زیاد می‌خوابه"
    ]

    def count_hits(keywords):
        return sum(1 for k in keywords if k in t)

    gi_score = count_hits(gi_keywords)
    resp_score = count_hits(resp_keywords)
    gen_score = count_hits(general_keywords)

    scores = {"GI": gi_score, "RESP": resp_score, "GENERAL": gen_score}
    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]

    if best_score == 0:
        return "GENERAL"

    return best_cat


# -------------------------
# تریاژ ساده
# -------------------------
def simple_triage(context: CallbackContext) -> dict:
    """
    بر اساس دسته علائم و سه جواب، یک تریاژ ساده انجام می‌دهد.
    """
    cat = context.user_data.get("symptom_category")
    f1 = context.user_data.get("followup_1_answer", "")
    f2 = context.user_data.get("followup_2_answer", "")
    f3 = context.user_data.get("followup_3_answer", "")

    triage_level = "home_care"
    reasons = []
    advice = ""

    # =====================
    #  GI – گوارشی
    # =====================
    if cat == "GI":
        if "خون" in f2:
            triage_level = "visit_soon"
            reasons.append("وجود خون در استفراغ یا مدفوع می‌تواند نشانه مشکل جدی باشد.")

        if "۳ بار" in f1 or "سه بار" in f1 or "بیشتر" in f1:
            triage_level = "visit_soon"
            reasons.append("استفراغ/اسهال مکرر در ۲۴ ساعت نیازمند بررسی دامپزشکی است.")

        if "نمی‌خورد" in f3 or "نمی‌نوشد" in f3:
            triage_level = "visit_soon"
            reasons.append("کاهش شدید خوردن و نوشیدن می‌تواند باعث کم‌آبی و بدتر شدن وضعیت شود.")

        if triage_level == "home_care":
            reasons.append("در حال حاضر علامت واضح اورژانسی گزارش نشده است.")
            advice = (
                "فعلاً می‌توان با مراقبت خانگی حیوان را تحت نظر گرفت:\n"
                "• ۱۲ ساعت غذای جامد را قطع کنید اما آب در دسترس باشد.\n"
                "• اگر استفراغ/اسهال ادامه‌دار شد یا بدتر شد، حتماً برای معاینه حضوری مراجعه کنید.\n"
                "• در صورت مشاهده خون، بی‌حالی شدید یا قطع کامل خوردن/نوشیدن، مراجعه اورژانسی لازم است."
            )
        else:
            advice = (
                "با توجه به توضیحات شما، بهتر است در اولین فرصت (امروز یا حداکثر فردا) "
                "برای معاینه حضوری دامپزشکی مراجعه کنید.\n"
                "در صورت بدتر شدن علائم، مراجعه اورژانسی را در نظر بگیرید."
            )

    # =====================
    # RESP – تنفسی
    # =====================
    elif cat == "RESP":
        if "کبود" in f2 or "خیلی سفید" in f2 or "خیلی سفيد" in f2:
            triage_level = "emergency"
            reasons.append("تغییر رنگ لثه‌ها به سمت کبود/خیلی سفید می‌تواند نشانه کمبود اکسیژن یا شوک باشد.")

        if "دهان باز" in f2:
            triage_level = "emergency"
            reasons.append("تنفس با دهان باز در حالت استراحت می‌تواند علامت اورژانسی باشد.")

        if "زمین‌گیر" in f3 or "غش" in f3:
            triage_level = "emergency"
            reasons.append("بی‌ثباتی وضعیت عمومی و عدم توانایی حرکت می‌تواند بسیار خطرناک باشد.")

        if triage_level == "emergency":
            advice = (
                "این وضعیت به‌عنوان اورژانس تنفسی در نظر گرفته می‌شود.\n"
                "• در اسرع وقت به نزدیک‌ترین مرکز دامپزشکی مراجعه کنید.\n"
                "• از وارد کردن استرس و جابجایی غیرضروری خودداری کنید.\n"
                "• حیوان را در وضعیت راحت و با حداقل فشار روی قفسه سینه نگه دارید."
            )
        else:
            triage_level = "visit_soon"
            reasons.append("علائم تنفسی معمولاً نیازمند معاینه نسبتاً سریع دامپزشکی هستند.")
            advice = (
                "در حال حاضر علائم نیازمند معاینه نسبتاً سریع دامپزشکی هستند.\n"
                "توصیه می‌شود امروز یا در اولین فرصت برای معاینه حضوری مراجعه کنید.\n"
                "در صورت بدتر شدن تنفس، کبودی لثه‌ها یا بی‌حالی شدید، مراجعه اورژانسی لازم است."
            )

    # =====================
    # GENERAL – عمومی / نامشخص
    # =====================
    else:
        if "شدید" in f1:
            triage_level = "visit_soon"
            reasons.append("بی‌حالی شدید نیازمند معاینه حضوری است.")

        if "نمی‌خورد" in f2:
            triage_level = "visit_soon"
            reasons.append("قطع اشتها برای بیش از ۲۴ ساعت (خصوصاً در گربه‌ها) می‌تواند خطرناک باشد.")

        if triage_level == "home_care":
            reasons.append(
                "علائم توصیف‌شده در حال حاضر بیشتر خفیف تا متوسط هستند و می‌توانند تحت نظر گرفته شوند."
            )
            advice = (
                "فعلاً می‌توانید حیوان را در منزل تحت نظر نگه دارید.\n"
                "اگر بی‌حالی بیش از ۲۴ ساعت ادامه داشت یا علائم جدیدی اضافه شد "
                "(استفراغ، اسهال، تنفس غیرطبیعی)، برای معاینه حضوری مراجعه کنید."
            )
        else:
            advice = (
                "با توجه به توضیحات شما، بهتر است در اولین فرصت برای معاینه حضوری "
                "به دامپزشک مراجعه کنید تا علت بی‌حالی بررسی شود."
            )

    return {
        "triage_level": triage_level,
        "reasons": reasons,
        "advice": advice,
    }


# -------------------------
# منوی اصلی و شروع
# -------------------------
def main_menu(update: Update, context: CallbackContext):
    update.message.reply_text(
        "برای شروع ارزیابی حیوان خانگی، روی دکمه «شروع» بزن.",
        reply_markup=MAIN_MENU,
    )


def start(update: Update, context: CallbackContext):
    main_menu(update, context)
    return ConversationHandler.END


def begin_registration(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()
    reply_keyboard = [["سگ", "گربه"]]

    update.message.reply_text(
        "خیلی خوب، از ابتدا شروع می‌کنیم 🌱\n\n"
        "گونه حیوان رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return PET_SPECIES


# -------------------------
# مراحل گفتگو
# -------------------------
def pet_species(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()

    if text not in ["سگ", "گربه"]:
        update.message.reply_text("لطفاً فقط یکی از گزینه‌ها رو انتخاب کن: سگ یا گربه.")
        return PET_SPECIES

    context.user_data["pet_species"] = "dog" if text == "سگ" else "cat"
    update.message.reply_text(
        "اسم حیوانت چیه؟",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PET_NAME


def pet_name(update: Update, context: CallbackContext) -> int:
    context.user_data["pet_name"] = update.message.text.strip()
    update.message.reply_text("سن تقریبی حیوان چقدره؟ (مثلاً: ۲ سال، ۸ ماه)")
    return PET_AGE


def pet_age(update: Update, context: CallbackContext) -> int:
    context.user_data["pet_age"] = update.message.text.strip()
    update.message.reply_text("وزن حدودی حیوان چقدره؟ (به کیلوگرم، مثلاً: ۴.۵)")
    return PET_WEIGHT


def pet_weight(update: Update, context: CallbackContext) -> int:
    context.user_data["pet_weight"] = update.message.text.strip()
    update.message.reply_text(
        "آیا بیماری زمینه‌ای مهمی داره؟ (مثلاً بیماری قلبی، کلیوی و ...)\n"
        "اگر نداره بنویس: نداره"
    )
    return PET_CONDITIONS


def pet_conditions(update: Update, context: CallbackContext) -> int:
    context.user_data["pet_conditions"] = update.message.text.strip()

    # ذخیره پروفایل حیوان
    user_id = update.effective_user.id
    pet_profile = {
        "species": context.user_data.get("pet_species"),
        "name": context.user_data.get("pet_name"),
        "age": context.user_data.get("pet_age"),
        "weight": context.user_data.get("pet_weight"),
        "chronic_conditions": context.user_data.get("pet_conditions"),
    }
    pet_id = save_pet_profile(user_id, pet_profile)
    context.user_data["pet_id"] = pet_id

    update.message.reply_text(
        "خیلی هم خوب ✅\n"
        "حالا لطفاً مشکل فعلی حیوانت رو کامل برام توضیح بده.\n"
        "هرچیزی به ذهنت می‌رسه بنویس: از کی شروع شده، چه علامت‌هایی داره، رفتارش چطوره و ..."
    )
    return CHIEF_COMPLAINT


def chief_complaint(update: Update, context: CallbackContext) -> int:
    complaint_text = update.message.text.strip()
    context.user_data["chief_complaint"] = complaint_text

    cat = classify_complaint(complaint_text)
    context.user_data["symptom_category"] = cat

    if cat == "GI":
        update.message.reply_text(
            "بر اساس توضیحاتت، به‌نظر می‌رسه مشکل بیشتر در دسته علائم گوارشی باشه.\n"
            "الان چند سؤال دقیق‌تر می‌پرسم:"
        )
        reply_keyboard = [
            ["۱-۲ بار", "۳ بار یا بیشتر"],
            ["نمی‌دانم"],
        ]
        update.message.reply_text(
            "در ۲۴ ساعت گذشته تقریباً چند بار استفراغ یا اسهال داشته؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_1

    elif cat == "RESP":
        update.message.reply_text(
            "بر اساس توضیحت، احتمالاً با علائم تنفسی طرف هستیم.\n"
            "الان چند سؤال دقیق‌تر می‌پرسم:"
        )
        reply_keyboard = [
            ["تنفس فقط تندتر شده"],
            ["سختی واضح در نفس کشیدن"],
            ["نمی‌دانم"],
        ]
        update.message.reply_text(
            "تنفس حیوان را چطور توصیف می‌کنی؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_1

    else:
        update.message.reply_text(
            "از توضیحت برمی‌آد بیشتر با علائم عمومی/سیستمی (بی‌حالی، تغییر اشتها و ...) طرف هستیم.\n"
            "چند سؤال تکمیلی می‌پرسم:"
        )
        reply_keyboard = [
            ["بی‌حالی خفیف"],
            ["بی‌حالی متوسط"],
            ["بی‌حالی شدید"],
        ]
        update.message.reply_text(
            "شدت بی‌حالی را چطور ارزیابی می‌کنی؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_1


def followup_1(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip()
    context.user_data["followup_1_answer"] = answer

    cat = context.user_data.get("symptom_category")

    if cat == "GI":
        reply_keyboard = [
            ["خون ندیدم"],
            ["رد خون دیدم"],
            ["مشکوکم / مطمئن نیستم"],
        ]
        update.message.reply_text(
            "تا جایی که دیدی، در استفراغ یا مدفوع خون وجود داشته؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_2

    elif cat == "RESP":
        reply_keyboard = [
            ["دهان بسته / رنگ لثه‌ها طبیعی است"],
            ["نفس‌نفس با دهان باز"],
            ["لب‌ها یا لثه‌ها کبود یا خیلی سفید به‌نظر می‌رسند"],
        ]
        update.message.reply_text(
            "وضعیت دهان و لثه‌ها چطوره؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_2

    else:
        reply_keyboard = [
            ["اشتها طبیعی است"],
            ["اشتها کمتر از معمول شده"],
            ["تقریباً نمی‌خورد"],
        ]
        update.message.reply_text(
            "اشتها در این یکی‌دو روز چطور بوده؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_2


def followup_2(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip()
    context.user_data["followup_2_answer"] = answer

    cat = context.user_data.get("symptom_category")

    if cat == "GI":
        reply_keyboard = [
            ["می‌خورد و می‌نوشد"],
            ["کمتر از معمول می‌خورد/می‌نوشد"],
            ["تقریباً نمی‌خورد و نمی‌نوشد"],
        ]
        update.message.reply_text(
            "در حال حاضر وضعیت خوردن و نوشیدن چطوره؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_3

    elif cat == "RESP":
        reply_keyboard = [
            ["راه می‌رود و رفتار نسبتاً طبیعی دارد"],
            ["بی‌حال و کم‌تحرک شده"],
            ["زمین‌گیر شده / گاهی انگار غش می‌کند"],
        ]
        update.message.reply_text(
            "از نظر توان حرکت و وضعیت عمومی چطور است؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_3

    else:
        reply_keyboard = [
            ["هیچ علامت دیگری ندیدم"],
            ["استفراغ یا اسهال هم دارد"],
            ["سرفه/عطسه یا علائم تنفسی دارد"],
            ["سایر علائم (مثلاً لنگش، درد موضعی و ...)"],
        ]
        update.message.reply_text(
            "آیا علامت دیگری هم همراه بی‌حالی وجود دارد؟",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return FOLLOWUP_3


def followup_3(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip()
    context.user_data["followup_3_answer"] = answer

    user_id = update.effective_user.id
    pet_id = context.user_data.get("pet_id")

    triage_result = simple_triage(context)
    triage_level = triage_result["triage_level"]
    reasons = triage_result["reasons"]
    advice = triage_result["advice"]

    case_data = {
        "chief_complaint": context.user_data.get("chief_complaint"),
        "symptom_category": context.user_data.get("symptom_category"),
        "followup_1_answer": context.user_data.get("followup_1_answer"),
        "followup_2_answer": context.user_data.get("followup_2_answer"),
        "followup_3_answer": context.user_data.get("followup_3_answer"),
        "triage_level": triage_level,
        "triage_reasons": reasons,
    }

    case_id = save_case(user_id, pet_id, case_data)

    if triage_level == "emergency":
        level_text = "🔴 سطح تریاژ: اورژانسی"
    elif triage_level == "visit_soon":
        level_text = "🟠 سطح تریاژ: نیازمند ویزیت در اولین فرصت"
    else:
        level_text = "🟢 سطح تریاژ: قابل پیگیری با مراقبت خانگی (در حال حاضر)"

    reasons_text = "\n".join([f"• {r}" for r in reasons]) if reasons else "—"

    update.message.reply_text(
        f"{level_text}\n\n"
        f"شناسه این پرونده:\n{case_id}\n\n"
        f"دلایل این ارزیابی:\n{reasons_text}\n\n"
        f"{advice}\n\n"
        "اگر دوست داری می‌تونی از همین‌جا:\n"
        "• یک مورد جدید را شروع کنی\n"
        "• یا برای مشاوره مستقیم با دامپزشک درخواست تماس/چت بدهی.",
        reply_markup=POST_RESULT_MENU,
    )

    context.user_data.clear()
    return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "فرایند ثبت اطلاعات متوقف شد. هر زمان خواستی دوباره /start رو بزن.",
        reply_markup=MAIN_MENU,
    )
    context.user_data.clear()
    return ConversationHandler.END


# -------------------------
# درخواست تماس / چت
# -------------------------
def request_call(update: Update, context: CallbackContext):
    update.message.reply_text(
        "در نسخه فعلی، امکان اتصال خودکار به دامپزشک هنوز به‌صورت کامل راه‌اندازی نشده.\n\n"
        "برای تماس تلفنی با دامپزشک، لطفاً با شماره زیر تماس بگیر:\n"
        f"{VET_PHONE_NUMBER}\n\n"
        "در نسخه‌های بعدی، این دکمه شما را به دامپزشک آن‌کال متصل خواهد کرد. 🩺"
    )


def request_chat(update: Update, context: CallbackContext):
    update.message.reply_text(
        "در نسخه فعلی، برای شروع چت آنلاین با دامپزشک، می‌تونی از این لینک/یوزرنیم استفاده کنی:\n"
        f"{VET_CHAT_LINK}\n\n"
        "در نسخه‌های بعدی، چت آنلاین مستقیماً از داخل همین بات انجام خواهد شد. 💬"
    )


# -------------------------
# اجرای اصلی بات
# -------------------------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                Filters.regex("^(شروع|شروع مجدد)$"), begin_registration
            )
        ],
        states={
            PET_SPECIES: [MessageHandler(Filters.text & ~Filters.command, pet_species)],
            PET_NAME: [MessageHandler(Filters.text & ~Filters.command, pet_name)],
            PET_AGE: [MessageHandler(Filters.text & ~Filters.command, pet_age)],
            PET_WEIGHT: [MessageHandler(Filters.text & ~Filters.command, pet_weight)],
            PET_CONDITIONS: [
                MessageHandler(Filters.text & ~Filters.command, pet_conditions)
            ],
            CHIEF_COMPLAINT: [
                MessageHandler(Filters.text & ~Filters.command, chief_complaint)
            ],
            FOLLOWUP_1: [
                MessageHandler(Filters.text & ~Filters.command, followup_1)
            ],
            FOLLOWUP_2: [
                MessageHandler(Filters.text & ~Filters.command, followup_2)
            ],
            FOLLOWUP_3: [
                MessageHandler(Filters.text & ~Filters.command, followup_3)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("menu", main_menu))

    dp.add_handler(
        MessageHandler(
            Filters.regex("^درخواست تماس با دامپزشک$"), request_call
        )
    )
    dp.add_handler(
        MessageHandler(
            Filters.regex("^درخواست چت آنلاین با دامپزشک$"), request_chat
        )
    )

    print("Bot is running...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
