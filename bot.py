import os
import csv
import asyncio
from datetime import datetime
from pathlib import Path
import time as _time

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

TASKS_STARTED = False
COMMANDS_SYNCED = False

# ===== Load env only when .env exists =====
if os.path.exists(".env"):
    load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_ENV = os.getenv("GUILD_ID")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN from environment variables")
if not GUILD_ID_ENV:
    raise RuntimeError("Missing GUILD_ID from environment variables")

GUILD_ID = int(GUILD_ID_ENV)

# ===== Roles to notify =====
ROLES_TO_NOTIFY = {"leader", "people"}
# ROLES_TO_NOTIFY = {"test"}

# ===== CSV paths =====
BASE_DIR           = Path(__file__).parent
COACHES_CSV_PATH   = BASE_DIR / "coaches.csv"
BOOKINGS_CSV_PATH  = BASE_DIR / "bookings.csv"

COACH_FIELDS   = ["timestamp", "user_id", "name", "time", "topic", "status"]
# booking status: BOOKED | CANCELLED_BY_COACH | CANCELLED_BY_COACHEE
BOOKING_FIELDS = ["id", "timestamp", "coach_id", "coach_name",
                  "coachee_id", "coachee_name", "time", "topic", "status"]

# =================================================
# Utility
# =================================================

def norm(s: str) -> str:
    return "".join(s.split()).lower() if s else ""

def is_sunday() -> bool:
    return datetime.now().weekday() == 6

CLOSED_MSG = (
    "⏰ ซินหมิงเปิดให้ใช้งานเฉพาะ **วันอาทิตย์** เท่านั้นนะครับ 💙\n"
    "รอเจอกันวันอาทิตย์หน้านะครับ 🙏"
)

def is_available(s: str | None) -> bool:
    if not s:
        return True
    return s.strip().upper() == "AVAILABLE"

def ensure_csv_exists(path: Path, fields: list[str]):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=fields).writeheader()

def safe_write_csv(path: Path, fieldnames: list[str], rows: list[dict],
                   retries: int = 5, delay: float = 0.4):
    last_err = None
    for _ in range(retries):
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
            return
        except PermissionError as e:
            last_err = e
            _time.sleep(delay)
    raise last_err

def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def load_coaches() -> list[dict]:
    ensure_csv_exists(COACHES_CSV_PATH, COACH_FIELDS)
    return load_csv(COACHES_CSV_PATH)

def save_coaches(rows: list[dict]):
    ensure_csv_exists(COACHES_CSV_PATH, COACH_FIELDS)
    normalized = [{
        "timestamp": r.get("timestamp", ""),
        "user_id":   r.get("user_id", ""),
        "name":      r.get("name", ""),
        "time":      r.get("time", ""),
        "topic":     r.get("topic", ""),
        "status":    (r.get("status") or "AVAILABLE").upper(),
    } for r in rows]
    safe_write_csv(COACHES_CSV_PATH, COACH_FIELDS, normalized)

def load_bookings() -> list[dict]:
    ensure_csv_exists(BOOKINGS_CSV_PATH, BOOKING_FIELDS)
    return load_csv(BOOKINGS_CSV_PATH)

def save_bookings(rows: list[dict]):
    ensure_csv_exists(BOOKINGS_CSV_PATH, BOOKING_FIELDS)
    safe_write_csv(BOOKINGS_CSV_PATH, BOOKING_FIELDS, rows)

def next_booking_id(rows: list[dict]) -> int:
    if not rows:
        return 1
    ids = [int(r["id"]) for r in rows if r.get("id", "").isdigit()]
    return max(ids) + 1 if ids else 1

# =================================================
# DM Helpers
# =================================================

async def dm_user(uid: str, text: str):
    if not uid or not str(uid).isdigit():
        return
    try:
        user = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
        if user:
            await (await user.create_dm()).send(text)
    except Exception:
        pass

async def dm_roles(message: str, file_path: str | None = None,
                   exclude_user_id: str | None = None):
    for guild in bot.guilds:
        if guild.id != GUILD_ID:
            continue
        for member in guild.members:
            if member.bot:
                continue
            if exclude_user_id and str(member.id) == str(exclude_user_id):
                continue
            if not any(r.name.lower() in ROLES_TO_NOTIFY for r in member.roles):
                continue
            try:
                dm = await member.create_dm()
                if file_path:
                    await dm.send(message, file=discord.File(file_path))
                else:
                    await dm.send(message)
            except Exception:
                continue

# =================================================
# Message builder helpers
# =================================================

SEP = "─" * 36

def wrap(inner: str) -> str:
    return f"\n{SEP}\n{inner}\n{SEP}\n"

def build_list_coaches_msg(coaches: list[dict], bookings: list[dict]) -> str:
    """
    สร้าง layout รายชื่อ coach + coachee ที่จองแต่ละคน

    👤 friend  |  พฤ 19:30-21:30  |  BM
       └─ 1. Yinglak  (ID #3)
       └─ 2. TomTom   (ID #5)

    👤 Yinglak  |  จันทร์ 19:30  |  6เสาหลักสุขภาพ
       └─ ยังไม่มีคนจอง
    """
    available = [c for c in coaches if is_available(c.get("status"))]
    if not available:
        return wrap("📭  ตอนนี้ยังไม่มี Coach ที่ว่างครับ")

    lines = [f"📋  **Coach ที่ว่าง** ({len(available)} คน)\n"]
    for c in available:
        c_uid   = c.get("user_id", "")
        c_name  = c.get("name", "")
        c_time  = c.get("time", "")
        c_topic = c.get("topic", "")
        mention = f"<@{c_uid}>" if c_uid.isdigit() else c_uid

        lines.append(f"👤 **{c_name}** ({mention})")
        lines.append(f"   🕐 {c_time}  |  📌 {c_topic}")

        # หา coachee ที่ยัง BOOKED อยู่กับ coach คนนี้ + เวลาตรงกัน
        booked = [
            bk for bk in bookings
            if bk.get("coach_id") == c_uid
            and bk.get("status") == "BOOKED"
            and norm(bk.get("time", "")) == norm(c_time)
        ]
        if booked:
            for i, bk in enumerate(booked, 1):
                ce_name = bk.get("coachee_name", "")
                ce_uid  = bk.get("coachee_id", "")
                ce_mention = f"<@{ce_uid}>" if ce_uid.isdigit() else ce_uid
                bk_id = bk.get("id", "?")
                lines.append(f"   └─ {i}. {ce_name} ({ce_mention})  •  ID {bk_id}")
        else:
            lines.append("   └─ ยังไม่มีคนจอง")

        lines.append("")

    inner = "\n".join(lines).rstrip()
    return wrap(inner)

def build_booking_notify_coach(coachee_name: str, coachee_mention: str,
                                booked_time: str, topic: str,
                                booking_id: int, all_coachees: list[str]) -> str:
    coachee_list = "\n".join(f"{i}. {n}" for i, n in enumerate(all_coachees, 1))
    inner = (
        f"🥳  มีคนจองคิวใหม่!\n\n"
        f"👤  Coachee  : {coachee_name} ({coachee_mention})\n"
        f"🕐  เวลา    : {booked_time}\n"
        f"📌  หัวข้อ  : {topic}\n"
        f"🔖  Booking ID : {booking_id}\n\n"
        f"📋  Coachee ทั้งหมดของคุณตอนนี้\n{coachee_list}"
    )
    return wrap(inner)

def build_booking_notify_coachee(coach_name: str, coach_mention: str,
                                  booked_time: str, topic: str,
                                  booking_id: int) -> str:
    inner = (
        f"✅  จองคิวสำเร็จแล้ว!\n\n"
        f"👤  Coach   : {coach_name} ({coach_mention})\n"
        f"🕐  เวลา   : {booked_time}\n"
        f"📌  หัวข้อ : {topic}\n"
        f"🔖  Booking ID : {booking_id}\n\n"
        f"หากต้องการยกเลิก ใช้ `/cancel` แล้วใส่ Booking ID ได้เลยครับ"
    )
    return wrap(inner)

def build_cancel_msg_other(cancelled_by: str, booking_id: int,
                            other_name: str, other_mention: str,
                            booked_time: str, topic: str) -> str:
    inner = (
        f"❌  {cancelled_by} ยกเลิก Booking {booking_id}\n\n"
        f"👤  {cancelled_by}  : {other_name} ({other_mention})\n"
        f"🕐  เวลา   : {booked_time}\n"
        f"📌  หัวข้อ : {topic}"
    )
    return wrap(inner)

def build_cancel_msg_self(booking_id: int, other_role: str,
                           other_name: str, other_mention: str,
                           booked_time: str, topic: str) -> str:
    inner = (
        f"✅  ยกเลิก Booking {booking_id} เรียบร้อยแล้ว\n\n"
        f"👤  {other_role}  : {other_name} ({other_mention})\n"
        f"🕐  เวลา   : {booked_time}\n"
        f"📌  หัวข้อ : {topic}"
    )
    return wrap(inner)

# =================================================
# Bot Setup
# =================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send("心明 พร้อมช่วยแล้วครับ!")

# =================================================
# /register_coach
# =================================================

@bot.tree.command(name="register_coach", description="ลงเป็น Coach (ผู้แนะนำ)")
@app_commands.describe(
    name="ชื่อ Coach เช่น coach-front",
    available_time="วัน-เวลา เช่น อาทิตย์ 19.00-21.00",
    topics="หัวข้อที่สอนได้ เช่น BM, Why I Join",
)
async def register_coach(interaction: discord.Interaction,
                          name: str, available_time: str, topics: str):
    uid = str(interaction.user.id)
    await interaction.response.defer(ephemeral=True)

    if not is_sunday():
        await interaction.followup.send(CLOSED_MSG, ephemeral=True)
        return

    coaches = load_coaches()
    for c in coaches:
        if c["user_id"] == uid and norm(c["time"]) == norm(available_time):
            await interaction.followup.send("⚠️ คุณลงเวลานี้ไว้แล้วครับ", ephemeral=True)
            return

    coaches.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user_id":   uid,
        "name":      name,
        "time":      available_time,
        "topic":     topics,
        "status":    "AVAILABLE",
    })
    try:
        save_coaches(coaches)
    except PermissionError:
        await interaction.followup.send(
            "❌ บันทึกไฟล์ไม่สำเร็จ เพราะ `coaches.csv` ถูกเปิดค้างใน Excel\n"
            "✅ กรุณาปิด Excel แล้วลองใหม่ครับ", ephemeral=True)
        return

    mention = f"<@{uid}>"
    inner = (
        f"✅  ลงทะเบียน Coach สำเร็จ!\n\n"
        f"👤  ชื่อ   : {name} ({mention})\n"
        f"🕐  เวลา  : {available_time}\n"
        f"📌  หัวข้อ : {topics}"
    )
    await interaction.followup.send(wrap(inner), ephemeral=False)
    await dm_roles(
        message=wrap(
            f"🆕  มี Coach ลงทะเบียนเพิ่ม!\n\n"
            f"👤  {name} ({mention})\n"
            f"🕐  {available_time}\n"
            f"📌  {topics}\n\n"
            f"ใช้ /book_coach เพื่อจองได้เลย 💙"
        ),
        exclude_user_id=uid,
    )

# =================================================
# /list_coaches
# =================================================

@bot.tree.command(name="list_coaches", description="ดูรายชื่อ Coach ที่ว่าง + คนที่จองแต่ละคน")
async def list_coaches(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not is_sunday():
        await interaction.followup.send(CLOSED_MSG, ephemeral=True)
        return

    coaches  = load_coaches()
    bookings = load_bookings()
    msg = build_list_coaches_msg(coaches, bookings)

    await interaction.followup.send(msg, ephemeral=False)

# =================================================
# /book_coach
# =================================================

@bot.tree.command(name="book_coach", description="จองคิว Coach")
@app_commands.describe(
    coach_name="ชื่อ Coach เช่น coach-front",
    booked_time="เวลาที่นัดจริง",
    topic="หัวข้อ",
)
async def book_coach(interaction: discord.Interaction,
                      coach_name: str, booked_time: str, topic: str):
    coachee    = interaction.user
    coachee_id = str(coachee.id)
    await interaction.response.defer(ephemeral=True)

    if not is_sunday():
        await interaction.followup.send(CLOSED_MSG, ephemeral=True)
        return

    coaches = load_coaches()
    matches = [c for c in coaches
               if norm(c.get("name", "")) == norm(coach_name) and is_available(c.get("status"))]

    if not matches:
        await interaction.followup.send(
            "❌ ไม่พบ Coach ชื่อนี้ที่ว่างครับ ลองดูชื่อใน `/list_coaches` อีกครั้งนะครับ",
            ephemeral=True)
        return

    coach    = matches[0]
    coach_id = coach["user_id"]

    bookings = load_bookings()

    # กัน coachee คนเดิมจอง coach คนเดิม + เวลาเดิมซ้ำ
    for bk in bookings:
        if (bk.get("coach_id") == coach_id
                and bk.get("coachee_id") == coachee_id
                and norm(bk.get("time", "")) == norm(booked_time)
                and bk.get("status") == "BOOKED"):
            await interaction.followup.send(
                "⚠️ คุณมีคิวกับ Coach คนนี้ เวลานี้อยู่แล้วครับ", ephemeral=True)
            return

    booking_id = next_booking_id(bookings)
    bookings.append({
        "id":           str(booking_id),
        "timestamp":    datetime.now().isoformat(timespec="seconds"),
        "coach_id":     coach_id,
        "coach_name":   coach.get("name", ""),
        "coachee_id":   coachee_id,
        "coachee_name": coachee.display_name,
        "time":         booked_time,
        "topic":        topic,
        "status":       "BOOKED",
    })
    try:
        save_bookings(bookings)
    except PermissionError:
        await interaction.followup.send(
            "❌ บันทึก `bookings.csv` ไม่สำเร็จ เพราะถูกเปิดค้างใน Excel\n"
            "✅ กรุณาปิด Excel แล้วลองใหม่ครับ", ephemeral=True)
        return

    coachee_mention = f"<@{coachee_id}>"
    coach_mention   = f"<@{coach_id}>"

    # รวม list coachee ทั้งหมดที่จอง coach คนนี้ ในเวลา slot เดียวกัน (รวมคิวใหม่)
    all_coachees = [
        f"{bk.get('coachee_name', '')} (<@{bk.get('coachee_id', '')}>)  •  ID {bk.get('id', '?')}"
        for bk in bookings
        if bk.get("coach_id") == coach_id
        and norm(bk.get("time", "")) == norm(booked_time)
        and bk.get("status") == "BOOKED"
    ]

    # แจ้ง coach (อีกฝ่าย) ผ่าน DM
    await dm_user(coach_id, build_booking_notify_coach(
        coachee.display_name, coachee_mention,
        booked_time, topic, booking_id, all_coachees))

    # แจ้ง coachee (ตัวเอง) ผ่าน followup
    await interaction.followup.send(
        build_booking_notify_coachee(
            coach.get("name", ""), coach_mention,
            booked_time, topic, booking_id),
        ephemeral=False)

# =================================================
# /cancel  — ใช้ได้ทั้ง coach และ coachee
# =================================================

@bot.tree.command(name="cancel", description="ยกเลิกคิว (ใช้ได้ทั้ง Coach และ Coachee)")
@app_commands.describe(booking_id="หมายเลข Booking ID ที่ต้องการยกเลิก")
async def cancel(interaction: discord.Interaction, booking_id: int):
    user    = interaction.user
    user_id = str(user.id)
    await interaction.response.defer(ephemeral=True)

    if not is_sunday():
        await interaction.followup.send(CLOSED_MSG, ephemeral=True)
        return

    bookings = load_bookings()
    target   = next((bk for bk in bookings if bk.get("id") == str(booking_id)), None)

    if not target:
        await interaction.followup.send("❌ ไม่พบ Booking ID นี้ครับ", ephemeral=True)
        return
    if target.get("status") != "BOOKED":
        await interaction.followup.send("ℹ️ คิวนี้ถูกยกเลิกไปแล้วครับ", ephemeral=True)
        return

    is_coach   = target.get("coach_id")   == user_id
    is_coachee = target.get("coachee_id") == user_id

    if not is_coach and not is_coachee:
        await interaction.followup.send(
            "❌ คุณไม่ใช่ Coach หรือ Coachee ของคิวนี้ครับ", ephemeral=True)
        return

    # อัปเดต status
    target["status"] = "CANCELLED_BY_COACH" if is_coach else "CANCELLED_BY_COACHEE"
    try:
        save_bookings(bookings)
    except PermissionError:
        await interaction.followup.send(
            "❌ เขียน `bookings.csv` ไม่ได้ เพราะถูกเปิดค้างใน Excel\n"
            "✅ ปิด Excel แล้วลองใหม่ครับ", ephemeral=True)
        return

    coach_id    = target.get("coach_id", "")
    coachee_id  = target.get("coachee_id", "")
    coach_name   = target.get("coach_name", "")
    coachee_name = target.get("coachee_name", "")
    coach_mention   = f"<@{coach_id}>"
    coachee_mention = f"<@{coachee_id}>"
    btime  = target.get("time", "")
    btopic = target.get("topic", "")

    if is_coach:
        # coach ยกเลิก → แจ้ง coachee ผ่าน DM, แจ้งตัวเองผ่าน followup
        await dm_user(coachee_id, build_cancel_msg_other(
            "Coach", booking_id, coach_name, coach_mention, btime, btopic))
        await interaction.followup.send(
            build_cancel_msg_self(
                booking_id, "Coachee", coachee_name, coachee_mention, btime, btopic),
            ephemeral=False)
    else:
        # coachee ยกเลิก → แจ้ง coach ผ่าน DM, แจ้งตัวเองผ่าน followup
        await dm_user(coach_id, build_cancel_msg_other(
            "Coachee", booking_id, coachee_name, coachee_mention, btime, btopic))
        await interaction.followup.send(
            build_cancel_msg_self(
                booking_id, "Coach", coach_name, coach_mention, btime, btopic),
            ephemeral=False)

# =================================================
# Background Tasks
# =================================================

async def weekly_announcement_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 11 and now.minute == 0:
            msg = wrap(
                "🌤  **สวัสดีเช้าวันอาทิตย์นะครับ!**\n\n"
                "• ลงเป็น Coach    →  `/register_coach`\n"
                "• ดูรายชื่อ Coach  →  `/list_coaches`\n"
                "• จองคิวซ้อม      →  `/book_coach`\n"
                "• ยกเลิกคิว       →  `/cancel`\n\n"
                "ขอให้เริ่มสัปดาห์ใหม่อย่างมีพลังนะครับ 💙\n"
                "— ซินหมิง 🧘"
            )
            await dm_roles(msg, "hello.gif")
            await asyncio.sleep(60)
        await asyncio.sleep(30)

async def daily_available_coaches_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 16 and now.minute == 0:
            coaches  = load_coaches()
            bookings = load_bookings()
            msg = build_list_coaches_msg(coaches, bookings)
            msg = msg.replace("📋  **Coach ที่ว่าง**",
                              "⏰  **อัปเดต 16:00 — Coach ที่ยังว่าง**", 1)
            footer = wrap("จองได้ถึง 22:00 น. นะคร้าบบ 💙")
            await dm_roles(msg + footer)
            await asyncio.sleep(60)
        await asyncio.sleep(30)

async def nightly_close_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 22 and now.minute == 0:
            await dm_roles(
                wrap("🌙  **ซินหมิงขอตัวไปพักแล้วนะครับ**\nวันนี้ปิดรับการจองแล้วน้า 💙😴"),
                "bye.gif")
            await asyncio.sleep(60)
        await asyncio.sleep(30)

# =================================================
# on_ready
# =================================================

@bot.event
async def on_ready():
    global TASKS_STARTED, COMMANDS_SYNCED
    print(f"Logged in as {bot.user}")
    ensure_csv_exists(COACHES_CSV_PATH, COACH_FIELDS)
    ensure_csv_exists(BOOKINGS_CSV_PATH, BOOKING_FIELDS)
    if not COMMANDS_SYNCED:
        COMMANDS_SYNCED = True
        synced = await bot.tree.sync()
        print("Synced global commands:", [c.name for c in synced])
    if not TASKS_STARTED:
        TASKS_STARTED = True
        bot.loop.create_task(weekly_announcement_dm())
        bot.loop.create_task(daily_available_coaches_dm())
        bot.loop.create_task(nightly_close_dm())

# =================================================
# Run
# =================================================

if __name__ == "__main__":
    print("Starting Xin Ming bot…")
    bot.run(TOKEN)