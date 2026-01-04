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
GUILD_OBJ = discord.Object(id=GUILD_ID)

# ===== Roles to notify =====
ROLES_TO_NOTIFY = {"leader", "people"}

# ===== CSV paths =====
BASE_DIR = Path(__file__).parent
BUDDIES_CSV_PATH = BASE_DIR / "buddies.csv"
BOOKINGS_CSV_PATH = BASE_DIR / "bookings.csv"

BUDDY_FIELDS = ["timestamp", "user_id", "name", "time", "topic", "status"]
BOOKING_FIELDS = [
    "id", "timestamp", "buddy_id", "buddy_name", "budder_id", "budder_name",
    "time", "topic", "status", "slot_time",
]

# =================================================
# Utility
# =================================================

def norm(s: str) -> str:
    # ไม่สนใจเว้นวรรค และไม่สนใจตัวพิมพ์ใหญ่-เล็ก
    return "".join(s.split()).lower() if s else ""

def is_available_status(s: str | None):
    if not s:
        return True
    return s.strip().upper() == "AVAILABLE"

def ensure_csv_exists(path: Path, fields: list[str]):
    """สร้างไฟล์ CSV + header เฉพาะตอนยังไม่มีไฟล์"""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

def safe_write_csv(path: Path, fieldnames: list[str], rows: list[dict], retries: int = 5, delay: float = 0.4):
    """
    เขียนไฟล์ CSV แบบทนต่อกรณีไฟล์ถูก Excel lock
    ถ้า PermissionError จะ retry หลายครั้ง
    """
    last_err = None
    for _ in range(retries):
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)
            return
        except PermissionError as e:
            last_err = e
            _time.sleep(delay)
    raise last_err

def load_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def load_buddies():
    ensure_csv_exists(BUDDIES_CSV_PATH, BUDDY_FIELDS)
    return load_csv(BUDDIES_CSV_PATH)

def save_buddies(rows):
    ensure_csv_exists(BUDDIES_CSV_PATH, BUDDY_FIELDS)
    normalized = []
    for r in rows:
        normalized.append({
            "timestamp": r.get("timestamp", ""),
            "user_id": r.get("user_id", ""),
            "name": r.get("name", ""),
            "time": r.get("time", ""),
            "topic": r.get("topic", ""),
            "status": (r.get("status") or "AVAILABLE"),
        })
    safe_write_csv(BUDDIES_CSV_PATH, BUDDY_FIELDS, normalized)

def load_bookings():
    ensure_csv_exists(BOOKINGS_CSV_PATH, BOOKING_FIELDS)
    return load_csv(BOOKINGS_CSV_PATH)

def save_bookings(rows):
    ensure_csv_exists(BOOKINGS_CSV_PATH, BOOKING_FIELDS)
    safe_write_csv(BOOKINGS_CSV_PATH, BOOKING_FIELDS, rows)

def next_booking_id(rows):
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
    uid_int = int(uid)

    user = bot.get_user(uid_int) or await bot.fetch_user(uid_int)
    if not user:
        return

    try:
        dm = await user.create_dm()
        await dm.send(text)
    except:
        pass

async def dm_roles(
    message: str,
    file_path: str | None = None,
    exclude_user_id: str | None = None,
):
    """ส่ง DM ให้ทุกคนที่มี role ใน ROLES_TO_NOTIFY (ยกเว้น exclude_user_id ถ้ามี)"""
    for guild in bot.guilds:
        if guild.id != GUILD_ID:
            continue

        for member in guild.members:
            if member.bot:
                continue

            if exclude_user_id and str(member.id) == str(exclude_user_id):
                continue

            has_role = any(r.name.lower() in ROLES_TO_NOTIFY for r in member.roles)
            if not has_role:
                continue

            try:
                dm = await member.create_dm()
                if file_path:
                    file = discord.File(file_path)
                    await dm.send(message, file=file)
                else:
                    await dm.send(message)
            except:
                continue

# =================================================
# Slot helpers
# =================================================

def update_buddy_status(uid: str, slot: str, new_status: str):
    buddies = load_buddies()
    changed = False
    for r in buddies:
        if r["user_id"] == uid and norm(r["time"]) == norm(slot):
            r["status"] = new_status
            changed = True
    if changed:
        save_buddies(buddies)

def remove_buddy_slot(uid: str, slot: str):
    buddies = load_buddies()
    new_rows = [
        r for r in buddies
        if not (r["user_id"] == uid and norm(r["time"]) == norm(slot))
    ]
    if len(new_rows) != len(buddies):
        save_buddies(new_rows)

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
# /register_buddy
# =================================================

@bot.tree.command(
    name="register_buddy",
    description="ลงทะเบียนเวลาว่างเพื่อเป็น Buddy",
    guild=GUILD_OBJ,
)
@app_commands.describe(
    name="ชื่อ Buddy เช่น buddy-front",
    available_time="วัน-เวลา เช่น อาทิตย์ 19.00-21.00",
    topics="หัวข้อที่สอนได้ เช่น BM, Why I Join",
)
async def register_buddy(
    interaction: discord.Interaction,
    name: str,
    available_time: str,
    topics: str,
):
    u = interaction.user
    uid = str(u.id)

    await interaction.response.defer(ephemeral=True)

    buddies = load_buddies()

    # กันซ้ำ: คนเดิมลงเวลาเดิมซ้ำ
    for b in buddies:
        if b["user_id"] == uid and norm(b["time"]) == norm(available_time):
            await interaction.followup.send(
                "⚠️ คุณลงเวลานี้ไว้แล้วครับ",
                ephemeral=True,
            )
            return

    timestamp = datetime.now().isoformat(timespec="seconds")
    buddies.append({
        "timestamp": timestamp,
        "user_id": uid,
        "name": name,
        "time": available_time,
        "topic": topics,
        "status": "AVAILABLE",
    })

    try:
        save_buddies(buddies)
    except PermissionError:
        await interaction.followup.send(
            "❌ บันทึกไฟล์ไม่สำเร็จ เพราะไฟล์ `buddies.csv` น่าจะถูกเปิดค้างใน Excel อยู่\n"
            "✅ กรุณาปิด Excel แล้วลอง `/register_buddy` ใหม่ครับ",
            ephemeral=True,
        )
        return

    user_mention = f"<@{uid}>"

    await dm_user(
        uid,
        "\n--------------------------------------------\n📩 📩 📩 📩 📩\n"
        f"✅ ลงทะเบียน Buddy สำเร็จ!\n"
        f"Buddy: {name} ({user_mention})\n"
        f"เวลา: {available_time}\n"
        f"หัวข้อ: {topics}\n"
        "\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
    )

    await dm_roles(
        message=(
            "\n--------------------------------------------\n📩 📩 📩 📩 📩\n🆕 มี Buddy ลงทะเบียนเพิ่ม!\n"
            f"• {name} ({user_mention})\n"
            f"• เวลา: {available_time}\n"
            f"• หัวข้อ: {topics}\n\n"
            "ใช้ /book_buddy เพื่อจองได้เลย 💙\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
        ),
        exclude_user_id=uid,
    )

    await interaction.followup.send(
        "ลงทะเบียนสำเร็จแล้วครับ! ซินหมิงส่งรายละเอียดไปที่ DM ให้แล้ว 📨",
        ephemeral=True,
    )

# =================================================
# /list_buddies
# =================================================

@bot.tree.command(
    name="list_buddies",
    description="ดูรายชื่อ Buddy ที่ว่าง",
    guild=GUILD_OBJ,
)
async def list_buddies(interaction: discord.Interaction):
    u = interaction.user
    uid = str(u.id)

    await interaction.response.defer(ephemeral=True)

    buddies = load_buddies()
    available = [b for b in buddies if is_available_status(b.get("status"))]

    if not available:
        await dm_user(uid, "\n--------------------------------------------\n📩 📩 📩 📩 📩\nตอนนี้ยังไม่มี Buddy ที่ว่างครับ\n📩 📩 📩 📩 📩\n--------------------------------------------\n")
        await interaction.followup.send(
            "ตอนนี้ยังไม่มี Buddy ที่ว่างครับ",
            ephemeral=True,
        )
        return

    msg = "\n--------------------------------------------\n📩 📩 📩 📩 📩\n📘 **Buddy ที่ยังว่าง**\n\n"
    for b in available:
        buddy_mention = f"<@{b['user_id']}>" if str(b.get("user_id","")).isdigit() else b.get("user_id","")
        msg += (
            f"• **{b.get('name','')}** ({buddy_mention}) "
            f"เวลา: `{b.get('time','')}` | หัวข้อ: `{b.get('topic','')}`\n"
        )
    msg += "📩 📩 📩 📩 📩\n--------------------------------------------\n"

    await dm_user(uid, msg)
    await interaction.followup.send(
        "ส่งรายการไปที่ DM แล้วครับ",
        ephemeral=True,
    )

# =================================================
# /book_buddy
# =================================================

@bot.tree.command(
    name="book_buddy",
    description="จองคิว Buddy",
    guild=GUILD_OBJ,
)
@app_commands.describe(
    buddy_name="ชื่อ Buddy เช่น buddy-front",
    booked_time="เวลาที่ต้องการนัดจริง",
    topic="หัวข้อ",
)
async def book_buddy(
    interaction: discord.Interaction,
    buddy_name: str,
    booked_time: str,
    topic: str,
):
    budder = interaction.user
    budder_id = str(budder.id)
    budder_mention = f"<@{budder_id}>"

    await interaction.response.defer(ephemeral=True)

    buddies = load_buddies()
    matches = [
        b for b in buddies
        if norm(b.get("name","")) == norm(buddy_name) and is_available_status(b.get("status"))
    ]

    if not matches:
        await interaction.followup.send(
            "ไม่พบ Buddy ชื่อนี้ที่ยังว่างครับ ลองตรวจสอบชื่อใน /list_buddies อีกครั้งนะครับ",
            ephemeral=True,
        )
        return

    buddy = matches[0]
    buddy_id = buddy["user_id"]
    buddy_mention = f"<@{buddy_id}>"

    bookings = load_bookings()
    for bk in bookings:
        if (
            bk.get("buddy_id") == buddy_id
            and norm(bk.get("time","")) == norm(booked_time)
            and bk.get("status") in ("PENDING", "CONFIRMED")
        ):
            await interaction.followup.send(
                "Buddy มีคิวเวลาเดียวกันอยู่แล้วครับ",
                ephemeral=True,
            )
            return

    booking_id = next_booking_id(bookings)

    bookings.append({
        "id": str(booking_id),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "buddy_id": buddy_id,
        "buddy_name": buddy.get("name",""),
        "budder_id": budder_id,
        "budder_name": budder.display_name,
        "time": booked_time,
        "topic": topic,
        "status": "PENDING",
        "slot_time": buddy.get("time",""),
    })

    try:
        save_bookings(bookings)
    except PermissionError:
        await interaction.followup.send(
            "❌ บันทึกไฟล์ `bookings.csv` ไม่สำเร็จ เพราะน่าจะถูกเปิดค้างใน Excel อยู่\n"
            "✅ กรุณาปิด Excel แล้วลองใหม่ครับ",
            ephemeral=True,
        )
        return

    update_buddy_status(buddy_id, buddy.get("time",""), "PENDING")

    await dm_user(
        buddy_id,
        "\n--------------------------------------------\n📩 📩 📩 📩 📩\n"
        "🥳 มีคำขอจองคิวใหม่!\n"
        f"จาก: {budder.display_name} ({budder_mention})\n"
        f"เวลา (นัดจริง): {booked_time}\n"
        f"หัวข้อ: {topic}\n"
        f"Booking ID: {booking_id}\n\n"
        "หากต้องการยืนยันคิวนี้ ใช้คำสั่ง: `/confirm_booking`\n"
        "\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
    )

    await dm_user(
        budder_id,
        "\n--------------------------------------------\n📩 📩 📩 📩 📩\n"
        "✅ ซินหมิงบันทึกคำขอจองคิวของคุณเรียบร้อยแล้ว!\n\n"
        f"Buddy: {buddy.get('name','')} ({buddy_mention})\n"
        f"เวลา (นัดจริง): {booked_time}\n"
        f"หัวข้อ: {topic}\n"
        f"Booking ID: {booking_id}\n"
        "สถานะตอนนี้: PENDING (รอ Buddy ยืนยัน)\n"
        "\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
    )

    await interaction.followup.send(
        "จองคิวสำเร็จแล้วครับ! ซินหมิงส่งรายละเอียดไปที่ DM ให้แล้ว 📨",
        ephemeral=True,
    )

# =================================================
# /confirm_booking
# =================================================

@bot.tree.command(
    name="confirm_booking",
    description="Buddy ยืนยันคิว",
    guild=GUILD_OBJ,
)
@app_commands.describe(booking_id="หมายเลข booking")
async def confirm_booking(interaction: discord.Interaction, booking_id: int):
    buddy = interaction.user
    buddy_id = str(buddy.id)
    buddy_mention = f"<@{buddy_id}>"

    await interaction.response.defer(ephemeral=True)

    bookings = load_bookings()
    target = next((bk for bk in bookings if bk.get("id") == str(booking_id)), None)

    if not target:
        await interaction.followup.send("ไม่พบ booking id นี้ครับ", ephemeral=True)
        return

    if target.get("buddy_id") != buddy_id:
        await interaction.followup.send("คุณไม่ใช่ Buddy ของคิวนี้ครับ", ephemeral=True)
        return

    if target.get("status") == "CONFIRMED":
        await interaction.followup.send("คิวนี้ถูกยืนยันไปก่อนแล้วครับ", ephemeral=True)
        return

    target["status"] = "CONFIRMED"
    try:
        save_bookings(bookings)
    except PermissionError:
        await interaction.followup.send(
            "❌ เขียน `bookings.csv` ไม่ได้ เพราะถูกเปิดค้างใน Excel\n"
            "✅ ปิด Excel แล้วลองใหม่ครับ",
            ephemeral=True,
        )
        return

    update_buddy_status(buddy_id, target.get("slot_time",""), "CONFIRMED")

    budder_id = target.get("budder_id","")
    budder_name = target.get("budder_name","")
    budder_mention = f"<@{budder_id}>"

    await dm_user(
        budder_id,
        "\n--------------------------------------------\n📩 📩 📩 📩 📩\n"
        "✅ คิว Buddy ของคุณได้รับการยืนยันแล้ว!\n\n"
        f"Buddy: {target.get('buddy_name','')} ({buddy_mention})\n"
        f"Budder: {budder_name} ({budder_mention})\n"
        f"เวลา: {target.get('time','')}\n"
        f"หัวข้อ: {target.get('topic','')}\n"
        "\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
    )

    await dm_user(
        buddy_id,
        "\n--------------------------------------------\n📩 📩 📩 📩 📩\n"
        f"คุณได้ยืนยัน booking {booking_id} เรียบร้อยแล้วครับ\n"
        f"Budder: {budder_name} ({budder_mention})\n"
        f"เวลา: {target.get('time','')}\n"
        f"หัวข้อ: {target.get('topic','')}\n"
        "\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
    )

    await interaction.followup.send("ยืนยันคิวสำเร็จแล้วครับ!", ephemeral=True)

# =================================================
# Background Tasks (เหมือนเดิม)
# =================================================

async def weekly_announcement_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 11 and now.minute == 0:
            msg = (
                "🌤 **สวัสดีเช้าวันอาทิตย์นะครับ!**\n\n"
                "• ลงเป็น Buddy → ใช้คำสั่ง: `/register_buddy`\n"
                "• จองคิวซ้อม → ใช้คำสั่ง: `/book_buddy`\n\n"
                "ขอให้เริ่มสัปดาห์ใหม่อย่างมีพลังนะครับ 💙\n"
                "— ซินหมิง 🧘‍♂️"
            )
            await dm_roles(msg, "hello.gif")
            await asyncio.sleep(60)
        await asyncio.sleep(30)

async def daily_available_buddies_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 16 and now.minute == 0:
            buddies = load_buddies()
            available = [b for b in buddies if is_available_status(b.get("status"))]
            if available:
                msg = "\n--------------------------------------------\n📩 📩 📩 📩 📩\n⏰ **อัปเดต 16:00**\nBuddy ที่ยังว่าง:\n"
                for b in available:
                    buddy_mention = f"<@{b['user_id']}>" if str(b.get("user_id","")).isdigit() else b.get("user_id","")
                    msg += f"• {b.get('name','')} ({buddy_mention}) | {b.get('time','')} | {b.get('topic','')}\n"
                msg += "\n ทุกคนยังสามารถจองกันได้ถึงเวลา 18:00 น. นะคร้าบบ\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
            else:
                msg = "\n--------------------------------------------\n📩 📩 📩 📩 📩\n⏰ 16:00 — เวลานี้ไม่มี Buddy ที่ว่างแล้วนะครับ 💙 \nสามารถลงทะเบียน Buddy ใหม่ และทำการจองคิว ได้จนถึงเวลา 18:00 น. นะคร้าบบ\n📩 📩 📩 📩 📩\n--------------------------------------------\n"
            await dm_roles(msg)
            await asyncio.sleep(60)
        await asyncio.sleep(30)

async def nightly_close_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 18 and now.minute == 0:
            msg = "🌙 **ซินหมิงขอตัวไปพักแล้วนะครับ**\nวันนี้ปิดรับการจองแล้วน้า 💙😴"
            await dm_roles(msg, "bye.gif")
            await asyncio.sleep(60)
        await asyncio.sleep(30)

# =================================================
# on_ready
# =================================================

@bot.event
async def on_ready():
    global TASKS_STARTED

    print(f"Logged in as {bot.user}")

    ensure_csv_exists(BUDDIES_CSV_PATH, BUDDY_FIELDS)
    ensure_csv_exists(BOOKINGS_CSV_PATH, BOOKING_FIELDS)

    synced = await bot.tree.sync(guild=GUILD_OBJ)
    print("Synced commands:", [c.name for c in synced])

    # ✅ กันสร้าง task ซ้ำเวลามี reconnect
    if not TASKS_STARTED:
        TASKS_STARTED = True
        bot.loop.create_task(weekly_announcement_dm())
        bot.loop.create_task(daily_available_buddies_dm())
        bot.loop.create_task(nightly_close_dm())

# =================================================
# Run Bot
# =================================================

if __name__ == "__main__":
    print("Starting Xin Ming bot…")
    bot.run(TOKEN)
