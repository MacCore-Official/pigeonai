import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from groq import Groq

# --- Persistent Memory Setup ---
SETTINGS_FILE = "pigeon_settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {"ai_channel_id": None, "poop_count": 0}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Bot Initialization ---
TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class PigeonBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="p!", intents=intents)
        self.groq_client = Groq(api_key=GROQ_API_KEY)
        self.settings = load_settings()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"🐦 Pigeon is airborne and synced!")

bot = PigeonBot()

# --- Slash Commands (The UI) ---

@bot.tree.command(name="serverinfo", description="View the nest statistics.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"🐦 {guild.name}", color=0x95a5a6) # Pigeon Grey
    embed.add_field(name="Total Birds (Members)", value=guild.member_count, inline=True)
    embed.add_field(name="Nest Owner", value=guild.owner.mention, inline=True)
    embed.add_field(name="Poops Delivered", value=bot.settings.get("poop_count", 0), inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.set_footer(text="Pigeon All-in-One • Powered by Groq")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_ai_channel", description="Set the channel where Pigeon chats.")
@app_commands.checks.has_permissions(administrator=True)
async def set_ai(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.settings["ai_channel_id"] = channel.id
    save_settings(bot.settings)
    await interaction.response.send_message(f"🐦 **COO!** I will now haunt {channel.mention} with my AI brain.")

@bot.tree.command(name="poop", description="Moderate a user with a targeted pigeon strike.")
async def poop(interaction: discord.Interaction, member: discord.Member):
    bot.settings["poop_count"] += 1
    save_settings(bot.settings)
    
    embed = discord.Embed(
        title="⚠️ PIGEON MODERATION", 
        description=f"**PIGEON DON'T LIKE!**\n\n{member.mention}, you just got pooped on! 💩🐦", 
        color=0xFF4500
    )
    embed.set_image(url="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHJibXNoZzZyeXoxZzF6eXoxZzF6eXoxZzF6eXoxZzF6eXoxZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l3vR9RE5Xkk9778is/giphy.gif")
    await interaction.response.send_message(embed=embed)

# --- AI Logic (Groq) ---

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Only reply if it's the designated AI channel
    if bot.settings["ai_channel_id"] and message.channel.id == bot.settings["ai_channel_id"]:
        async with message.channel.typing():
            try:
                chat_completion = bot.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are Pigeon, a chaotic but funny Discord bot. You love bread, hate statues, and use bird puns. Occasionally say 'Coo!' or threathen to poop on things."
                        },
                        {"role": "user", "content": message.content}
                    ],
                    model="llama3-8b-8192",
                )
                await message.reply(chat_completion.choices[0].message.content)
            except Exception as e:
                print(f"Error: {e}")

bot.run(TOKEN)
