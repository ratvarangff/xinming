import os
import csv
import asyncio
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

<<<<<<< HEAD
# ===== Load env only when .env exists =====
=======
# ===== Load env only when .env exists (local dev) =====
>>>>>>> 01a3395af38440235ef3b511be6135bd5ef24855
if os.path.exists(".env"):
    load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_ENV = os.getenv("GUILD_ID")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN from environment variables")
<<<<<<< HEAD
if not GUILD_ID_ENV:
    raise RuntimeError("Missing GUILD_ID from environment variables")

GUILD_ID = int(GUILD_ID_ENV)
GUILD_OBJ = discord.Object(id=GUILD_ID)

# ===== Roles to notify =====
ROLES_TO_NOTIFY = {"leader", "people"}
# ROLES_TO_NOTIFY = {"test"}   # ใช้ role "test" ชั่วคราวสำหรับเทสต์

# ===== CSV Storage =====
=======

if not GUILD_ID_ENV:
    raise RuntimeError("Missing GUILD_ID from environment variables")

GUILD_ID = int(GUILD_ID_ENV)
GUILD_OBJ = discord.Object(id=GUILD_ID)

# ===== Roles to notify by DM =====
ROLES_TO_NOTIFY = {"leader", "people"}  # all lowercase for easy comparison

# ===== CSV paths =====
>>>>>>> 01a3395af38440235ef3b511be6135bd5ef24855
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
    return "".join(s.split()).lower() if s else ""

def is_available_status(s: str | None):
    if not s:
        return True
    return s.strip().upper() == "AVAILABLE"

def reset_csv(path: Path, fields: list[str]):
    """รีเซ็ตไฟล์ให้เป็นของใหม่ทุกครั้งที่บอทเริ่มรัน (เหมาะกับระบบรายสัปดาห์)"""
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

def load_buddies():
    if not BUDDIES_CSV_PATH.exists():
        return []
    with BUDDIES_CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def save_buddies(rows):
    with BUDDIES_CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=BUDDY_FIELDS)
        writer.writeheader()
        for r in rows:
            status = r.get("status") or "AVAILABLE"
            writer.writerow({
                "timestamp": r.get("timestamp", ""),
                "user_id": r.get("user_id", ""),
                "name": r.get("name", ""),
                "time": r.get("time", ""),
                "topic": r.get("topic", ""),
                "status": status,
            })

def load_bookings():
    if not BOOKINGS_CSV_PATH.exists():
        return []
    with BOOKINGS_CSV_PATH.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def save_bookings(rows):
    with BOOKINGS_CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=BOOKING_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def next_booking_id(rows):
    if not rows:
        return 1
    ids = [int(r["id"]) for r in rows if r.get("id", "").isdigit()]
    return max(ids) + 1 if ids else 1

# =================================================
# DM Helpers
# =================================================

async def dm_user(uid: str, text: str):
    if not uid or not uid.isdigit():
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
# Update Slot helpers
# =================================================

def update_buddy_status(uid: str, slot: str, new_status: str):
    """อัปเดตสถานะ slot ของ Buddy (เช่น AVAILABLE / PENDING / CONFIRMED)"""
    buddies = load_buddies()
    changed = False
    for r in buddies:
        if r["user_id"] == uid and norm(r["time"]) == norm(slot):
            r["status"] = new_status
            changed = True
    if changed:
        save_buddies(buddies)

def remove_buddy_slot(uid: str, slot: str):
    """
    ลบ slot ของ Buddy ทิ้งไปเลย (ใช้กรณี Buddy เป็นคนยกเลิกเอง
    แปลว่าเขาไม่สะดวกในช่วงเวลานั้นแล้ว)
    """
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

    # กันซ้ำ
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
    save_buddies(buddies)

    user_mention = f"<@{uid}>"

    # DM ผู้ลงทะเบียน
    await dm_user(
        uid,
        f"✅ ลงทะเบียน Buddy สำเร็จ!\n"
        f"Buddy: {name} ({user_mention})\n"
        f"เวลา: {available_time}\n"
        f"หัวข้อ: {topics}"
    )

    # แจ้งทุกคนใน role (ยกเว้นเจ้าตัวเอง)
    await dm_roles(
        message=(
            "🆕 มี Buddy ลงทะเบียนเพิ่ม!\n"
            f"• {name} ({user_mention})\n"
            f"• เวลา: {available_time}\n"
            f"• หัวข้อ: {topics}\n\n"
            "ใช้ /book_buddy เพื่อจองได้เลย 💙"
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
    available = [b for b in buddies if is_available_status(b["status"])]

    if not available:
        await dm_user(uid, "ตอนนี้ยังไม่มี Buddy ที่ว่างครับ")
        await interaction.followup.send(
            "ตอนนี้ยังไม่มี Buddy ที่ว่างครับ",
            ephemeral=True,
        )
        return

    msg = "📘 **Buddy ที่ยังว่าง**\n\n"
    for b in available:
        buddy_mention = f"<@{b['user_id']}>" if b["user_id"].isdigit() else b["user_id"]
        msg += (
            f"• **{b['name']}** ({buddy_mention}) "
            f"เวลา: `{b['time']}` | หัวข้อ: `{b['topic']}`\n"
        )

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
        if norm(b["name"]) == norm(buddy_name) and is_available_status(b["status"])
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
            bk["buddy_id"] == buddy_id
            and norm(bk["time"]) == norm(booked_time)
            and bk["status"] in ("PENDING", "CONFIRMED")
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
        "buddy_name": buddy["name"],
        "budder_id": budder_id,
        "budder_name": budder.display_name,
        "time": booked_time,
        "topic": topic,
        "status": "PENDING",
        "slot_time": buddy["time"],
    })
    save_bookings(bookings)

    update_buddy_status(buddy_id, buddy["time"], "PENDING")

    # DM ถึง Buddy (ให้เห็นทั้งชื่อและ mention ของ Budder)
    await dm_user(
        buddy_id,
        "📩 มีคำขอจองคิวใหม่!\n\n"
        f"จาก: {budder.display_name} ({budder_mention})\n"
        f"เวลา (นัดจริง): {booked_time}\n"
        f"หัวข้อ: {topic}\n"
        f"Booking ID: {booking_id}\n\n"
        "หากต้องการยืนยันคิวนี้ ใช้คำสั่ง: `/confirm_booking`"
    )

    # DM ถึง Budder (ให้เห็นทั้งชื่อและ mention ของ Buddy)
    await dm_user(
        budder_id,
        "✅ ซินหมิงบันทึกคำขอจองคิวของคุณเรียบร้อยแล้ว!\n\n"
        f"Buddy: {buddy['name']} ({buddy_mention})\n"
        f"เวลา (นัดจริง): {booked_time}\n"
        f"หัวข้อ: {topic}\n"
        f"Booking ID: {booking_id}\n"
        "สถานะตอนนี้: PENDING (รอ Buddy ยืนยัน)\n"
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
@app_commands.describe(
    booking_id="หมายเลข booking",
)
async def confirm_booking(
    interaction: discord.Interaction,
    booking_id: int,
):
    buddy = interaction.user
    buddy_id = str(buddy.id)
    buddy_mention = f"<@{buddy_id}>"

    await interaction.response.defer(ephemeral=True)

    bookings = load_bookings()

    target = None
    for bk in bookings:
        if bk["id"] == str(booking_id):
            target = bk
            break

    if not target:
        await interaction.followup.send(
            "ไม่พบ booking id นี้ครับ",
            ephemeral=True,
        )
        return

    if target["buddy_id"] != buddy_id:
        await interaction.followup.send(
            "คุณไม่ใช่ Buddy ของคิวนี้ครับ",
            ephemeral=True,
        )
        return

    if target["status"] == "CONFIRMED":
        await interaction.followup.send(
            "คิวนี้ถูกยืนยันไปก่อนแล้วครับ",
            ephemeral=True,
        )
        return

    target["status"] = "CONFIRMED"
    save_bookings(bookings)

    update_buddy_status(buddy_id, target["slot_time"], "CONFIRMED")

    budder_id = target["budder_id"]
    budder_name = target["budder_name"]
    budder_mention = f"<@{budder_id}>"

    # DM ถึง Budder แจ้งชื่อ Buddy
    await dm_user(
        budder_id,
        "✅ คิว Buddy ของคุณได้รับการยืนยันแล้ว!\n\n"
        f"Buddy: {target['buddy_name']} ({buddy_mention})\n"
        f"Budder: {budder_name} ({budder_mention})\n"
        f"เวลา: {target['time']}\n"
        f"หัวข้อ: {target['topic']}"
    )

    # DM ถึง Buddy
    await dm_user(
        buddy_id,
        f"คุณได้ยืนยัน booking {booking_id} เรียบร้อยแล้วครับ\n"
        f"Budder: {budder_name} ({budder_mention})\n"
        f"เวลา: {target['time']}\n"
        f"หัวข้อ: {target['topic']}"
    )

    await interaction.followup.send(
        "ยืนยันคิวสำเร็จแล้วครับ!",
        ephemeral=True,
    )

# =================================================
# /cancel_booking
# =================================================

@bot.tree.command(
    name="cancel_booking",
    description="ยกเลิกคิวที่จองไว้ พร้อมใส่เหตุผลให้เพื่อนรู้",
    guild=GUILD_OBJ,
)
@app_commands.describe(
    booking_id="หมายเลข booking ที่ต้องการยกเลิก",
    reason="เหตุผลสั้น ๆ ที่อยากฝากบอกอีกฝ่าย (จำเป็นต้องใส่)",
)
async def cancel_booking(
    interaction: discord.Interaction,
    booking_id: int,
    reason: str,
):
    user = interaction.user
    user_id = str(user.id)
    user_mention = f"<@{user_id}>"

    await interaction.response.defer(ephemeral=True)

    bookings = load_bookings()

    target = None
    for bk in bookings:
        if bk["id"] == str(booking_id):
            target = bk
            break

    if not target:
        await interaction.followup.send(
            "ไม่พบ booking id นี้ครับ",
            ephemeral=True,
        )
        return

    buddy_id = target["buddy_id"]
    budder_id = target["budder_id"]
    buddy_name = target["buddy_name"]
    budder_name = target["budder_name"]
    buddy_mention = f"<@{buddy_id}>"
    budder_mention = f"<@{budder_id}>"
    slot_time = target.get("slot_time", "")

    # อนุญาตเฉพาะ Buddy หรือ Budder
    if user_id not in (buddy_id, budder_id):
        await interaction.followup.send(
            "คุณไม่ใช่คนในคิวนี้ จึงไม่สามารถยกเลิกได้ครับ",
            ephemeral=True,
        )
        return

    if target["status"] == "CANCELLED":
        await interaction.followup.send(
            "คิวนี้ถูกยกเลิกไปก่อนแล้วครับ",
            ephemeral=True,
        )
        return

    # บันทึกสถานะเป็น CANCELLED
    target["status"] = "CANCELLED"
    save_bookings(bookings)

    # Buddy ยกเลิก -> ลบ slot ออกจาก buddies
    if user_id == buddy_id:
        if slot_time:
            remove_buddy_slot(buddy_id, slot_time)

        # DM ถึง Budder
        await dm_user(
            budder_id,
            "❌ คิว Buddy ของคุณถูกยกเลิกแล้วนะครับ\n\n"
            f"Buddy: {buddy_name} ({buddy_mention})\n"
            f"Budder: {budder_name} ({budder_mention})\n"
            f"Booking ID: {booking_id}\n"
            f"เวลา: {target['time']}\n"
            f"หัวข้อ: {target['topic']}\n"
            f"เหตุผลจาก Buddy: {reason}"
        )

        # DM ยืนยันกลับไปที่ Buddy
        await dm_user(
            buddy_id,
            "ซินหมิงยกเลิกคิวให้เรียบร้อยแล้วครับ\n\n"
            f"คุณ: {buddy_name} ({buddy_mention})\n"
            f"Budder: {budder_name} ({budder_mention})\n"
            f"Booking ID: {booking_id}\n"
            f"เหตุผลที่แจ้งไป: {reason}"
        )

    else:
        # Budder ยกเลิก -> ปล่อย slot ให้ AVAILABLE
        if slot_time:
            update_buddy_status(buddy_id, slot_time, "AVAILABLE")

        # DM ถึง Buddy
        await dm_user(
            buddy_id,
            "❌ คิวที่ถูกจองไว้กับคุณถูกยกเลิกแล้วครับ\n\n"
            f"Buddy: {buddy_name} ({buddy_mention})\n"
            f"Budder: {budder_name} ({budder_mention})\n"
            f"Booking ID: {booking_id}\n"
            f"เวลา: {target['time']}\n"
            f"หัวข้อ: {target['topic']}\n"
            f"เหตุผลจาก Budder: {reason}"
        )

        # DM ยืนยันกลับไปที่ Budder
        await dm_user(
            budder_id,
            "ซินหมิงยกเลิกคิวให้เรียบร้อยแล้วครับ\n\n"
            f"Buddy: {buddy_name} ({buddy_mention})\n"
            f"คุณ: {budder_name} ({budder_mention})\n"
            f"Booking ID: {booking_id}\n"
            f"เหตุผลที่แจ้งไป: {reason}"
        )

    await interaction.followup.send(
        f"ยกเลิกคิวหมายเลข {booking_id} สำเร็จแล้วครับ ซินหมิงแจ้งอีกฝ่ายให้เรียบร้อยแล้ว 📨",
        ephemeral=True,
    )

# =================================================
# Background Tasks (เทสต์: weekday()==5, hour==15,...)
# =================================================

async def weekly_announcement_dm():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()

        if now.weekday() == 6 and now.hour == 10 and now.minute == 40:
            msg = (
                "🌤 **สวัสดีเช้าวันอาทิตย์นะครับ!**\n\n"
                "กำลังจะเริ่มต้นสัปดาห์ใหม่แล้ว ซินหมิงอยากชวนคุณมาวางแผนล่วงหน้า ✨\n\n"
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

        if now.weekday() == 6 and now.hour == 17 and now.minute == 0:
            buddies = load_buddies()
            available = [b for b in buddies if is_available_status(b["status"])]

            if available:
                msg = "⏰ **อัปเดต 17:00**\nBuddy ที่ยังว่าง:\n\n"
                for b in available:
                    buddy_mention = f"<@{b['user_id']}>" if b["user_id"].isdigit() else b["user_id"]
                    msg += f"• {b['name']} ({buddy_mention}) | {b['time']} | {b['topic']}\n"
            else:
                msg = "⏰ 17:00 — วันนี้ไม่มี Buddy ที่ว่างแล้วนะครับ 💙"

            await dm_roles(msg)
            await asyncio.sleep(60)

        await asyncio.sleep(30)

async def nightly_close_dm():
    """ปิดรับคิวเวลา 20:00 น. (ตอนนี้ตั้งเวลาไว้เทสต์)"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()

        if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
            msg = (
                "🌙 **ซินหมิงขอตัวไปพักแล้วนะครับ**\n"
                "วันนี้ปิดรับการจองแล้วน้า 💙😴"
            )
            await dm_roles(msg, "bye.gif")
            await asyncio.sleep(60)

        await asyncio.sleep(30)

# =================================================
# on_ready
# =================================================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Reset CSV ทุกครั้งที่เริ่มรัน (ถ้าไม่อยากรีเซ็ตทุกครั้ง ค่อยเอาออกทีหลัง)
    reset_csv(BUDDIES_CSV_PATH, BUDDY_FIELDS)
    reset_csv(BOOKINGS_CSV_PATH, BOOKING_FIELDS)

    # Sync commands ให้ guild เดียวนี้
    synced = await bot.tree.sync(guild=GUILD_OBJ)
    print("Synced commands:", [c.name for c in synced])

    # Start background tasks
    bot.loop.create_task(weekly_announcement_dm())
    bot.loop.create_task(daily_available_buddies_dm())
    bot.loop.create_task(nightly_close_dm())

# =================================================
# Run Bot
# =================================================

if __name__ == "__main__":
    print("Starting Xin Ming bot…")
    bot.run(TOKEN)
