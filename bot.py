import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import sqlite3
from groq import Groq

# --- Database Setup (For Forever Memory) ---
DB_PATH = "pigeon_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Table for server settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    # Table for chat history
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (channel_id INTEGER, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def save_chat(channel_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO history (channel_id, role, content) VALUES (?, ?, ?)", (channel_id, role, content))
    conn.commit()
    conn.close()

def get_history(channel_id, limit=20):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM history WHERE channel_id=? ORDER BY timestamp DESC LIMIT ?", (channel_id, limit))
    rows = c.fetchall()
    conn.close()
    # Reverse so it's in chronological order
    return [{"role": r, "content": c} for r, c in reversed(rows)]

# --- Setup ---
TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LOG_CHANNEL_ID = 1477480005779853477 

class PigeonBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="p!", intents=intents)
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        init_db()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Pigeon is immortal. Made by Willz (typertyper)")

bot = PigeonBot()

# --- Commands ---

@bot.tree.command(name="serverinfo", description="Nest stats check.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    owner = guild.owner.mention if guild.owner else "The Head Pigeon"
    poops = get_setting("poop_count", "0")
    
    embed = discord.Embed(title=f"🐦 {guild.name} NEST", color=0x3498db)
    embed.add_field(name="Birds in Nest", value=f"**{guild.member_count}**", inline=True)
    embed.add_field(name="Nest Owner", value=owner, inline=True)
    embed.add_field(name="Poops Dropped", value=f"**{poops}**", inline=True)
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="Made by Willz (typertyper)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_ai_channel", description="Set the AI chat channel.")
@app_commands.checks.has_permissions(administrator=True)
async def set_ai(interaction: discord.Interaction, channel: discord.TextChannel):
    set_setting("ai_channel_id", channel.id)
    await interaction.response.send_message(f"🐦 This is my territory now {channel.mention}")

@bot.tree.command(name="poop", description="Drop a bomb.")
async def poop(interaction: discord.Interaction, member: discord.Member):
    count = int(get_setting("poop_count", "0")) + 1
    set_setting("poop_count", count)
    embed = discord.Embed(title="⚠️ PIGEON STRIKE", description=f"**PIGEON DON'T LIKE!**\n\n{member.mention}, you just got pooped on! 💩", color=0xFF4500)
    embed.set_image(url="https://media.giphy.com/media/l3vR9RE5Xkk9778is/giphy.gif")
    embed.set_footer(text="Made by Willz (typertyper)")
    await interaction.response.send_message(embed=embed)

# --- AI & Logging Logic ---

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    ai_channel_id = get_setting("ai_channel_id")
    if ai_channel_id and str(message.channel.id) == str(ai_channel_id):
        async with message.channel.typing():
            try:
                # 1. Save User Message to Database
                user_content = f"{message.author.display_name}: {message.content}"
                save_chat(message.channel.id, "user", user_content)

                # 2. Get Forever History (Last 20 messages for context)
                history = get_history(message.channel.id)
                
                messages_to_send = [
                    {"role": "system", "content": "You are Pigeon, a Gen Z bird. You are sarcastic, use slang (no cap, fr, bruh), love bread, and hate statues. Use exactly 1 emoji. Remember everything users tell you. Be short."}
                ] + history

                # 3. Get AI Response
                chat_completion = bot.groq_client.chat.completions.create(
                    messages=messages_to_send,
                    model="llama-3.3-70b-versatile",
                )
                response = chat_completion.choices[0].message.content

                # 4. Save AI Reply to Database
                save_chat(message.channel.id, "assistant", response)

                # 5. Send Bird Logs to the Log Channel
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    log_embed = discord.Embed(title="📜 Bird Log Update", color=0x95a5a6)
                    log_embed.add_field(name="User", value=message.author.name, inline=True)
                    log_embed.add_field(name="Said", value=message.content, inline=False)
                    log_embed.add_field(name="Pigeon Replied", value=response, inline=False)
                    log_embed.set_footer(text=f"Channel: {message.channel.name}")
                    await log_channel.send(embed=log_embed)

                await message.reply(response)
            
            except Exception as e:
                await message.reply(f"🐦 **BRAIN FREEZE:** `{str(e)[:50]}`")

bot.run(TOKEN)
