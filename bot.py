import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import sqlite3
from groq import Groq

# --- Database Setup ---
# Using a local path that doesn't require special folder permissions
DB_PATH = "pigeon_infinity.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS settings 
                     (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS history 
                     (channel_id INTEGER, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DATABASE INIT ERROR: {e}")

def get_setting(key, default=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else default
    except:
        return default

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

def get_history(channel_id, limit=15):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT role, content FROM history WHERE channel_id=? ORDER BY timestamp DESC LIMIT ?", (channel_id, limit))
        rows = c.fetchall()
        conn.close()
        return [{"role": r, "content": c} for r, c in reversed(rows)]
    except:
        return []

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
        print(f"Pigeon Memory Online. Made by Willz (typertyper)")

bot = PigeonBot()

# --- Commands ---

@bot.tree.command(name="serverinfo", description="Nest stats check.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    owner = guild.owner.mention if guild.owner else "The Head Pigeon"
    poops = get_setting("poop_count", "0")
    
    embed = discord.Embed(title=f"🐦 {guild.name} NEST", color=0x3498db)
    embed.add_field(name="Birds", value=f"**{guild.member_count}**", inline=True)
    embed.add_field(name="Owner", value=owner, inline=True)
    embed.add_field(name="Poops", value=f"**{poops}**", inline=True)
    embed.set_footer(text="Made by Willz (typertyper)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_ai_channel", description="Set the AI chat channel.")
@app_commands.checks.has_permissions(administrator=True)
async def set_ai(interaction: discord.Interaction, channel: discord.TextChannel):
    set_setting("ai_channel_id", channel.id)
    await interaction.response.send_message(f"🐦 Territory claimed: {channel.mention}")

@bot.tree.command(name="poop", description="Drop a bomb.")
async def poop(interaction: discord.Interaction, member: discord.Member):
    count = int(get_setting("poop_count", "0")) + 1
    set_setting("poop_count", count)
    embed = discord.Embed(title="⚠️ PIGEON STRIKE", description=f"**POOPED ON {member.mention}!** 💩", color=0xFF4500)
    embed.set_image(url="https://media.giphy.com/media/l3vR9RE5Xkk9778is/giphy.gif")
    embed.set_footer(text="Made by Willz (typertyper)")
    await interaction.response.send_message(embed=embed)

# --- AI & Logging ---

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    ai_channel_id = get_setting("ai_channel_id")
    if ai_channel_id and str(message.channel.id) == str(ai_channel_id):
        async with message.channel.typing():
            try:
                # 1. Save and Get History
                user_msg = f"{message.author.display_name}: {message.content}"
                save_chat(message.channel.id, "user", user_msg)
                history = get_history(message.channel.id)
                
                # 2. Build Gen Z Prompt
                messages_to_send = [
                    {"role": "system", "content": "You are Pigeon, a Gen Z bird. YOU ALWAYS SWEAR AND BE RUDE AND YOU HAVE MANY ENIMES. If someone be's rude to you, you be rude back You are sarcasm peak, use slang (fr, dry, lol , getout!, bruh, diddy, diddy party), love bread, thinks <@1207182058217148427> is a fish . 1 emoji only. Remember names/facts REMEMBER EVERYTHING. Be short fr."}
                ] + history

                # 3. Call Groq
                chat_completion = bot.groq_client.chat.completions.create(
                    messages=messages_to_send,
                    model="llama-3.3-70b-versatile",
                )
                response = chat_completion.choices[0].message.content

                # 4. Save and Log
                save_chat(message.channel.id, "assistant", response)
                
                log_chan = bot.get_channel(LOG_CHANNEL_ID)
                if log_chan:
                    log_embed = discord.Embed(title="📜 Bird Log", color=0x95a5a6)
                    log_embed.add_field(name="User", value=message.author.name)
                    log_embed.add_field(name="Chat", value=f"U: {message.content}\nP: {response}")
                    await log_chan.send(embed=log_embed)

                await message.reply(response)
            
            except Exception as e:
                print(f"AI ERROR: {e}")
                await message.reply(f"🐦 **BRAIN FREEZE:** `{str(e)[:50]}`")

bot.run(TOKEN)
