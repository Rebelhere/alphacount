import os
from dotenv import load_dotenv
import discord
import random
from discord.ext import commands
import nest_asyncio
from itertools import product
from collections import defaultdict
import json
import re
import pymongo
from pymongo import MongoClient

# =========================
# 🔧 CONFIGURATION
# =========================
CONFIG_FILE = "config.json"

def load_channel_id():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f).get("allowed_channel_id")
    except FileNotFoundError:
        return None

def save_channel_id(channel_id):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"allowed_channel_id": channel_id}, f)

# =========================
# 🚀 BOT SETUP
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.emojis = True
intents.guilds = True
bot = commands.Bot(command_prefix='+', intents=intents)

load_dotenv()
nest_asyncio.apply()

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['discord_bot']
scores_collection = db['user_scores']
config_collection = db['config']

current_index = 0
last_user_id = None
user_scores = defaultdict(int)

# =========================
# 🔡 ALPHABET SEQUENCE
# =========================
def generate_alpha_sequence():
    length = 1
    while True:
        for combo in product("ABCDEFGHIJKLMNOPQRSTUVWXYZ", repeat=length):
            yield ''.join(combo)
        length += 1

alpha_gen = generate_alpha_sequence()
alpha_sequence = []

def get_sequence(n):
    while len(alpha_sequence) <= n:
        alpha_sequence.append(next(alpha_gen))
    return alpha_sequence[n]
# =========================
def update_user_score(user_id):
    scores_collection.update_one(
        {"_id": user_id},
        {"$inc": {"score": 1}},
        upsert=True
    )

def get_user_score(user_id):
    doc = scores_collection.find_one({"_id": user_id})
    return doc['score'] if doc else 0

def get_leaderboard(limit=10):
    return list(scores_collection.find().sort("score", -1).limit(limit))

# =========================
# 🤖 BOT EVENTS
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    global current_index, last_user_id

    if message.author.bot:
        return
    # 🚫 Ignore if message contains custom emojis
    if re.search(r'<a?:\w+:\d+>', message.content):
        return

    # 🚫 Ignore if message contains mentions
    if message.mentions or message.role_mentions or message.channel_mentions:
        return

    allowed_channel_id = load_channel_id()
    if allowed_channel_id is None or message.channel.id != allowed_channel_id:
        return  # Only allow messages in the set channel

    content = message.content.strip()

    if content.startswith(('+', '-')):  # Ignore bot commands and instructions
        return

    content = content.upper()
    expected = get_sequence(current_index)

    if content == expected:
        emoji = random.choice(message.guild.emojis)

        if message.author.id == last_user_id:
            await message.add_reaction("❌")
            await message.channel.send("Fuck off loner ")
        else:
            await message.add_reaction(emoji)
            current_index += 1
            last_user_id = message.author.id
            # user_scores[message.author.id] += 1
            update_user_score(message.author.id)
    else:
        await message.add_reaction("❌")
        await message.channel.send("You ruined it asshole 😡 next alphabet is A")
        current_index = 0
        last_user_id = None

@bot.event
async def on_message_edit(_, after):
    global current_index, last_user_id
    await after.clear_reactions()
    await after.add_reaction("❌")
    await after.channel.send("You ruined it asshole 😡 next alphabet is A (editing won't save you)")
    current_index = 0
    last_user_id = None

# =========================
# 🔧 ADMIN COMMANDS
# =========================
@bot.command(name='setchannel')
@commands.has_permissions(administrator=True)
async def setchannel(ctx):
    channel_id = ctx.channel.id
    save_channel_id(channel_id)
    await ctx.send(f"✅ This channel (`#{ctx.channel.name}`) has been set as the allowed counting channel.")

# =========================
# 📊 USER COMMANDS
# =========================
# 🔢 Command: Leaderboard
@bot.command(name="leaderboard")
async def leaderboard(ctx):
    leaderboard_data = get_leaderboard()
    if not leaderboard_data:
        await ctx.send("No one has scored yet!")
        return

    description = ""
    for i, entry in enumerate(leaderboard_data, start=1):
        user = await bot.fetch_user(entry['_id'])
        description += f"{i}. **{user.name}** — {entry['score']} ✅\n"

    embed = discord.Embed(title="🏆 Leaderboard", description=description, color=0x00ff00)
    await ctx.send(embed=embed)



# 👤 Command: My Stats
@bot.command(name="mystats")
async def mystats(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    score = get_user_score(member.id)
    await ctx.send(f"👤 **{member.name}**, you have **{score}** correct counts ✅.")

# =========================
# ▶️ RUN BOT
# =========================
if __name__ == "__main__":
    bot.run(os.getenv('TOKEN'))