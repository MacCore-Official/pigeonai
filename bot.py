import discord
from discord.ext import commands
from discord import app_commands
import os
import sqlite3
import datetime
import random
from groq import Groq

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LOG_CHANNEL_ID = 1477480005779853477
DB_PATH = "pigeon_infinity.db"

# --- DATABASE ENGINE ---
class Database:
    @staticmethod
    def execute(query, params=()):
        with sqlite3.connect(DB_PATH) as conn:
            return conn.execute(query, params)

    @staticmethod
    def init():
        Database.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        Database.execute('''CREATE TABLE IF NOT EXISTS history 
                            (channel_id INTEGER, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

# --- COG: MODERATION ---
class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="purge", description="Delete messages fast.")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🧹 Cleaned {len(deleted)-1} messes bruh.", delete_after=3)

    @commands.hybrid_command(name="kick", description="Kick a bird.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Vibe check failed."):
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.display_name} was booted fr.")

    @commands.hybrid_command(name="ban", description="Perm-ban a bird.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Caught 4k."):
        await member.ban(reason=reason)
        await ctx.send(f"🚫 {member.display_name} is deadass gone.")

# --- COG: AI BRAIN (The "AI Thing") ---
class AIBrain(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.groq = Groq(api_key=GROQ_API_KEY)

    def get_history(self, channel_id):
        cursor = Database.execute("SELECT role, content FROM history WHERE channel_id=? ORDER BY timestamp DESC LIMIT 6", (channel_id,))
        return [{"role": r, "content": c} for r, c in reversed(cursor.fetchall())]

    def save_msg(self, channel_id, role, content):
        Database.execute("INSERT INTO history (channel_id, role, content) VALUES (?, ?, ?)", (channel_id, role, content[:500]))
        Database.execute("DELETE FROM history WHERE timestamp NOT IN (SELECT timestamp FROM history WHERE channel_id=? ORDER BY timestamp DESC LIMIT 20)", (channel_id,))

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots or prefix commands
        if message.author.bot or message.content.startswith('p!'): 
            return
        
        # Check if this is the AI channel
        ai_chan_data = Database.execute("SELECT value FROM settings WHERE key='ai_channel_id'").fetchone()
        if ai_chan_data and str(message.channel.id) == ai_chan_data[0]:
            async with message.channel.typing():
                try:
                    self.save_msg(message.channel.id, "user", f"{message.author.name}: {message.content}")
                    history = self.get_history(message.channel.id)
                    
                    # The Vibe Logic
                    chat_completion = self.groq.chat.completions.create(
                        messages=[{"role": "system", "content": "You are Pigeon. Gen Z bird. Max 20 words. If nice, be chill (bruh, lol). If swearing, SWEAR BACK IN ALL CAPS. 1 emoji."}] + history,
                        model="llama-3.1-8b-instant"
                    )
                    response = chat_completion.choices[0].message.content

                    self.save_msg(message.channel.id, "assistant", response)
                    await self.log_interaction(message, response)
                    await message.reply(response)
                except Exception as e:
                    print(f"AI Error: {e}")
                    await message.reply(f"🐦 **BRAIN FREEZE:** `{str(e)[:40]}`")

    async def log_interaction(self, message, response):
        log_chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            embed = discord.Embed(title="📜 Bird Log", color=0x3498db, timestamp=datetime.datetime.now())
            embed.add_field(name="User", value=message.author.name, inline=True)
            embed.add_field(name="Conversation", value=f"**U:** {message.content}\n**P:** {response}", inline=False)
            embed.set_footer(text=f"Channel: {message.channel.name} | Made by Willz")
            await log_chan.send(embed=embed)

# --- MAIN BOT CLASS ---
class PigeonBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="p!", intents=discord.Intents.all())

    async def setup_hook(self):
        Database.init()
        await self.add_cog(Moderation(self))
        await self.add_cog(AIBrain(self))
        await self.tree.sync()
        print("🐦 Pigeon Pro is airborne. Made by Willz (typertyper)")

    # --- Fun Extras ---
    @commands.hybrid_command(name="ping")
    async def ping(self, ctx):
        await ctx.send(f"🏓 Pong! {round(self.latency * 1000)}ms. fr.")

    @commands.hybrid_command(name="slap", description="Slap someone with a wet feather.")
    async def slap(self, ctx, member: discord.Member):
        await ctx.send(f"🪶 {ctx.author.mention} slapped {member.mention} with a wet feather! L.")

    @commands.hybrid_command(name="rate", description="Pigeon rates your vibe.")
    async def rate(self, ctx, item: str):
        score = random.randint(0, 10)
        await ctx.send(f"🐦 I rate **{item}** a solid {score}/10. No cap.")

    # --- Setup Commands ---
    @app_commands.command(name="set_ai_channel", description="Set where Pigeon talks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_ai(self, interaction: discord.Interaction, channel: discord.TextChannel):
        Database.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('ai_channel_id', ?)", (str(channel.id),))
        await interaction.response.send_message(f"🐦 Territory claimed: {channel.mention}. Talk to me here bruh.")

bot = PigeonBot()
bot.run(TOKEN)
