import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from groq import Groq

# --- Memory ---
SETTINGS_FILE = "pigeon_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"ai_channel_id": None, "poop_count": 0}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Setup ---
TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class PigeonBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all() 
        super().__init__(command_prefix="p!", intents=intents)
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.settings = load_settings()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Pigeon is live. Made by Willz (typertyper)")

bot = PigeonBot()

# --- Commands ---

@bot.tree.command(name="serverinfo", description="Nest stats check.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    owner = guild.owner.mention if guild.owner else "The Head Pigeon"
    
    embed = discord.Embed(title=f"🐦 {guild.name} NEST", color=0x3498db)
    embed.add_field(name="Birds in Nest", value=f"**{guild.member_count}**", inline=True)
    embed.add_field(name="Nest Owner", value=owner, inline=True)
    embed.add_field(name="Poops Dropped", value=f"**{bot.settings.get('poop_count', 0)}**", inline=True)
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.set_footer(text="Made by Willz (typertyper)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_ai_channel", description="Set the AI chat channel.")
@app_commands.checks.has_permissions(administrator=True)
async def set_ai(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.settings["ai_channel_id"] = channel.id
    save_settings(bot.settings)
    await interaction.response.send_message(f"🐦 Coo! This is my spot now {channel.mention}")

@bot.tree.command(name="poop", description="Drop a bomb on someone.")
async def poop(interaction: discord.Interaction, member: discord.Member):
    bot.settings["poop_count"] = bot.settings.get("poop_count", 0) + 1
    save_settings(bot.settings)
    
    embed = discord.Embed(
        title="⚠️ PIGEON STRIKE", 
        description=f"**PIGEON DON'T LIKE!**\n\n{member.mention}, you just got pooped on! 💩", 
        color=0xFF4500
    )
    embed.set_image(url="https://media.giphy.com/media/l3vR9RE5Xkk9778is/giphy.gif")
    embed.set_footer(text="Made by Willz (typertyper)")
    await interaction.response.send_message(embed=embed)

# --- AI Logic ---

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    ai_id = bot.settings.get("ai_channel_id")
    if ai_id and message.channel.id == ai_id:
        async with message.channel.typing():
            try:
                # Using the newest model so it doesn't crash
                chat_completion = bot.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system", 
                            "content": "You are Pigeon, a Gen Z bird. You are sarcastic, use slang, love bread, and hate statues. Be short and chill."
                        },
                        {"role": "user", "content": message.content}
                    ],
                    model="llama-3.3-70b-versatile",
                )
                
                response = chat_completion.choices[0].message.content
                if response:
                    await message.reply(response)
                else:
                    await message.reply("🐦 *No thoughts, head empty*")
            
            except Exception as e:
                await message.reply(f"🐦 **BRAIN FREEZE:** `{str(e)[:50]}`")

bot.run(TOKEN)
