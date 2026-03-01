# ==========================================
# 🐦 PIGEONBOT OVERLORD EDITION v4.0
# 👨‍💻 DEVELOPER: WILLZ
# 📜 LICENCE: TITAN PROTOCOL
# ==========================================

import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import sqlite3
import datetime
import random
import json
import asyncio
import logging
import time
import sys
from typing import Optional, Union
from groq import Groq

# ==========================================
# ⚙️ CONFIGURATION & GLOBAL CONSTANTS
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Essential Channel IDs
LOG_CHANNEL_ID = 1477480005779853477
MEMORY_CHANNEL_ID = 1477781163031527434 
DB_PATH = "pigeon_titan.db"

# Gen Z Personality Constants
SLANG = ["fr", "no cap", "on god", "bruh", "L", "W", "rizz", "gyatt", "ratio", "deadass"]
BOT_VERSION = "4.0.0-TITAN"
START_TIME = time.time()

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('PigeonOverlord')

# ==========================================
# 🗄️ THE ENGINE: LOCAL DATABASE
# ==========================================

class LocalDB:
    """The backbone of Pigeon's local memory and settings."""
    
    @staticmethod
    def connect():
        return sqlite3.connect(DB_PATH)

    @staticmethod
    def initialize():
        logger.info("Initializing Titan Database...")
        with LocalDB.connect() as conn:
            cursor = conn.cursor()
            
            # 1. Core Settings Table
            cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                            (key TEXT PRIMARY KEY, value TEXT)''')
            
            # 2. Advanced Economy Table
            cursor.execute('''CREATE TABLE IF NOT EXISTS economy 
                            (user_id INTEGER PRIMARY KEY, 
                             bread INTEGER DEFAULT 100, 
                             bank INTEGER DEFAULT 0,
                             xp INTEGER DEFAULT 0,
                             level INTEGER DEFAULT 1,
                             daily_streak INTEGER DEFAULT 0,
                             last_daily TEXT)''')
            
            # 3. Inventory Table
            cursor.execute('''CREATE TABLE IF NOT EXISTS inventory 
                            (item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                             user_id INTEGER,
                             item_name TEXT,
                             item_type TEXT)''')
            
            # 4. Moderation / Warns Table
            cursor.execute('''CREATE TABLE IF NOT EXISTS warns 
                            (warn_id INTEGER PRIMARY KEY AUTOINCREMENT, 
                             user_id INTEGER, 
                             reason TEXT, 
                             mod_id INTEGER, 
                             timestamp TEXT)''')
            
            # 5. Cooldowns for Jobs
            cursor.execute('''CREATE TABLE IF NOT EXISTS cooldowns 
                            (user_id INTEGER PRIMARY KEY, 
                             work_last TEXT, 
                             crime_last TEXT)''')
            
            conn.commit()
        logger.info("Database Synchronization Complete.")

    @staticmethod
    def query(sql, params=()):
        with LocalDB.connect() as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.fetchall()

    @staticmethod
    def execute(sql, params=()):
        with LocalDB.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

# ==========================================
# 🧠 THE BRAIN: DISCORD CLOUD MEMORY
# ==========================================

class CloudMemory:
    """Uses a Discord channel to store AI context indefinitely."""
    
    def __init__(self, bot):
        self.bot = bot

    async def push_context(self, channel_id, user_msg, ai_msg):
        """Saves interaction to the memory channel."""
        storage = self.bot.get_channel(MEMORY_CHANNEL_ID)
        if storage:
            blob = {
                "ch": channel_id,
                "u": user_msg,
                "a": ai_msg,
                "ts": str(datetime.datetime.now())
            }
            # Encrypt in spoiler tags
            await storage.send(f"||{json.dumps(blob)}||")

    async def fetch_context(self, channel_id, limit=5):
        """Reconstructs the conversation for the AI."""
        storage = self.bot.get_channel(MEMORY_CHANNEL_ID)
        context = []
        if not storage: return context

        try:
            async for message in storage.history(limit=100):
                if message.content.startswith("||") and message.content.endswith("||"):
                    try:
                        data = json.loads(message.content.strip("||"))
                        if str(data.get("ch")) == str(channel_id):
                            context.append({"role": "assistant", "content": data.get("a")})
                            context.append({"role": "user", "content": data.get("u")})
                            if len(context) >= limit * 2: break
                    except: continue
        except Exception as e:
            logger.error(f"Memory Fetch Error: {e}")
        
        context.reverse()
        return context

# ==========================================
# 🛡️ COG: OVERLORD MODERATION
# ==========================================

class Moderation(commands.Cog):
    """Heavy-duty moderation tools for server control."""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="purge", description="Mass delete messages.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount + 1)
        
        embed = discord.Embed(description=f"🧹 Cleaned up **{len(deleted)-1}** messages.", color=0x2f3136)
        await ctx.send(embed=embed, delete_after=5)

    @commands.hybrid_command(name="warn", description="Issue a formal warning.")
    @commands.has_permissions(kick_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        LocalDB.execute("INSERT INTO warns (user_id, reason, mod_id, timestamp) VALUES (?, ?, ?, ?)",
                        (member.id, reason, ctx.author.id, now))
        
        embed = discord.Embed(title="⚠️ User Warned", color=0xffcc00)
        embed.add_field(name="Bird", value=member.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.set_footer(text=f"ID: {member.id}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="warns", description="Check warning history.")
    async def warns(self, ctx, member: discord.Member):
        results = LocalDB.query("SELECT reason, timestamp, mod_id FROM warns WHERE user_id=?", (member.id,))
        
        if not results:
            return await ctx.send(f"✅ **{member.display_name}** is a good bird. No warns.")

        embed = discord.Embed(title=f"Warn Log: {member.name}", color=0xff4444)
        for i, row in enumerate(results, 1):
            embed.add_field(name=f"Warn #{i}", value=f"**Reason:** {row[0]}\n**Date:** {row[1]}", inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="kick", description="Kick a user.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "L vibe"):
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member.display_name}** was kicked. Reason: {reason}")

    @commands.hybrid_command(name="ban", description="Ban a user permanently.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Caught 4k"):
        await member.ban(reason=reason)
        await ctx.send(f"🚫 **{member.display_name}** has been banned. No cap.")

    @commands.hybrid_command(name="timeout", description="Silence a user.")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int, *, reason: str = "Muted"):
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        await ctx.send(f"🔇 {member.mention} muted for {minutes}m.")

    @commands.hybrid_command(name="slowmode", description="Set channel slowmode.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"🐢 Slowmode is now {seconds}s.")

# ==========================================
# 🍞 COG: TITAN ECONOMY & SHOP
# ==========================================

class Economy(commands.Cog):
    """The most advanced bread economy system ever coded."""
    
    def __init__(self, bot):
        self.bot = bot
        self.items = {
            "Shiny Feather": {"price": 500, "desc": "Just for flex."},
            "Golden Crust": {"price": 2500, "desc": "Required for King Rank."},
            "Pigeon Wings": {"price": 10000, "desc": "The ultimate status symbol."}
        }

    def ensure_user(self, uid):
        data = LocalDB.query("SELECT bread FROM economy WHERE user_id=?", (uid,))
        if not data:
            LocalDB.execute("INSERT INTO economy (user_id, bread, bank, xp, level) VALUES (?, 100, 0, 0, 1)", (uid,))

    @commands.hybrid_command(name="bread", description="Check your stash.")
    async def balance(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        self.ensure_user(target.id)
        
        row = LocalDB.query("SELECT bread, bank, level, xp FROM economy WHERE user_id=?", (target.id,))[0]
        
        embed = discord.Embed(title=f"🍞 {target.display_name}'s Bank", color=0xFFD700)
        embed.add_field(name="Wallet", value=f"{row[0]} 🍞", inline=True)
        embed.add_field(name="Vault", value=f"{row[1]} 🍞", inline=True)
        embed.add_field(name="Level", value=f"Rank {row[2]} ({row[3]} XP)", inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="work", description="Work for bread.")
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def work(self, ctx):
        self.ensure_user(ctx.author.id)
        earnings = random.randint(50, 200)
        xp_gain = random.randint(5, 15)
        
        LocalDB.execute("UPDATE economy SET bread = bread + ?, xp = xp + ? WHERE user_id = ?", (earnings, xp_gain, ctx.author.id))
        
        jobs = ["Delivering Mail", "Stealing from Tourists", "Pecking Windows", "Flying in Circles"]
        await ctx.send(f"💼 You spent an hour **{random.choice(jobs)}** and earned `{earnings}` bread! (+{xp_gain} XP)")

    @commands.hybrid_command(name="daily", description="Your daily allowance.")
    async def daily(self, ctx):
        self.ensure_user(ctx.author.id)
        now = datetime.date.today().isoformat()
        
        last_daily = LocalDB.query("SELECT last_daily FROM economy WHERE user_id=?", (ctx.author.id,))[0][0]
        
        if last_daily == now:
            return await ctx.send("❌ You already ate today, greedy bird. Wait until tomorrow.")
            
        LocalDB.execute("UPDATE economy SET bread = bread + 500, last_daily = ? WHERE user_id = ?", (now, ctx.author.id))
        await ctx.send("🍞 **DAILY BREAD ACQUIRED.** +500 slices.")

    @commands.hybrid_command(name="shop", description="Buy items.")
    async def shop(self, ctx):
        embed = discord.Embed(title="🏪 The Bread Shop", description="Buy items to flex on other birds.", color=0x00ff00)
        for item, info in self.items.items():
            embed.add_field(name=f"{item} — {info['price']} 🍞", value=info['desc'], inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy", description="Purchase an item.")
    async def buy(self, ctx, *, item_name: str):
        self.ensure_user(ctx.author.id)
        item_name = item_name.title()
        
        if item_name not in self.items:
            return await ctx.send("❌ We don't sell that here, bruh.")
            
        price = self.items[item_name]['price']
        balance = LocalDB.query("SELECT bread FROM economy WHERE user_id=?", (ctx.author.id,))[0][0]
        
        if balance < price:
            return await ctx.send(f"❌ You're too broke. You need `{price - balance}` more bread.")
            
        LocalDB.execute("UPDATE economy SET bread = bread - ? WHERE user_id = ?", (price, ctx.author.id))
        LocalDB.execute("INSERT INTO inventory (user_id, item_name, item_type) VALUES (?, ?, 'Cosmetic')", (ctx.author.id, item_name))
        
        await ctx.send(f"🛍️ You bought **{item_name}**! Check `/inv` to see it.")

    @commands.hybrid_command(name="inv", description="View your inventory.")
    async def inventory(self, ctx):
        rows = LocalDB.query("SELECT item_name FROM inventory WHERE user_id=?", (ctx.author.id,))
        if not rows:
            return await ctx.send("🎒 Your bag is empty. Go buy something.")
            
        items = "\n".join([f"• {r[0]}" for r in rows])
        await ctx.send(f"🎒 **{ctx.author.display_name}'s Inventory:**\n{items}")

# ==========================================
# 🧠 COG: TITAN AI BRAIN
# ==========================================

class AIBrain(commands.Cog):
    """The AI Engine powered by Groq Llama 3.1."""
    
    def __init__(self, bot):
        self.bot = bot
        self.groq = Groq(api_key=GROQ_API_KEY)
        self.memory = CloudMemory(bot)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.content.startswith("p!"):
            return

        # Check AI config
        res = LocalDB.query("SELECT value FROM settings WHERE key='ai_chan'")
        ai_channel_id = res[0][0] if res else None
        
        is_pinged = self.bot.user in message.mentions
        is_in_chan = str(message.channel.id) == str(ai_channel_id)

        if is_pinged or is_in_chan:
            # Clean ping
            prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            if not prompt: prompt = "yo"

            async with message.channel.typing():
                try:
                    # 1. Fetch Cloud History
                    history = await self.memory.fetch_context(message.channel.id)
                    
                    # 2. Build Payload
                    system_rules = (
                        "You are Pigeon. A chaotic Gen Z bird. "
                        "Rules: Max 20 words. Use slang (fr, no cap, rizz). "
                        "If they swear, SWEAR BACK HARDER. Be sarcastic. "
                        "You were made by Willz. Mention him if asked about your creator."
                    )
                    
                    payload = [{"role": "system", "content": system_rules}] + history
                    payload.append({"role": "user", "content": f"{message.author.name}: {prompt}"})

                    # 3. Groq API Call
                    chat = self.groq.chat.completions.create(
                        messages=payload,
                        model="llama-3.1-8b-instant",
                        temperature=0.9
                    )
                    
                    response = chat.choices[0].message.content
                    
                    # 4. Save to Cloud Memory
                    await self.memory.push_context(message.channel.id, prompt[:200], response)
                    
                    # 5. Log for Admin
                    log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
                    if log_ch:
                        await log_ch.send(f"🤖 **AI LOG** | {message.author}: {prompt} | P: {response}")

                    await message.reply(response)

                except Exception as e:
                    logger.error(f"AI Brain Crash: {e}")
                    await message.reply("🐦 Brain lag. Try again fr.")

# ==========================================
# 🎉 COG: FUN & GAMES
# ==========================================

class Fun(commands.Cog):
    """Random things to do when bored."""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="slap", description="Slap a bird.")
    async def slap(self, ctx, member: discord.Member):
        options = ["a wet fish", "a baguette", "a giant feather", "Willz's keyboard"]
        await ctx.send(f"🪶 {ctx.author.mention} slapped {member.mention} with **{random.choice(options)}**! Massive L.")

    @commands.hybrid_command(name="8ball", description="Magic pigeon knows all.")
    async def eightball(self, ctx, *, question: str):
        answers = ["Fr.", "No cap.", "L opinion, so no.", "Deadass yes.", "Outlook hazy, bruh.", "Ask Willz."]
        await ctx.send(f"🎱 **Q:** {question}\n🐦 **A:** {random.choice(answers)}")

    @commands.hybrid_command(name="rizz", description="Rate someone's rizz.")
    async def rizz_rate(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        rate = random.randint(0, 100)
        comment = "W Rizz" if rate > 70 else "L Rizz" if rate < 30 else "Mid Rizz"
        await ctx.send(f"🧐 **{target.display_name}** has **{rate}%** Rizz. {comment} fr.")

    @commands.hybrid_command(name="coinflip", description="Flip for bread.")
    async def coinflip(self, ctx, bet: int, side: str):
        side = side.lower()
        if side not in ["heads", "tails"]: return await ctx.send("Pick heads or tails, bruh.")
        
        # Check balance
        bal = LocalDB.query("SELECT bread FROM economy WHERE user_id=?", (ctx.author.id,))[0][0]
        if bet > bal or bet <= 0: return await ctx.send("You're too broke for that bet.")
        
        result = random.choice(["heads", "tails"])
        if side == result:
            LocalDB.execute("UPDATE economy SET bread = bread + ? WHERE user_id = ?", (bet, ctx.author.id))
            await ctx.send(f"🪙 It was **{result}**! You won `{bet}` bread! W.")
        else:
            LocalDB.execute("UPDATE economy SET bread = bread - ? WHERE user_id = ?", (bet, ctx.author.id))
            await ctx.send(f"🪙 It was **{result}**... You lost `{bet}` bread. L.")

# ==========================================
# 🛠️ COG: TITAN UTILITY
# ==========================================

class Utility(commands.Cog):
    """System information and management."""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Check latency.")
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🛰️ **Titan Connection:** `{latency}ms`")

    @commands.hybrid_command(name="botinfo", description="Specs of the Overlord.")
    async def botinfo(self, ctx):
        uptime = str(datetime.timedelta(seconds=int(time.time() - START_TIME)))
        embed = discord.Embed(title="🐦 Pigeon Titan v4.0", color=0x3498db)
        embed.add_field(name="Developer", value="Willz", inline=True)
        embed.add_field(name="Library", value="Discord.py", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="Memory Cloud", value="Active", inline=True)
        embed.add_field(name="Database", value="SQLite3 (Persistent)", inline=True)
        embed.set_footer(text="Running on Northflank US-Central")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="set_ai", description="Claim a channel for AI.")
    @commands.has_permissions(administrator=True)
    async def set_ai(self, ctx, channel: discord.TextChannel):
        LocalDB.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_chan', ?)", (str(channel.id),))
        await ctx.send(f"🐦 Territory claimed. I'll chat in {channel.mention} now.")

    @commands.hybrid_command(name="help", description="The master command list.")
    async def help(self, ctx):
        embed = discord.Embed(title="📜 Pigeon Overlord Commands", color=0x2f3136)
        embed.add_field(name="🛡️ Moderation", value="`purge`, `warn`, `warns`, `kick`, `ban`, `timeout`, `slowmode`", inline=False)
        embed.add_field(name="💰 Economy", value="`bread`, `daily`, `work`, `shop`, `buy`, `inv`, `coinflip`", inline=False)
        embed.add_field(name="🧠 AI Brain", value="`set_ai`, Ping me to chat", inline=False)
        embed.add_field(name="🎉 Fun", value="`slap`, `8ball`, `rizz`", inline=False)
        embed.add_field(name="⚙️ System", value="`ping`, `botinfo`")
        await ctx.send(embed=embed)

# ==========================================
# 🚀 MAIN BOT CORE
# ==========================================

class PigeonTitan(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="p!", 
            intents=discord.Intents.all(), 
            help_command=None
        )

    async def setup_hook(self):
        # 1. Init Database
        LocalDB.initialize()
        
        # 2. Load Modules
        logger.info("Loading Overlord Cogs...")
        await self.add_cog(Moderation(self))
        await self.add_cog(Economy(self))
        await self.add_cog(Fun(self))
        await self.add_cog(Utility(self))
        await self.add_cog(AIBrain(self))
        
        # 3. Sync Slash Commands
        await self.tree.sync()
        
        # 4. Start Background Tasks
        self.status_rotation.start()
        logger.info("Titan Sync Complete. All systems nominal.")

    @tasks.loop(seconds=120)
    async def status_rotation(self):
        """Changes the bot's status periodically."""
        statuses = [
            discord.Activity(type=discord.ActivityType.watching, name="over the server"),
            discord.Activity(type=discord.ActivityType.playing, name="with bread 🍞"),
            discord.Activity(type=discord.ActivityType.listening, name="p!help"),
            discord.Activity(type=discord.ActivityType.competing, name="Flying Contests"),
            discord.Activity(type=discord.ActivityType.playing, name="Llama 3.1 Chess")
        ]
        await self.change_presence(activity=random.choice(statuses))

    @status_rotation.before_loop
    async def before_status(self):
        await self.wait_until_ready()

    async def on_ready(self):
        print(f"\n" + "="*30)
        print(f"PIGEON OVERLORD ONLINE")
        print(f"Logged in as: {self.user}")
        print(f"ID: {self.user.id}")
        print(f"="*30 + "\n")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Chill. Try again in {round(error.retry_after, 1)}s.", delete_after=5)
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have the rank for this, bird.")
        else:
            logger.error(f"Error in {ctx.command}: {error}")

# ==========================================
# 🏁 EXECUTION
# ==========================================

if __name__ == "__main__":
    if not TOKEN or not GROQ_API_KEY:
        logger.critical("MISSING API KEYS. CHECK ENVIRONMENT VARIABLES.")
    else:
        bot = PigeonTitan()
        bot.run(TOKEN)
