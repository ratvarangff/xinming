import os
import csv
import asyncio
from datetime import datetime, date
from pathlib import Path

from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

# ===== โหลด token จาก .env =====
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("ไม่พบ DISCORD_TOKEN ในไฟล์ .env")

# ===== ใส่ Server ID =====
GUILD_ID = 1095677916144214026
GUILD_OBJ = discord.Object(id=GUILD_ID)

# ===== Role ที่ต้องการให้บอทส่ง DM =====
ROLES_TO_NOTIFY = {"leader", "people"}  # พิมพ์เล็กทั้งหมด เพื่อเทียบง่าย

# ===== ตำแหน่งไฟล์ CSV =====
BASE_DIR = Path(__file__).parent

BUDDIES_CSV_PATH = BASE_DIR / "buddies.csv"
BOOKINGS_CSV_PATH = BASE_DIR / "bookings.csv"

# buddies.csv fields
BUDDY_FIELDS = ["timestamp", "user_id", "name", "time", "topic", "status"]

# bookings.csv fields
BOOKING_FIELDS = [
    "id",
    "timestamp",
    "buddy_id",
    "buddy_name",
    "budder_id",
    "budder_name",
    "time",
    "topic",
    "status",
    "slot_time",
]

# ---------------------------------------------------
# Utility helpers
# ---------------------------------------------------

def norm(s: str) -> str:
    if s is None:
        return ""
    return "".join(s.split()).lower()

def is_available_status(status_value: str | None) -> bool:
    if not status_value:
        return True
    return status_value.strip().upper() == "AVAILABLE"

# ---------------------------------------------------
# CSV file helpers
# ---------------------------------------------------

def cleanup_old_file(path: Path, max_age_days: int = 14):
    if not path.exists():
        return
    mtime = path.stat().st_mtime
    file_date = datetime.fromtimestamp(mtime).date()
    today = date.today()
    if (today - file_date).days > max_age_days:
        path.unlink()

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
            status_raw = r.get("status")
            status_clean = status_raw if status_raw and status_raw.strip() else "AVAILABLE"

            writer.writerow({
                "timestamp": r.get("timestamp", ""),
                "user_id": r.get("user_id", ""),
                "name": r.get("name", ""),
                "time": r.get("time", ""),
                "topic": r.get("topic", ""),
                "status": status_clean,
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
            writer.writerow({
                "id": r.get("id", ""),
                "timestamp": r.get("timestamp", ""),
                "buddy_id": r.get("buddy_id", ""),
                "buddy_name": r.get("buddy_name", ""),
                "budder_id": r.get("budder_id", ""),
                "budder_name": r.get("budder_name", ""),
                "time": r.get("time", ""),
                "topic": r.get("topic", ""),
                "status": r.get("status", "PENDING"),
                "slot_time": r.get("slot_time", ""),
            })

def next_booking_id(rows):
    if not rows:
        return 1
    max_id = 0
    for r in rows:
        try:
            max_id = max(max_id, int(r.get("id", 0)))
        except:
            pass
    return max_id + 1

# ---------------------------------------------------
# DM helper
# ---------------------------------------------------

async def dm_user(user_id_str: str, content: str):
    if not user_id_str or not user_id_str.isdigit():
        return
    user_id = int(user_id_str)

    user_obj = bot.get_user(user_id)
    if user_obj is None:
        try:
            user_obj = await bot.fetch_user(user_id)
        except:
            return

    try:
        dm = await user_obj.create_dm()
        await dm.send(content)
    except discord.Forbidden:
        pass
    except:
        pass

# ---------------------------------------------------
# Update Buddy Slot
# ---------------------------------------------------

def update_buddy_status(buddy_user_id: str, time_str: str, new_status: str):
    buddies = load_buddies()
    changed = False

    for row in buddies:
        if row.get("user_id") == buddy_user_id and norm(row.get("time", "")) == norm(time_str):
            row["status"] = new_status
            changed = True

    if changed:
        save_buddies(buddies)

# ---------------------------------------------------
# Bot Setup
# ---------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------
# Commands
# ---------------------------------------------------

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send("心明 พร้อมช่วยแล้วครับ! ลองใช้ /register_buddy หรือ /book_buddy ดูได้เลยนะครับ")

# ---------------------------------------------------
# /register_buddy
# ---------------------------------------------------

@bot.tree.command(
    name="register_buddy",
    description="ลงทะเบียนเวลาว่างและหัวข้อที่สามารถเป็น Buddy ได้",
    guild=GUILD_OBJ,
)
@app_commands.describe(
    name="ชื่อเล่น Buddy เช่น buddy-front",
    available_time="วันและเวลาว่าง เช่น อาทิตย์ 19.00-21.00",
    topics="หัวข้อที่สอนได้ เช่น BM, Why I Join, ขายหนังสือ",
)
async def register_buddy(
    interaction: discord.Interaction,
    name: str,
    available_time: str,
    topics: str,
):
    user = interaction.user
    user_id_str = str(user.id)

    buddies = load_buddies()

    # กันข้อมูลซ้ำ
    for row in buddies:
        if (
            row.get("user_id") == user_id_str
            and norm(row.get("time", "")) == norm(available_time)
            and norm(row.get("topic", "")) == norm(topics)
        ):
            await interaction.response.send_message(
                "⚠️ คุณได้ลงเวลานี้และหัวข้อนี้ไว้แล้ว ซินหมิง DM รายละเอียดให้แล้วนะครับ 📨",
                ephemeral=True,
            )
            await dm_user(
                user_id_str,
                "⚠️ คุณลงเวลานี้ + หัวข้อนี้ไว้แล้ว ไม่จำเป็นต้องลงซ้ำครับ",
            )
            return

    timestamp = datetime.now().isoformat(timespec="seconds")

    new_row = {
        "timestamp": timestamp,
        "user_id": user_id_str,
        "name": name,
        "time": available_time,
        "topic": topics,
        "status": "AVAILABLE",
    }

    buddies.append(new_row)
    save_buddies(buddies)

    await dm_user(
        user_id_str,
        f"✅ ลงทะเบียน Buddy เรียบร้อย!\n\n"
        f"ชื่อ: {name}\n"
        f"เวลา: {available_time}\n"
        f"หัวข้อ: {topics}"
    )

    await interaction.response.send_message(
        "✅ คุณลงเวลา Buddy สำเร็จแล้วครับ ซินหมิงส่งข้อมูลไปที่ DM แล้ว 📨",
        ephemeral=True,
    )

# ---------------------------------------------------
# /list_buddies
# ---------------------------------------------------

@bot.tree.command(
    name="list_buddies",
    description="ดูรายชื่อ Buddy ที่ยังว่าง (ส่งรายการไปที่ DM)",
    guild=GUILD_OBJ,
)
async def list_buddies(interaction: discord.Interaction):
    user = interaction.user
    user_id_str = str(user.id)

    buddies = load_buddies()
    available = [b for b in buddies if is_available_status(b.get("status"))]

    if not available:
        await interaction.response.send_message("ตอนนี้ยังไม่มี Buddy ที่ว่างครับ", ephemeral=True)
        await dm_user(user_id_str, "ตอนนี้ยังไม่มี Buddy ที่ว่างเลยครับ 🙏")
        return

    lines = []
    for b in available:
        buddy_id = b.get("user_id", "")
        buddy_mention = f"<@{buddy_id}>" if buddy_id.isdigit() else buddy_id

        lines.append(
            f"• **{b.get('name','')}** ({buddy_mention})\n"
            f"  เวลา: `{b.get('time','')}` | หัวข้อ: `{b.get('topic','')}`\n"
        )

    final_text = "📘 **Buddy ที่ยังว่าง (AVAILABLE)**\n\n" + "\n".join(lines)

    await dm_user(user_id_str, final_text)
    await interaction.response.send_message("📨 ส่งรายการ Buddy ไปที่ DM แล้วครับ", ephemeral=True)

# ---------------------------------------------------
# /book_buddy
# ---------------------------------------------------

@bot.tree.command(
    name="book_buddy",
    description="Budder จองคิวเพื่อฝึกกับ Buddy",
    guild=GUILD_OBJ,
)
@app_commands.describe(
    buddy_name="ชื่อ Buddy เช่น buddy-front",
    booked_time="เวลาที่อยากนัดจริง เช่น อาทิตย์ 20.00-21.00",
    topic="หัวข้อที่อยากซ้อม",
)
async def book_buddy(
    interaction: discord.Interaction,
    buddy_name: str,
    booked_time: str,
    topic: str,
):
    budder = interaction.user
    budder_id_str = str(budder.id)

    buddies = load_buddies()

    # หา Buddy ตามชื่อ + ต้อง AVAILABLE
    matches = [
        b for b in buddies
        if norm(b.get("name", "")) == norm(buddy_name)
        and is_available_status(b.get("status"))
    ]

    if not matches:
        await interaction.response.send_message(
            "❌ ไม่พบ Buddy ชื่อนี้ที่ยังว่างครับ เช็คชื่อใน /list_buddies ก่อนนะ",
            ephemeral=True,
        )
        await dm_user(budder_id_str, "❌ ไม่พบ Buddy ชื่อนี้ที่ยังว่างครับ")
        return

    if len(matches) > 1:
        await interaction.response.send_message(
            "⚠️ พบชื่อ Buddy ซ้ำหลายคน กรุณาระบุชื่อให้ชัดเจนกว่านี้นะครับ",
            ephemeral=True,
        )
        await dm_user(budder_id_str, "⚠️ พบ Buddy ชื่อนี้หลาย slot ครับ")
        return

    buddy = matches[0]
    buddy_id_str = buddy.get("user_id", "")
    buddy_slot_time = buddy.get("time", "")
    buddy_display_name = buddy.get("name", "")

    bookings = load_bookings()

    # กัน double booking เวลาเดียวกัน
    for bk in bookings:
        if (
            bk.get("buddy_id") == buddy_id_str
            and norm(bk.get("time", "")) == norm(booked_time)
            and bk.get("status") in ("PENDING", "CONFIRMED")
        ):
            await interaction.response.send_message(
                "⚠️ Buddy มีคิวเวลาเดียวกันอยู่แล้วครับ",
                ephemeral=True,
            )
            await dm_user(budder_id_str, "⚠️ เวลานี้ Buddy ถูกจองแล้ว")
            return

    booking_id = next_booking_id(bookings)
    timestamp = datetime.now().isoformat(timespec="seconds")

    new_booking = {
        "id": str(booking_id),
        "timestamp": timestamp,
        "buddy_id": buddy_id_str,
        "buddy_name": buddy_display_name,
        "budder_id": budder_id_str,
        "budder_name": budder.display_name,
        "time": booked_time,
        "topic": topic,
        "status": "PENDING",
        "slot_time": buddy_slot_time,
    }

    bookings.append(new_booking)
    save_bookings(bookings)

    update_buddy_status(buddy_id_str, buddy_slot_time, "PENDING")

    # DM Buddy
    await dm_user(
        buddy_id_str,
        f"📩 มีคำขอจองคิวจาก **{budder.display_name}**\n"
        f"เวลา (นัดจริง): {booked_time}\n"
        f"หัวข้อ: {topic}\n"
        f"Booking ID: `{booking_id}`\n\n"
        f"ยืนยันได้ที่คำสั่ง `/confirm_booking booking_id:{booking_id}`"
    )

    # DM Budder
    await dm_user(
        budder_id_str,
        f"✅ ซินหมิงบันทึกคำขอจองคิวแล้ว!\n\n"
        f"Buddy: {buddy_display_name}\n"
        f"เวลา: {booked_time}\n"
        f"หัวข้อ: {topic}\n"
        f"Booking ID: `{booking_id}`\n"
        "ตอนนี้สถานะเป็น **PENDING**"
    )

    await interaction.response.send_message(
        "✅ จองคิวเรียบร้อยครับ ซินหมิงส่งรายละเอียดไปที่ DM แล้ว",
        ephemeral=True,
    )

# ---------------------------------------------------
# /confirm_booking
# ---------------------------------------------------

@bot.tree.command(
    name="confirm_booking",
    description="Buddy ใช้คำสั่งนี้เพื่อยืนยันคิวที่ Budder จอง",
    guild=GUILD_OBJ,
)
@app_commands.describe(
    booking_id="รหัสการจอง (ตัวเลข)"
)
async def confirm_booking(
    interaction: discord.Interaction,
    booking_id: int,
):
    buddy = interaction.user
    buddy_id_str = str(buddy.id)

    bookings = load_bookings()
    target = None

    for bk in bookings:
        try:
            if int(bk.get("id", 0)) == booking_id:
                target = bk
                break
        except:
            pass

    if target is None:
        await interaction.response.send_message("❌ ไม่พบ booking id นี้", ephemeral=True)
        await dm_user(buddy_id_str, "❌ ไม่พบ booking id นี้เลยครับ")
        return

    if target.get("buddy_id") != buddy_id_str:
        await interaction.response.send_message("⚠️ คุณไม่ใช่ Buddy ของคิวนี้", ephemeral=True)
        await dm_user(buddy_id_str, "⚠️ คุณไม่ใช่ Buddy เจ้าของคิวนี้ครับ")
        return

    if target.get("status") == "CONFIRMED":
        await interaction.response.send_message("ℹ️ คิวนี้ถูกยืนยันไปแล้ว", ephemeral=True)
        await dm_user(buddy_id_str, "ℹ️ คิวนี้ถูกยืนยันไปก่อนหน้าแล้วครับ")
        return

    target["status"] = "CONFIRMED"
    save_bookings(bookings)

    slot_time = target.get("slot_time", "")
    update_buddy_status(buddy_id_str, slot_time, "CONFIRMED")

    # DM Budder
    await dm_user(
        target.get("budder_id", ""),
        f"✅ คิว Buddy ของคุณได้รับการยืนยันแล้ว!\n"
        f"Buddy: {target.get('buddy_name','')}\n"
        f"เวลา: {target.get('time','')}\n"
        f"หัวข้อ: {target.get('topic','')}"
    )

    # DM Buddy
    await dm_user(
        buddy_id_str,
        f"✅ คุณได้ยืนยันคิวหมายเลข `{booking_id}` เรียบร้อยแล้วครับ!"
    )

    await interaction.response.send_message(
        f"✅ ยืนยัน booking `{booking_id}` แล้ว",
        ephemeral=True,
    )

# ---------------------------------------------------
# Weekly Announcement DM (เฉพาะ role leader & people)
# ---------------------------------------------------

async def weekly_announcement_dm():
    await bot.wait_until_ready()

    while not bot.is_closed():
        now = datetime.now()

        if now.weekday() == 6 and now.hour == 11 and now.minute == 24:
            msg = (
                "🌤 **สวัสดีเช้าวันอาทิตย์นะครับ!**\n\n"
                "กำลังจะเริ่มต้นสัปดาห์ใหม่แล้ว ซินหมิงอยากชวนคุณมาวางแผนล่วงหน้า ✨\n\n"
                "• ลงเป็น Buddy → ใช้คำสั่ง: `/register_buddy`\n"
                "• จองคิวซ้อม → ใช้คำสั่ง: `/book_buddy`\n\n"
                "ขอให้เริ่มสัปดาห์ใหม่อย่างมีพลังนะครับ 💙\n"
                "— ซินหมิง 🧘‍♂️"
            )

            for guild in bot.guilds:
                if guild.id != GUILD_ID:
                    continue

                for member in guild.members:
                    if member.bot:
                        continue

                    # ตรวจ role
                    has_role = any(
                        (role.name.lower() in ROLES_TO_NOTIFY)
                        for role in member.roles
                    )
                    if not has_role:
                        continue

                    try:
                        dm = await member.create_dm()
                        file = discord.File("sunday.gif")  # ไฟล์ GIF ที่อยู่ในโฟลเดอร์เดียวกับ bot.py
                        await dm.send(msg, file=file)

                    except discord.Forbidden:
                        continue
                    except Exception as e:
                        print(f"Error DM to {member.id}: {e}")

            await asyncio.sleep(60)

        await asyncio.sleep(30)

# ---------------------------------------------------
# on_ready
# ---------------------------------------------------

@bot.event
async def on_ready():
    cleanup_old_file(BUDDIES_CSV_PATH, max_age_days=14)
    cleanup_old_file(BOOKINGS_CSV_PATH, max_age_days=14)

    # Sync global เพื่อเคลียร์คำสั่งเก่า
    try:
        g = await bot.tree.sync()
        print(f"Synced {len(g)} GLOBAL commands")
    except Exception as e:
        print(f"Global sync failed: {e}")

    # Sync เฉพาะ guild
    synced = await bot.tree.sync(guild=GUILD_OBJ)
    print(f"Synced {len(synced)} GUILD commands to guild {GUILD_ID}")

    print(f"Logged in as {bot.user}")

    # เริ่ม task weekly DM
    bot.loop.create_task(weekly_announcement_dm())

# ---------------------------------------------------
# Run Bot
# ---------------------------------------------------

if __name__ == "__main__":
    print("Starting Xin Ming bot…")
    bot.run(TOKEN)
