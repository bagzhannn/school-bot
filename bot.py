"""
╔══════════════════════════════════════════════════════════════════╗
║          МЕКТЕП ҚАУІПСІЗДІГІ БОТЫ / ШКОЛЬНЫЙ БОТ               ║
║          Школьная анонимная система обратной связи               ║
╚══════════════════════════════════════════════════════════════════╝

Установка:
    pip install aiogram python-dotenv

.env файл:
    BOT_TOKEN=8732561509:AAHsP1DbdAZ3Dr8idyjow97CNHCki4VkS9k
    ADMIN_IDS=6751410899
    URGENT_ADMIN_IDS=6751410899
    DB_PATH=school_bot.db
    ATTACH_DIR=attachments

Запуск:
    python bot.py

Команды для администраторов:
    /admin_cases            — последние 10 дел
    /admin_case CASE-ID     — полная информация о деле
    /set_status CASE-ID статус  — изменить статус
    /note CASE-ID текст     — добавить заметку
    /stats                  — статистика за всё время
    /export_today           — список дел за сегодня
"""

import asyncio
import logging
import os
import random
import sqlite3
import string
from datetime import datetime, date
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────── CONFIG ────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "school_bot.db")
ATTACH_DIR = os.getenv("ATTACH_DIR", "attachments")

ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]
URGENT_ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("URGENT_ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# Статусы дел (для команды /set_status)
VALID_STATUSES = ["new", "viewed", "investigating", "contacted", "resolved", "closed"]

Path(ATTACH_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ─────────────────────────── CONSTANTS ─────────────────────────────

RU = "ru"
KK = "kk"

TEXTS = {
    "choose_lang": {
        RU: "Выберите язык:",
        KK: "Тілді таңдаңыз:",
    },
    "welcome": {
        RU: (
            "🛡 <b>Школьная система анонимных обращений</b>\n\n"
            "Вы можете анонимно или открыто сообщить о буллинге, угрозах, "
            "насилии, вымогательстве, кибербуллинге и других проблемах.\n\n"
            "🔒 Ваши данные надёжно защищены. Анонимные обращения не раскрывают вашу личность."
        ),
        KK: (
            "🛡 <b>Мектептің анонимді өтініш жүйесі</b>\n\n"
            "Сіз буллинг, қорқыту, зорлық, бопсалау, кибербуллинг және басқа "
            "мәселелер туралы анонимді не ашық түрде хабарлай аласыз.\n\n"
            "🔒 Деректеріңіз сенімді қорғалған. Анонимді өтініштер жеке басыңызды ашпайды."
        ),
    },
    "choose_mode": {
        RU: "Выберите формат обращения:",
        KK: "Өтініш түрін таңдаңыз:",
    },
    "choose_category": {
        RU: "Выберите тип ситуации:",
        KK: "Жағдай түрін таңдаңыз:",
    },
    "ask_event_time": {
        RU: "📅 <b>Когда произошел инцидент?</b>\nНапример: сегодня утром, вчера в 14:00, 18 апреля.",
        KK: "📅 <b>Оқиға қашан болды?</b>\nМысалы: бүгін таңертең, кеше 14:00-де, 18 сәуірде.",
    },
    "ask_location": {
        RU: "📍 <b>Где это произошло?</b>\nНапример: спортзал, столовая, класс 7А, WhatsApp.",
        KK: "📍 <b>Бұл қай жерде болды?</b>\nМысалы: спорт залы, асхана, 7А сыныбы, WhatsApp.",
    },
    "ask_people": {
        RU: (
            "👤 <b>Кто был участником ситуации?</b>\n"
            "Если не знаете точно — напишите класс, описание внешности или прозвище. "
            "Для анонимного обращения вы не обязаны называть точные имена."
        ),
        KK: (
            "👤 <b>Оқиғаға кімдер қатысты?</b>\n"
            "Нақты білмесеңіз — сыныбын, сыртқы белгілерін немесе лақап атын жазыңыз. "
            "Анонимді өтініште нақты есімдерді атауға міндетті емессіз."
        ),
    },
    "ask_description": {
        RU: (
            "📝 <b>Опишите, что произошло.</b>\n"
            "Чем подробнее, тем лучше школа сможет разобраться и помочь. "
            "Пишите всё, что считаете важным."
        ),
        KK: (
            "📝 <b>Не болғанын толық жазыңыз.</b>\n"
            "Неғұрлым нақты жазсаңыз, мектеп соғұрлым жақсы тексеріп, көмектесе алады. "
            "Маңызды деп санайтын барлығын жазыңыз."
        ),
    },
    "ask_ongoing": {
        RU: "🔄 <b>Это продолжается сейчас или происходит регулярно?</b>",
        KK: "🔄 <b>Бұл жағдай қазір де жалғасып жатыр ма немесе жүйелі түрде болып тұра ма?</b>",
    },
    "ask_urgent": {
        RU: "🚨 <b>Это срочная ситуация, требующая немедленного вмешательства?</b>",
        KK: "🚨 <b>Бұл дереу ден қоюды қажет ететін шұғыл жағдай ма?</b>",
    },
    "ask_reporter_name": {
        RU: "✏️ Напишите ваше <b>имя и фамилию</b>:",
        KK: "✏️ <b>Аты-жөніңізді</b> жазыңыз:",
    },
    "ask_reporter_class": {
        RU: "🏫 Напишите ваш <b>класс</b> (например, 8Б):",
        KK: "🏫 <b>Сыныбыңызды</b> жазыңыз (мысалы, 8Б):",
    },
    "ask_reporter_contact": {
        RU: "📱 Напишите <b>контакт для связи</b> (номер телефона, Telegram username или @):",
        KK: "📱 <b>Байланыс мекенжайыңызды</b> жазыңыз (телефон нөмірі, Telegram username немесе @):",
    },
    "ask_attachment": {
        RU: (
            "📎 <b>Хотите прикрепить доказательства?</b>\n\n"
            "Вы можете отправить:\n"
            "• Фото\n• Видео\n• Скриншот\n• Голосовое сообщение\n• Документ\n\n"
            "Для нескольких файлов — отправляйте по одному. "
            'После отправки всех файлов нажмите <b>"Завершить"</b>.\n'
            'Если доказательств нет — нажмите <b>"Пропустить"</b>.'
        ),
        KK: (
            "📎 <b>Дәлелдер тіркегіңіз келе ме?</b>\n\n"
            "Жіберуге болады:\n"
            "• Фото\n• Видео\n• Скриншот\n• Дауыстық хабарлама\n• Құжат\n\n"
            "Бірнеше файл болса — біртіндеп жіберіңіз. "
            'Барлығын жіберіп болған соң <b>"Аяқтау"</b> түймесін басыңыз.\n'
            'Дәлел жоқ болса — <b>"Өткізу"</b> түймесін басыңыз.'
        ),
    },
    "fake_report_warning": {
        RU: (
            "⚠️ <i>Пожалуйста, сообщайте только достоверную информацию. "
            "Ложные обвинения мешают защите учащихся и нарушают права других людей.</i>"
        ),
        KK: (
            "⚠️ <i>Тек шынайы ақпарат жіберуіңізді сұраймыз. "
            "Жалған айыптау оқушыларды қорғау жұмысына кедергі келтіріп, басқалардың құқығын бұзады.</i>"
        ),
    },
    "urgent_notice": {
        RU: (
            "🆘 <b>Если вам угрожает немедленная опасность:</b>\n"
            "Немедленно обратитесь к дежурному учителю, классному руководителю, "
            "родителям или позвоните по номеру 112."
        ),
        KK: (
            "🆘 <b>Егер сізге дәл қазір қауіп төніп тұрса:</b>\n"
            "Бірден кезекші мұғалімге, сынып жетекшісіне, "
            "ата-анаңызға хабарласыңыз немесе 112 нөміріне қоңырау шалыңыз."
        ),
    },
}

CATEGORIES = {
    "bullying":    {RU: "🥊 Буллинг",               KK: "🥊 Буллинг"},
    "fight":       {RU: "⚔️ Драка",                  KK: "⚔️ Төбелес"},
    "threat":      {RU: "😠 Угроза",                 KK: "😠 Қоқан-лоқы"},
    "cyber":       {RU: "📱 Кибербуллинг",           KK: "📱 Кибербуллинг"},
    "extortion":   {RU: "💰 Вымогательство",         KK: "💰 Бопсалау"},
    "harassment":  {RU: "🚫 Домогательство",         KK: "🚫 Әдепсіз әрекет"},
    "crisis":      {RU: "💙 Психологический кризис", KK: "💙 Психологиялық дағдарыс"},
    "other":       {RU: "❓ Другое",                  KK: "❓ Басқа"},
}

MODES = {
    "anonymous": {RU: "🔒 Анонимно",          KK: "🔒 Анонимді"},
    "named":     {RU: "👤 Личное обращение",   KK: "👤 Ашық өтініш"},
    "witness":   {RU: "👀 Я свидетель",        KK: "👀 Мен куәгермін"},
}

STATUS_LABELS = {
    "new":           "🆕 Новое",
    "viewed":        "👁 Просмотрено",
    "investigating": "🔍 Расследуется",
    "contacted":     "📞 Связались с учеником",
    "resolved":      "✅ Решено",
    "closed":        "🔒 Закрыто",
}


# ─────────────────────────── FSM STATES ────────────────────────────

class ReportFSM(StatesGroup):
    choosing_language  = State()
    choosing_mode      = State()
    choosing_category  = State()
    event_time         = State()
    location           = State()
    people             = State()
    description        = State()
    ongoing            = State()
    urgent             = State()
    reporter_name      = State()
    reporter_class     = State()
    reporter_contact   = State()
    attachment         = State()
    checking_case_id   = State()
    checking_secret    = State()


# ─────────────────────────── DATABASE ──────────────────────────────

def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id          TEXT UNIQUE,
            secret_code      TEXT,
            report_mode      TEXT,
            language         TEXT,
            category         TEXT,
            event_time       TEXT,
            location         TEXT,
            people_involved  TEXT,
            description      TEXT,
            ongoing          INTEGER,
            urgent           INTEGER,
            reporter_name    TEXT,
            reporter_class   TEXT,
            reporter_contact TEXT,
            status           TEXT DEFAULT 'new',
            admin_note       TEXT DEFAULT '',
            created_at       TEXT,
            updated_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id          TEXT,
            telegram_file_id TEXT,
            file_type        TEXT,
            file_name        TEXT,
            created_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id    TEXT,
            actor_id   INTEGER,
            action     TEXT,
            detail     TEXT,
            created_at TEXT
        );
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized: %s", DB_PATH)


def generate_case_id() -> str:
    now = datetime.now()
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"CASE-{now.strftime('%Y%m%d')}-{suffix}"


def generate_secret_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def save_report(data: dict) -> tuple[str, str]:
    case_id = generate_case_id()
    secret_code = generate_secret_code()
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reports (
            case_id, secret_code, report_mode, language, category, event_time,
            location, people_involved, description, ongoing, urgent,
            reporter_name, reporter_class, reporter_contact,
            status, admin_note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', '', ?, ?)
        """,
        (
            case_id, secret_code,
            data.get("report_mode"), data.get("language"),
            data.get("category"), data.get("event_time"),
            data.get("location"), data.get("people"),
            data.get("description"),
            1 if data.get("ongoing") else 0,
            1 if data.get("urgent") else 0,
            data.get("reporter_name"), data.get("reporter_class"),
            data.get("reporter_contact"),
            now, now,
        ),
    )
    # Сохраняем вложения
    for att in data.get("attachments", []):
        cur.execute(
            "INSERT INTO attachments (case_id, telegram_file_id, file_type, file_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (case_id, att["file_id"], att["type"], att.get("file_name", ""), now),
        )
    # Запись в аудит
    cur.execute(
        "INSERT INTO audit_logs (case_id, actor_id, action, detail, created_at) VALUES (?, ?, 'created', ?, ?)",
        (case_id, 0, f"New {data.get('report_mode')} report", now),
    )
    conn.commit()
    conn.close()
    return case_id, secret_code


def get_report(case_id: str, secret_code: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT case_id, status, updated_at, category, location, admin_note FROM reports WHERE case_id=? AND secret_code=?",
        (case_id, secret_code),
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_report_by_id(case_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports WHERE case_id=?", (case_id,))
    row = cur.fetchone()
    columns = [d[0] for d in cur.description] if cur.description else []
    conn.close()
    if row:
        return dict(zip(columns, row))
    return None


def update_status(case_id: str, status: str, actor_id: int):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE reports SET status=?, updated_at=? WHERE case_id=?", (status, now, case_id))
    cur.execute(
        "INSERT INTO audit_logs (case_id, actor_id, action, detail, created_at) VALUES (?, ?, 'status_changed', ?, ?)",
        (case_id, actor_id, f"Status → {status}", now),
    )
    conn.commit()
    conn.close()


def add_note(case_id: str, note: str, actor_id: int):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE reports SET admin_note=?, updated_at=? WHERE case_id=?", (note, now, case_id))
    cur.execute(
        "INSERT INTO audit_logs (case_id, actor_id, action, detail, created_at) VALUES (?, ?, 'note_added', ?, ?)",
        (case_id, actor_id, note, now),
    )
    conn.commit()
    conn.close()


def get_recent_cases(limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT case_id, category, status, urgent, created_at FROM reports ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM reports")
    total = cur.fetchone()[0]
    cur.execute("SELECT category, COUNT(*) FROM reports GROUP BY category ORDER BY COUNT(*) DESC")
    by_cat = cur.fetchall()
    cur.execute("SELECT status, COUNT(*) FROM reports GROUP BY status")
    by_status = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM reports WHERE urgent=1")
    urgent = cur.fetchone()[0]
    conn.close()
    return total, by_cat, by_status, urgent


def get_cases_today():
    conn = get_conn()
    today = date.today().isoformat()
    cur = conn.cursor()
    cur.execute(
        "SELECT case_id, category, status, urgent, created_at FROM reports WHERE created_at LIKE ? ORDER BY id DESC",
        (f"{today}%",),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_attachments(case_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT file_type, telegram_file_id, file_name FROM attachments WHERE case_id=?", (case_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ─────────────────────────── KEYBOARDS ─────────────────────────────

def lang_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="lang:ru")
    kb.button(text="🇰🇿 Қазақша", callback_data="lang:kk")
    kb.adjust(2)
    return kb.as_markup()


def main_menu(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("🔒 Анонимное сообщение"    if lang == RU else "🔒 Анонимді хабарлама"),   callback_data="mode:anonymous")
    kb.button(text=("👤 Личное обращение"       if lang == RU else "👤 Ашық өтініш"),           callback_data="mode:named")
    kb.button(text=("👀 Я свидетель"            if lang == RU else "👀 Мен куәгермін"),         callback_data="mode:witness")
    kb.button(text=("🔍 Проверить статус"       if lang == RU else "🔍 Мәртебені тексеру"),     callback_data="check_status")
    kb.button(text=("📖 Инструкция"             if lang == RU else "📖 Нұсқаулық"),             callback_data="help_info")
    kb.adjust(1)
    return kb.as_markup()


def category_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, labels in CATEGORIES.items():
        kb.button(text=labels[lang], callback_data=f"cat:{key}")
    kb.adjust(2)
    return kb.as_markup()


def yes_no_kb(lang: str, prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("✅ Да"  if lang == RU else "✅ Иә"),  callback_data=f"{prefix}:yes")
    kb.button(text=("❌ Нет" if lang == RU else "❌ Жоқ"), callback_data=f"{prefix}:no")
    kb.adjust(2)
    return kb.as_markup()


def urgent_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("🚨 Срочно"    if lang == RU else "🚨 Шұғыл"),     callback_data="urg:yes")
    kb.button(text=("✅ Не срочно" if lang == RU else "✅ Шұғыл емес"), callback_data="urg:no")
    kb.adjust(2)
    return kb.as_markup()


def attachment_kb(lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=("⏭ Пропустить" if lang == RU else "⏭ Өткізу")))
    builder.add(KeyboardButton(text=("✅ Завершить"  if lang == RU else "✅ Аяқтау")))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def confirm_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("✅ Подтвердить и отправить" if lang == RU else "✅ Растап жіберу"), callback_data="confirm_send")
    kb.button(text=("🔄 Начать заново"           if lang == RU else "🔄 Қайта бастау"),  callback_data="restart")
    kb.adjust(1)
    return kb.as_markup()


# ─────────────────────────── HELPERS ───────────────────────────────

def admin_message(data: dict, case_id: str) -> str:
    cat = CATEGORIES.get(data.get("category", ""), {}).get(RU, data.get("category", "?"))
    mode = MODES.get(data.get("report_mode", ""), {}).get(RU, data.get("report_mode", "?"))
    urgent_icon = "🚨" if data.get("urgent") else "✅"
    ongoing_text = "Да" if data.get("ongoing") else "Нет"
    attachments_count = len(data.get("attachments", []))

    return (
        f"{'🚨🚨🚨 СРОЧНО! ' if data.get('urgent') else ''}📨 <b>НОВОЕ ОБРАЩЕНИЕ</b>\n\n"
        f"<b>Case ID:</b> <code>{case_id}</code>\n"
        f"<b>Тип:</b> {cat}\n"
        f"<b>Формат:</b> {mode}\n"
        f"<b>Срочность:</b> {urgent_icon}\n"
        f"<b>Продолжается:</b> {ongoing_text}\n\n"
        f"<b>Время события:</b> {data.get('event_time', '—')}\n"
        f"<b>Место:</b> {data.get('location', '—')}\n"
        f"<b>Участники:</b> {data.get('people', '—')}\n\n"
        f"<b>Описание:</b>\n{data.get('description', '—')}\n\n"
        f"{'<b>Имя:</b> ' + str(data.get('reporter_name')) + chr(10) if data.get('reporter_name') else ''}"
        f"{'<b>Класс:</b> ' + str(data.get('reporter_class')) + chr(10) if data.get('reporter_class') else ''}"
        f"{'<b>Контакт:</b> ' + str(data.get('reporter_contact')) + chr(10) if data.get('reporter_contact') else ''}"
        f"\n<b>Вложений:</b> {attachments_count}\n"
        f"<b>Статус:</b> 🆕 NEW\n\n"
        f"Используйте /admin_case {case_id} для просмотра подробностей."
    )


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id in URGENT_ADMIN_IDS


def skip_words(lang: str) -> tuple[str, str]:
    if lang == RU:
        return "⏭ Пропустить", "✅ Завершить"
    return "⏭ Өткізу", "✅ Аяқтау"


# ─────────────────────────── HANDLERS ──────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ReportFSM.choosing_language)
    await message.answer("Выберите язык / Тілді таңдаңыз:", reply_markup=lang_kb())


@dp.callback_query(F.data.startswith("lang:"))
async def choose_lang(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split(":", 1)[1]
    await state.update_data(language=lang)
    await state.set_state(ReportFSM.choosing_mode)
    await callback.message.edit_text(TEXTS["welcome"][lang], reply_markup=main_menu(lang))
    await callback.answer()


@dp.callback_query(F.data == "help_info")
async def help_info(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", RU)
    text = (
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1. Выберите формат: анонимно, личное или свидетель\n"
        "2. Выберите тип события\n"
        "3. Заполните информацию по шагам\n"
        "4. При желании — прикрепите доказательства\n"
        "5. Получите номер обращения и секретный код\n"
        "6. По номеру + коду можно проверить статус\n\n"
        "Обращения получают уполномоченные сотрудники школы. "
        "Анонимность гарантируется."
        if lang == RU else
        "📖 <b>Ботты қалай пайдалануға болады:</b>\n\n"
        "1. Форматты таңдаңыз: анонимді, жеке немесе куәгер ретінде\n"
        "2. Оқиға түрін таңдаңыз\n"
        "3. Ақпаратты қадамма-қадам толтырыңыз\n"
        "4. Қаласаңыз — дәлелдер тіркеңіз\n"
        "5. Өтініш нөмірі мен құпия кодты алыңыз\n"
        "6. Нөмір + кодпен мәртебені тексере аласыз\n\n"
        "Өтініштерді мектептің уәкілетті қызметкерлері алады. "
        "Анонимдік кепілдендіріледі."
    )
    await callback.message.answer(text)
    await callback.answer()


@dp.callback_query(F.data == "restart")
async def restart(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ReportFSM.choosing_language)
    await callback.message.answer("Выберите язык / Тілді таңдаңыз:", reply_markup=lang_kb())
    await callback.answer()


@dp.callback_query(F.data.startswith("mode:"))
async def choose_mode(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = data["language"]
    await state.update_data(report_mode=mode)
    await state.set_state(ReportFSM.choosing_category)
    await callback.message.answer(
        TEXTS["fake_report_warning"][lang] + "\n\n" + TEXTS["choose_category"][lang],
        reply_markup=category_kb(lang),
    )
    await callback.answer()


@dp.callback_query(F.data == "check_status")
async def check_status_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", RU)
    await state.set_state(ReportFSM.checking_case_id)
    await callback.message.answer(
        "🔍 Введите <b>номер обращения</b> (Case ID):\nПример: CASE-20260421-1234"
        if lang == RU else
        "🔍 <b>Өтініш нөмірін</b> енгізіңіз (Case ID):\nМысалы: CASE-20260421-1234"
    )
    await callback.answer()


@dp.message(ReportFSM.checking_case_id)
async def get_case_id_input(message: Message, state: FSMContext):
    await state.update_data(check_case_id=message.text.strip().upper())
    data = await state.get_data()
    lang = data.get("language", RU)
    await state.set_state(ReportFSM.checking_secret)
    await message.answer(
        "🔑 Введите <b>секретный код</b>:"
        if lang == RU else
        "🔑 <b>Құпия кодты</b> енгізіңіз:"
    )


@dp.message(ReportFSM.checking_secret)
async def get_secret_input(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", RU)
    case_id = data.get("check_case_id", "")
    secret = message.text.strip().upper()
    row = get_report(case_id, secret)
    if not row:
        await message.answer(
            "❌ Обращение не найдено. Проверьте номер и код."
            if lang == RU else
            "❌ Өтініш табылмады. Нөмір мен кодты тексеріңіз."
        )
        await state.clear()
        return
    _, status, updated_at, category, location, admin_note = row
    cat_label = CATEGORIES.get(category, {}).get(lang, category)
    status_label = STATUS_LABELS.get(status, status)
    text = (
        f"📋 <b>Информация об обращении</b>\n\n"
        f"<b>Case ID:</b> <code>{case_id}</code>\n"
        f"<b>Тип:</b> {cat_label}\n"
        f"<b>Место:</b> {location}\n"
        f"<b>Статус:</b> {status_label}\n"
        f"<b>Обновлено:</b> {updated_at}\n"
        f"<b>Заметка:</b> {admin_note or '—'}"
        if lang == RU else
        f"📋 <b>Өтініш туралы ақпарат</b>\n\n"
        f"<b>Case ID:</b> <code>{case_id}</code>\n"
        f"<b>Түрі:</b> {cat_label}\n"
        f"<b>Орны:</b> {location}\n"
        f"<b>Мәртебесі:</b> {status_label}\n"
        f"<b>Жаңартылды:</b> {updated_at}\n"
        f"<b>Ескертпе:</b> {admin_note or '—'}"
    )
    await message.answer(text)
    await state.clear()


@dp.callback_query(F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.split(":", 1)[1]
    data = await state.get_data()
    lang = data["language"]
    await state.update_data(category=cat)
    await state.set_state(ReportFSM.event_time)
    # Специальное предупреждение для кризиса
    if cat == "crisis":
        await callback.message.answer(TEXTS["urgent_notice"][lang])
    await callback.message.answer(TEXTS["ask_event_time"][lang])
    await callback.answer()


@dp.message(ReportFSM.event_time)
async def got_event_time(message: Message, state: FSMContext):
    await state.update_data(event_time=message.text.strip())
    data = await state.get_data()
    await state.set_state(ReportFSM.location)
    await message.answer(TEXTS["ask_location"][data["language"]])


@dp.message(ReportFSM.location)
async def got_location(message: Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    data = await state.get_data()
    await state.set_state(ReportFSM.people)
    await message.answer(TEXTS["ask_people"][data["language"]])


@dp.message(ReportFSM.people)
async def got_people(message: Message, state: FSMContext):
    await state.update_data(people=message.text.strip())
    data = await state.get_data()
    await state.set_state(ReportFSM.description)
    await message.answer(TEXTS["ask_description"][data["language"]])


@dp.message(ReportFSM.description)
async def got_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    data = await state.get_data()
    lang = data["language"]
    await state.set_state(ReportFSM.ongoing)
    await message.answer(TEXTS["ask_ongoing"][lang], reply_markup=yes_no_kb(lang, "ongoing"))


@dp.callback_query(F.data.startswith("ongoing:"))
async def got_ongoing(callback: CallbackQuery, state: FSMContext):
    val = callback.data.endswith(":yes")
    data = await state.get_data()
    lang = data["language"]
    await state.update_data(ongoing=val)
    await state.set_state(ReportFSM.urgent)
    await callback.message.answer(TEXTS["ask_urgent"][lang], reply_markup=urgent_kb(lang))
    await callback.answer()


@dp.callback_query(F.data.startswith("urg:"))
async def got_urgent(callback: CallbackQuery, state: FSMContext):
    val = callback.data.endswith(":yes")
    data = await state.get_data()
    lang = data["language"]
    await state.update_data(urgent=val)

    if val:
        await callback.message.answer(TEXTS["urgent_notice"][lang])

    if data.get("report_mode") == "anonymous":
        await state.set_state(ReportFSM.attachment)
        await callback.message.answer(TEXTS["ask_attachment"][lang], reply_markup=attachment_kb(lang))
    else:
        await state.set_state(ReportFSM.reporter_name)
        await callback.message.answer(TEXTS["ask_reporter_name"][lang])
    await callback.answer()


@dp.message(ReportFSM.reporter_name)
async def got_reporter_name(message: Message, state: FSMContext):
    await state.update_data(reporter_name=message.text.strip())
    data = await state.get_data()
    await state.set_state(ReportFSM.reporter_class)
    await message.answer(TEXTS["ask_reporter_class"][data["language"]])


@dp.message(ReportFSM.reporter_class)
async def got_reporter_class(message: Message, state: FSMContext):
    await state.update_data(reporter_class=message.text.strip())
    data = await state.get_data()
    await state.set_state(ReportFSM.reporter_contact)
    await message.answer(TEXTS["ask_reporter_contact"][data["language"]])


@dp.message(ReportFSM.reporter_contact)
async def got_reporter_contact(message: Message, state: FSMContext):
    await state.update_data(reporter_contact=message.text.strip())
    data = await state.get_data()
    lang = data["language"]
    await state.set_state(ReportFSM.attachment)
    await message.answer(TEXTS["ask_attachment"][lang], reply_markup=attachment_kb(lang))


# Вложения — текстовые кнопки (пропустить / завершить)
@dp.message(ReportFSM.attachment, F.text)
async def attachment_text(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    skip_w, finish_w = skip_words(lang)

    if message.text in (skip_w, finish_w):
        await _finalize_report(message, state, data)
    else:
        await message.answer(
            "Пожалуйста, отправьте файл или нажмите кнопку."
            if lang == RU else
            "Файл жіберіңіз немесе түймені басыңыз."
        )


# Вложения — медиафайлы
@dp.message(
    ReportFSM.attachment,
    F.content_type.in_({ContentType.PHOTO, ContentType.VIDEO, ContentType.VOICE, ContentType.DOCUMENT}),
)
async def attachment_media(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data["language"]
    attachments = data.get("attachments", [])

    if message.photo:
        attachments.append({"type": "photo", "file_id": message.photo[-1].file_id, "file_name": "photo.jpg"})
    elif message.video:
        attachments.append({"type": "video", "file_id": message.video.file_id, "file_name": message.video.file_name or "video"})
    elif message.voice:
        attachments.append({"type": "voice", "file_id": message.voice.file_id, "file_name": "voice.ogg"})
    elif message.document:
        attachments.append({"type": "document", "file_id": message.document.file_id, "file_name": message.document.file_name or "doc"})

    await state.update_data(attachments=attachments)
    _, finish_w = skip_words(lang)
    await message.answer(
        f"✅ Файл прикреплён ({len(attachments)} шт.). Отправьте ещё или нажмите «{finish_w}»."
        if lang == RU else
        f"✅ Файл тіркелді ({len(attachments)} дана). Тағы жіберіңіз немесе «{finish_w}» түймесін басыңыз."
    )


async def _finalize_report(message: Message, state: FSMContext, data: dict):
    lang = data.get("language", RU)

    case_id, secret_code = save_report(data)

    # Уведомление администраторов
    admin_ids_to_notify = set(ADMIN_IDS)
    if data.get("urgent") or data.get("category") in ("crisis", "fight", "threat"):
        admin_ids_to_notify.update(URGENT_ADMIN_IDS)

    admin_text = admin_message(data, case_id)
    for admin_id in admin_ids_to_notify:
        try:
            await bot.send_message(admin_id, admin_text)
            # Пересылаем вложения администраторам
            for att in data.get("attachments", []):
                try:
                    if att["type"] == "photo":
                        await bot.send_photo(admin_id, att["file_id"], caption=f"[{case_id}]")
                    elif att["type"] == "video":
                        await bot.send_video(admin_id, att["file_id"], caption=f"[{case_id}]")
                    elif att["type"] == "voice":
                        await bot.send_voice(admin_id, att["file_id"])
                    elif att["type"] == "document":
                        await bot.send_document(admin_id, att["file_id"], caption=f"[{case_id}]")
                except Exception as e:
                    logger.warning("Failed to send attachment to admin: %s", e)
        except Exception as e:
            logger.exception("Failed to notify admin %s: %s", admin_id, e)

    # Сообщение студенту
    confirm = (
        f"✅ <b>Ваше обращение принято!</b>\n\n"
        f"📋 <b>Номер обращения:</b> <code>{case_id}</code>\n"
        f"🔑 <b>Секретный код:</b> <code>{secret_code}</code>\n\n"
        f"⚠️ <b>Сохраните эти данные</b> — они нужны для проверки статуса.\n\n"
        f"Ваше обращение передано уполномоченным сотрудникам школы. "
        f"Мы постараемся разобраться в ситуации."
        if lang == RU else
        f"✅ <b>Өтінішіңіз қабылданды!</b>\n\n"
        f"📋 <b>Өтініш нөмірі:</b> <code>{case_id}</code>\n"
        f"🔑 <b>Құпия код:</b> <code>{secret_code}</code>\n\n"
        f"⚠️ <b>Бұл деректерді сақтаңыз</b> — мәртебені тексеру үшін қажет.\n\n"
        f"Өтінішіңіз мектептің уәкілетті қызметкерлеріне жеткізілді. "
        f"Жағдайды шешуге тырысамыз."
    )
    await message.answer(confirm, reply_markup=ReplyKeyboardRemove())
    await state.clear()


# ─────────────────────────── ADMIN COMMANDS ────────────────────────

@dp.message(Command("admin_cases"))
async def cmd_admin_cases(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    rows = get_recent_cases(10)
    if not rows:
        await message.answer("Дел не найдено.")
        return
    lines = ["<b>Последние 10 дел:</b>\n"]
    for case_id, category, status, urgent, created_at in rows:
        cat_ru = CATEGORIES.get(category, {}).get(RU, category)
        urg = "🚨" if urgent else ""
        st = STATUS_LABELS.get(status, status)
        lines.append(f"{urg}<code>{case_id}</code> | {cat_ru} | {st}\n{created_at[:16]}")
    await message.answer("\n\n".join(lines))


@dp.message(Command("admin_case"))
async def cmd_admin_case(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /admin_case CASE-ID")
        return
    case_id = parts[1].strip().upper()
    row = get_report_by_id(case_id)
    if not row:
        await message.answer(f"❌ Дело {case_id} не найдено.")
        return
    cat_ru = CATEGORIES.get(row["category"], {}).get(RU, row["category"])
    mode_ru = MODES.get(row["report_mode"], {}).get(RU, row["report_mode"])
    st = STATUS_LABELS.get(row["status"], row["status"])
    text = (
        f"📋 <b>Дело: {case_id}</b>\n\n"
        f"<b>Статус:</b> {st}\n"
        f"<b>Тип:</b> {cat_ru}\n"
        f"<b>Формат:</b> {mode_ru}\n"
        f"<b>Срочно:</b> {'🚨 Да' if row['urgent'] else 'Нет'}\n"
        f"<b>Продолжается:</b> {'Да' if row['ongoing'] else 'Нет'}\n\n"
        f"<b>Время:</b> {row['event_time'] or '—'}\n"
        f"<b>Место:</b> {row['location'] or '—'}\n"
        f"<b>Участники:</b> {row['people_involved'] or '—'}\n\n"
        f"<b>Описание:</b>\n{row['description'] or '—'}\n\n"
        f"<b>Имя:</b> {row['reporter_name'] or '—'}\n"
        f"<b>Класс:</b> {row['reporter_class'] or '—'}\n"
        f"<b>Контакт:</b> {row['reporter_contact'] or '—'}\n\n"
        f"<b>Заметка:</b> {row['admin_note'] or '—'}\n"
        f"<b>Создано:</b> {row['created_at']}\n"
        f"<b>Обновлено:</b> {row['updated_at']}\n\n"
        f"<i>Команды: /set_status {case_id} &lt;статус&gt;\n"
        f"/note {case_id} &lt;текст заметки&gt;</i>"
    )
    await message.answer(text)
    # Отправляем вложения
    attachments = get_attachments(case_id)
    if attachments:
        await message.answer(f"📎 Вложений: {len(attachments)}")
        for file_type, file_id, file_name in attachments:
            try:
                if file_type == "photo":
                    await message.answer_photo(file_id, caption=file_name)
                elif file_type == "video":
                    await message.answer_video(file_id, caption=file_name)
                elif file_type == "voice":
                    await message.answer_voice(file_id)
                elif file_type == "document":
                    await message.answer_document(file_id, caption=file_name)
            except Exception as e:
                await message.answer(f"[Не удалось загрузить вложение: {e}]")


@dp.message(Command("set_status"))
async def cmd_set_status(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        valid = " | ".join(VALID_STATUSES)
        await message.answer(f"Использование: /set_status CASE-ID статус\nДоступные статусы: {valid}")
        return
    case_id = parts[1].strip().upper()
    new_status = parts[2].strip().lower()
    if new_status not in VALID_STATUSES:
        await message.answer(f"❌ Недопустимый статус. Доступные: {', '.join(VALID_STATUSES)}")
        return
    row = get_report_by_id(case_id)
    if not row:
        await message.answer(f"❌ Дело {case_id} не найдено.")
        return
    update_status(case_id, new_status, message.from_user.id)
    await message.answer(f"✅ Статус <code>{case_id}</code> → {STATUS_LABELS.get(new_status, new_status)}")


@dp.message(Command("note"))
async def cmd_note(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /note CASE-ID текст заметки")
        return
    case_id = parts[1].strip().upper()
    note_text = parts[2].strip()
    row = get_report_by_id(case_id)
    if not row:
        await message.answer(f"❌ Дело {case_id} не найдено.")
        return
    add_note(case_id, note_text, message.from_user.id)
    await message.answer(f"✅ Заметка к <code>{case_id}</code> сохранена.")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    total, by_cat, by_status, urgent = get_stats()
    lines = [f"📊 <b>Статистика всех обращений</b>\n\nВсего: <b>{total}</b> | Срочных: <b>{urgent}</b>\n"]
    lines.append("<b>По типу:</b>")
    for cat, count in by_cat:
        cat_label = CATEGORIES.get(cat, {}).get(RU, cat)
        lines.append(f"  {cat_label}: {count}")
    lines.append("\n<b>По статусу:</b>")
    for status, count in by_status:
        st_label = STATUS_LABELS.get(status, status)
        lines.append(f"  {st_label}: {count}")
    await message.answer("\n".join(lines))


@dp.message(Command("export_today"))
async def cmd_export_today(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    rows = get_cases_today()
    if not rows:
        await message.answer("Сегодня обращений нет.")
        return
    lines = [f"📅 <b>Обращения за сегодня ({date.today().isoformat()}):</b>\n"]
    for case_id, category, status, urgent, created_at in rows:
        cat_ru = CATEGORIES.get(category, {}).get(RU, category)
        urg = "🚨 " if urgent else ""
        st = STATUS_LABELS.get(status, status)
        lines.append(f"{urg}<code>{case_id}</code>\n{cat_ru} | {st} | {created_at[11:16]}")
    await message.answer("\n\n".join(lines))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🔧 <b>Команды администратора:</b>\n\n"
        "/admin_cases — последние 10 дел\n"
        "/admin_case CASE-ID — полная информация о деле\n"
        "/set_status CASE-ID статус — изменить статус\n"
        "/note CASE-ID текст — добавить заметку\n"
        "/stats — общая статистика\n"
        "/export_today — дела за сегодня\n\n"
        "<b>Доступные статусы:</b>\n"
        + "\n".join(f"  <code>{s}</code> — {STATUS_LABELS[s]}" for s in VALID_STATUSES)
    )


# ─────────────────────────── MAIN ──────────────────────────────────

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Add it to .env")
        return
    init_db()
    logger.info("Bot starting. Admin IDs: %s", ADMIN_IDS)
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
