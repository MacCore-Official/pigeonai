import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import sqlite3
import datetime
import random
import json
import asyncio
from groq import Groq

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Channels
LOG_CHANNEL_ID = 1477480005779853477
MEMORY_CHANNEL_ID = 1477781163031527434  # The Discord Database Channel
DB_PATH = "pigeon_settings.db"

# ==========================================
# DATABASE ENGINES
# ==========================================

class LocalDB:
    """Handles Economy, Settings, and Warns using local SQLite"""
    @staticmethod
    def execute(query, params=()):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor

    @staticmethod
    def init():
        LocalDB.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        LocalDB.execute('CREATE TABLE IF NOT EXISTS economy (user_id INTEGER PRIMARY KEY, bread INTEGER DEFAULT 0, wallet INTEGER DEFAULT 0)')
        LocalDB.execute('CREATE TABLE IF NOT EXISTS warns (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, reason TEXT, mod_id INTEGER)')

class DiscordMemoryDB:
    """Handles the AI Memory by reading/writing to a Discord Channel!"""
    def __init__(self, bot):
        self.bot = bot

    async def save_memory(self, channel_id, user_msg, ai_msg):
        """Saves the interaction as a hidden JSON string in the memory channel."""
        mem_channel = self.bot.get_channel(MEMORY_CHANNEL_ID)
        if mem_channel:
            data = {"c": channel_id, "u": user_msg, "a": ai_msg}
            # Send as a spoiler so it doesn't look ugly if a human looks at it
            await mem_channel.send(f"||{json.dumps(data)}||")

    async def get_memory(self, channel_id, limit=6):
        """Reads the last few messages from the memory channel to rebuild history."""
        mem_channel = self.bot.get_channel(MEMORY_CHANNEL_ID)
        history = []
        if mem_channel:
            try:
                # Scan recent messages in the memory channel
                async for msg in mem_channel.history(limit=50):
                    if msg.content.startswith("||") and msg.content.endswith("||"):
                        try:
                            clean_json = msg.content.strip("||")
                            data = json.loads(clean_json)
                            # Only grab memory for the channel we are currently talking in
                            if str(data.get("c")) == str(channel_id):
                                history.append({"role": "assistant", "content": data.get("a")[:300]})
                                history.append({"role": "user", "content": data.get("u")[:300]})
                                if len(history) >= limit * 2:
                                    break
                        except json.JSONDecodeError:
                            continue
            except discord.Forbidden:
                print("❌ ERROR: Pigeon cannot read the memory channel! Check permissions.")
        
        # Reverse to chronological order
        history.reverse()
        return history

# ==========================================
# COG: MODERATION
# ==========================================

class Moderation(commands.Cog):
    """Advanced Server Moderation"""
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="purge", description="Delete messages in bulk.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 Swept away {len(deleted)-1} messages. Pigeon out.", delete_after=5)

    @commands.hybrid_command(name="kick", description="Kick a disruptive bird.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Bad vibes."):
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member.display_name}** got kicked out of the nest. Reason: {reason}")

    @commands.hybrid_command(name="ban", description="Perm-ban a user.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Caught 4k."):
        await member.ban(reason=reason)
        await ctx.send(f"🚫 **{member.display_name}** has been banned. Deadass.")

    @commands.hybrid_command(name="timeout", description="Mute someone for a specific time.")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int, *, reason: str = "Needs to chill."):
        duration = datetime.timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        await ctx.send(f"🔇 **{member.display_name}** has been silenced for {minutes} minutes.")

    @commands.hybrid_command(name="warn", description="Warn a user.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str):
        LocalDB.execute("INSERT INTO warns (user_id, reason, mod_id) VALUES (?, ?, ?)", (member.id, reason, ctx.author.id))
        await ctx.send(f"⚠️ **{member.display_name}** has been warned: {reason}")

    @commands.hybrid_command(name="warns", description="Check someone's warnings.")
    async def warns(self, ctx, member: discord.Member):
        cursor = LocalDB.execute("SELECT reason FROM warns WHERE user_id=?", (member.id,))
        warnings = cursor.fetchall()
        if not warnings:
            await ctx.send(f"✅ **{member.display_name}** has a clean record. Good bird.")
        else:
            warn_text = "\n".join([f"{i+1}. {w[0]}" for i, w in enumerate(warnings)])
            embed = discord.Embed(title=f"Warnings for {member.display_name}", description=warn_text, color=0xFF0000)
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="slowmode", description="Set channel slowmode.")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"🐢 Slowmode set to {seconds} seconds.")

    @commands.hybrid_command(name="lock", description="Lock the current channel.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🔒 Channel locked. Nobody can peck here now.")

    @commands.hybrid_command(name="unlock", description="Unlock the current channel.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🔓 Channel unlocked. Fly free.")

# ==========================================
# COG: ECONOMY
# ==========================================

class Economy(commands.Cog):
    """Bread Economy System"""
    def __init__(self, bot):
        self.bot = bot

    def get_bread(self, user_id):
        res = LocalDB.execute("SELECT bread FROM economy WHERE user_id=?", (user_id,)).fetchone()
        return res[0] if res else 0

    def add_bread(self, user_id, amount):
        current = self.get_bread(user_id)
        LocalDB.execute("INSERT OR REPLACE INTO economy (user_id, bread) VALUES (?, ?)", (user_id, current + amount))

    @commands.hybrid_command(name="bread", description="Check your bread balance.")
    async def bread(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        amount = self.get_bread(target.id)
        await ctx.send(f"🍞 **{target.display_name}** currently has `{amount}` slices of bread.")

    @commands.hybrid_command(name="daily", description="Claim your daily bread.")
    @commands.cooldown(1, 86400, commands.BucketType.user) # 24 hour cooldown
    async def daily(self, ctx):
        self.add_bread(ctx.author.id, 50)
        await ctx.send("🍞 You claimed your daily 50 slices of bread! Come back tomorrow.")

    @commands.hybrid_command(name="gamble", description="Gamble your bread.")
    async def gamble(self, ctx, amount: int):
        balance = self.get_bread(ctx.author.id)
        if amount > balance or amount <= 0:
            return await ctx.send("❌ You don't have enough bread for that bet, bro.")
        
        if random.choice([True, False]):
            self.add_bread(ctx.author.id, amount)
            await ctx.send(f"🎰 **WINNER!** You doubled your bet and won `{amount}` bread!")
        else:
            self.add_bread(ctx.author.id, -amount)
            await ctx.send(f"📉 **OOF.** You lost `{amount}` bread. Better luck next time.")

    @commands.hybrid_command(name="leaderboard", description="Top bread hoarders.")
    async def leaderboard(self, ctx):
        cursor = LocalDB.execute("SELECT user_id, bread FROM economy ORDER BY bread DESC LIMIT 10")
        rows = cursor.fetchall()
        
        lb = "\n".join([f"**#{i+1}** <@{row[0]}> - {row[1]} 🍞" for i, row in enumerate(rows)])
        embed = discord.Embed(title="🏆 Server Leaderboard", description=lb or "No one has bread.", color=0xFFD700)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="givebread", description="Give someone your bread.")
    async def givebread(self, ctx, member: discord.Member, amount: int):
        if amount <= 0: return await ctx.send("❌ Amount must be positive.")
        if self.get_bread(ctx.author.id) < amount: return await ctx.send("❌ You are too broke for that.")
        
        self.add_bread(ctx.author.id, -amount)
        self.add_bread(member.id, amount)
        await ctx.send(f"🤝 You gave **{amount}** bread to {member.mention}.")

# ==========================================
# COG: FUN
# ==========================================

class Fun(commands.Cog):
    """Fun & Games"""
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="slap", description="Slap someone.")
    async def slap(self, ctx, member: discord.Member):
        await ctx.send(f"🪶 {ctx.author.mention} slapped {member.mention} with a wet feather! EMOTIONAL DAMAGE.")

    @commands.hybrid_command(name="rate", description="Pigeon rates something.")
    async def rate(self, ctx, *, item: str):
        await ctx.send(f"🐦 I rate **{item}** a solid {random.randint(0, 10)}/10. No cap.")

    @commands.hybrid_command(name="8ball", description="Ask the magic pigeon.")
    async def eightball(self, ctx, *, question: str):
        responses = ["Fr yes.", "No cap, absolute truth.", "Bruh no.", "Deadass no.", "Maybe?", "Don't ask me that."]
        await ctx.send(f"🎱 **Question:** {question}\n🐦 **Answer:** {random.choice(responses)}")

    @commands.hybrid_command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, ctx):
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"🪙 The coin landed on: **{result}**!")

    @commands.hybrid_command(name="fact", description="Get a random pigeon fact.")
    async def fact(self, ctx):
        facts = [
            "Pigeons can recognize themselves in a mirror.",
            "Pigeons delivered messages in World War I and II.",
            "A pigeon can fly up to 90 mph!",
            "Pigeons mate for life.",
            "Bread is actually bad for pigeons' stomachs, but I love it anyway."
        ]
        await ctx.send(f"🧠 **Pigeon Fact:** {random.choice(facts)}")

# ==========================================
# COG: UTILITY
# ==========================================

class Utility(commands.Cog):
    """Server Info and Settings"""
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Check bot latency.")
    async def ping(self, ctx):
        await ctx.send(f"🏓 **Pong!** `{round(self.bot.latency * 1000)}ms`. Zooming.")

    @commands.hybrid_command(name="serverinfo", description="Get server stats.")
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"🏢 {guild.name}", color=0x3498db)
        embed.add_field(name="Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"), inline=True)
        if guild.icon: embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text="Made by Willz")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="userinfo", description="Inspect a user.")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"👤 {member.name}", color=member.color)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%b %d, %Y"), inline=True)
        embed.add_field(name="Joined Discord", value=member.created_at.strftime("%b %d, %Y"), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="set_ai", description="Set the channel where Pigeon chats.")
    @commands.has_permissions(administrator=True)
    async def set_ai(self, ctx, channel: discord.TextChannel):
        LocalDB.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_channel_id', ?)", (str(channel.id),))
        await ctx.send(f"🐦 Territory claimed. I will talk to people in {channel.mention}.")

# ==========================================
# COG: AI BRAIN (With Memory Channel & Ping)
# ==========================================

class AIBrain(commands.Cog):
    """Groq AI logic linked to Discord Channel Memory"""
    def __init__(self, bot):
        self.bot = bot
        self.groq = Groq(api_key=GROQ_API_KEY)
        self.memory = DiscordMemoryDB(bot)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if message.content.startswith('p!'): return

        # Get AI Channel
        ai_chan_data = LocalDB.execute("SELECT value FROM settings WHERE key='ai_channel_id'").fetchone()
        is_ai_channel = ai_chan_data and str(message.channel.id) == ai_chan_data[0]
        
        # Check if bot is pinged
        is_pinged = self.bot.user in message.mentions

        # If it's in the AI channel OR the bot was pinged, it talks!
        if is_ai_channel or is_pinged:
            
            # Remove the ping from the string so the AI doesn't get confused
            clean_content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
            if not clean_content:
                clean_content = "Hey Pigeon"

            async with message.channel.typing():
                try:
                    # 1. Fetch History from the Discord Memory Channel
                    history = await self.memory.get_memory(message.channel.id, limit=5)
                    
                    # 2. System Prompt
                    sys_prompt = "You are Pigeon. Gen Z bot. Max 25 words. Sarcastic, uses slang. If they swear, SWEAR BACK IN ALL CAPS. 1 emoji. Made by Willz."
                    messages_to_send = [{"role": "system", "content": sys_prompt}] + history
                    messages_to_send.append({"role": "user", "content": f"{message.author.name}: {clean_content}"})

                    # 3. Request Llama Model
                    chat = self.groq.chat.completions.create(
                        messages=messages_to_send,
                        model="llama-3.1-8b-instant",
                        temperature=0.8
                    )
                    resp = chat.choices[0].message.content

                    # 4. Save to Memory Channel
                    await self.memory.save_memory(message.channel.id, clean_content[:300], resp)
                    
                    # 5. Send to Log Channel
                    await self.log_interaction(message, resp)

                    # 6. Reply
                    await message.reply(resp)

                except Exception as e:
                    print(f"AI ERROR: {e}")
                    await message.reply(f"🐦 **BRAIN FREEZE:** Groq Rate Limit or Error.")

    async def log_interaction(self, message, resp):
        log_chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            embed = discord.Embed(title="📜 Pigeon Chat Log", color=0x2f3136, timestamp=datetime.datetime.now())
            embed.add_field(name="User", value=message.author.name)
            embed.add_field(name="Exchange", value=f"**U:** {message.content}\n**P:** {resp}", inline=False)
            embed.set_footer(text=f"Channel: {message.channel.name}")
            await log_chan.send(embed=embed)

# ==========================================
# MAIN BOT CLASS & SETUP
# ==========================================

class PigeonBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="p!", intents=discord.Intents.all(), help_command=None)

    async def setup_hook(self):
        LocalDB.init()
        # Load all the massive features
        await self.add_cog(Moderation(self))
        await self.add_cog(Economy(self))
        await self.add_cog(Fun(self))
        await self.add_cog(Utility(self))
        await self.add_cog(AIBrain(self))
        
        await self.tree.sync()
        self.status_loop.start()
        print(f"=============================")
        print(f"🐦 Pigeon Titan is ONLINE!")
        print(f"👨‍💻 Developer: Willz")
        print(f"=============================")

    @tasks.loop(seconds=60)
    async def status_loop(self):
        statuses = ["p!help", "Dominating the sky", "Eating Bread 🍞", "Made by Willz", "Watching you..."]
        await self.change_presence(activity=discord.Game(random.choice(statuses)))

    @commands.hybrid_command(name="help", description="Show all bot commands.")
    async def help_cmd(self, ctx):
        embed = discord.Embed(title="🐦 Pigeon Titan Dashboard", description="Prefix: `p!` or use `/` commands.", color=0x3498db)
        embed.add_field(name="🛡️ Mod", value="`purge`, `kick`, `ban`, `timeout`, `warn`, `warns`, `slowmode`, `lock`, `unlock`", inline=False)
        embed.add_field(name="🍞 Econ", value="`bread`, `daily`, `gamble`, `givebread`, `leaderboard`", inline=False)
        embed.add_field(name="🎉 Fun", value="`slap`, `rate`, `8ball`, `coinflip`, `fact`", inline=False)
        embed.add_field(name="⚙️ Utils", value="`ping`, `serverinfo`, `userinfo`, `set_ai`", inline=False)
        embed.set_footer(text="Made by Willz • v3.0 Ultimate")
        await ctx.send(embed=embed)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Chill bruh. Try again in {round(error.retry_after, 2)} seconds.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to do that.")
        else:
            print(f"Ignoring exception in command {ctx.command}: {error}")

# Run the Bot
bot = PigeonBot()
bot.run(TOKEN)
