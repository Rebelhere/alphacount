import os
from dotenv import load_dotenv
import discord
import random
from discord.ext import commands
from discord.ui import Button, View
import nest_asyncio
from itertools import product
from collections import defaultdict
import json
import re
from pymongo import MongoClient
import asyncio


# =========================
# 🔧 CONFIGURATION
# =========================
CONFIG_FILE = "config.json"
ruined = False


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
def number_to_alpha(n):
    result = ""
    while n > 0:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result

def generate_alpha_sequence():
    n = 1
    while True:
        yield number_to_alpha(n)
        n += 1

alpha_gen = generate_alpha_sequence()
alpha_sequence = []
# score
def get_sequence(n):
    while len(alpha_sequence) <= n:
        alpha_sequence.append(next(alpha_gen))
    return alpha_sequence[n]

# =========================
# 🏆 USER SCORE MANAGEMENT
# =========================
def checkuser(user_id):
    doc = scores_collection.find_one({"_id": user_id})
    if doc is None:
        scores_collection.insert_one({"_id": user_id, "correct": 0, "wrong": 0})
        return False
    return True

    

def update_user_score(user_id):
    checkuser(user_id)  # Ensure user exists in the collection
    scores_collection.update_one(
        {"_id": user_id},
        {"$inc": {"correct": 1}},
        upsert=True
    )

def update_wrong_score(user_id):
    checkuser(user_id)  # Ensure user exists in the collection
    scores_collection.update_one(
        {"_id": user_id},
        {"$inc": {"wrong": 1}},
        upsert=True
    )   

def get_user_score(user_id):
    doc = scores_collection.find_one({"_id": user_id})
    if doc is None:
        return {"correct": 0, "wrong": 0, "accuracy": 0}
    
    correct = doc.get("correct", 0)
    wrong = doc.get("wrong", 0)
    total = correct + wrong
    accuracy = (correct / total) * 100 if total > 0 else 0
    return {"correct": correct, "wrong": wrong, "accuracy": accuracy}

def calculate_score(user_id):
    doc = scores_collection.find_one({"_id": user_id})
    if doc is None:
        return 0
    return doc.get("correct", 0) - doc.get("wrong", 0)

def get_leaderboard():
    return list(scores_collection.find())

def set_leaderboard():
    users = get_leaderboard()
    leaderboard_data = []
    for user in users:
        user_id = user['_id']
        score = calculate_score(user_id)
        leaderboard_data.append({
            '_id': user_id,
            'correct': user.get('correct', 0),
            'wrong': user.get('wrong', 0),
            'score': score
        })
    return sorted(leaderboard_data, key=lambda x: x['score'], reverse=True)
# =========================
class LeaderboardView(View):
    def __init__(self, leaderboard_data, bot):
        super().__init__(timeout=60)
        self.leaderboard_data = leaderboard_data
        self.current_page = 0
        self.bot = bot
        self.entries_per_page = 10
        self.max_pages = max(1, (len(leaderboard_data) - 1) // self.entries_per_page + 1)
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        # Previous button
        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=self.current_page == 0)
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Page indicator
        page_indicator = Button(label=f"Page {self.current_page + 1}/{self.max_pages}", style=discord.ButtonStyle.secondary, disabled=True)
        self.add_item(page_indicator)
        
        # Next button
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, disabled=self.current_page == self.max_pages - 1)
        next_button.callback = self.next_page
        self.add_item(next_button)
    
    async def previous_page(self, interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=await self.get_embed(), view=self)
    
    async def next_page(self, interaction):
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=await self.get_embed(), view=self)
    
    async def get_embed(self):
        start_idx = self.current_page * self.entries_per_page
        end_idx = min(start_idx + self.entries_per_page, len(self.leaderboard_data))
        
        description = ""
        for i, entry in enumerate(self.leaderboard_data[start_idx:end_idx], start=start_idx + 1):
            try:
                user = await self.bot.fetch_user(entry['_id'])
                username = user.name
            except:
                username = f"User {entry['_id']}"
            
            description += f"#{i}. **{username}** — {entry['score']} points\n"
        
        if not description:
            description = "No scores yet!"
            
        return discord.Embed(
            title="🏆 Leaderboard", 
            description=description, 
            color=0x00ff00
        )
# =============== MONITOR TASK ===============
async def monitor_channel():
    await bot.wait_until_ready()
async def monitor_channel():
    # This function is now only for monitoring, not for validating sequences
    # to avoid race conditions with on_message
    await bot.wait_until_ready()
    channel_id = load_channel_id()
    if not channel_id:
        return

    counting_channel = bot.get_channel(channel_id)
    
    while not bot.is_closed():
        try:
            # Just keep the task alive, but don't process messages here
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[Monitor Error] {e}")
            await asyncio.sleep(1)
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.loop.create_task(monitor_channel())

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    global current_index, last_user_id, ruined

    if message.author.bot:
        return

    if re.search(r'<a?:\w+:\d+>', message.content):
        return

    if message.mentions or message.role_mentions or message.channel_mentions:
        return

    allowed_channel_id = load_channel_id()
    if allowed_channel_id is None or message.channel.id != allowed_channel_id:
        return

    content = message.content.strip()

    if content.startswith(('+', '-')):
        return

    content = content.upper()

    # If game is ruined, only resume when 'A' is typed
    if ruined:
        if content == "A":
            current_index = 1
            last_user_id = message.author.id
            user_scores[message.author.id] += 1
            update_user_score(message.author.id)
            emoji = random.choice(message.guild.emojis)
            await message.add_reaction(emoji)
            ruined = False
        else:
            return  # Ignore everything until "A"
        return

    expected = get_sequence(current_index)

    if content == expected:
        if message.author.id == last_user_id:
            await message.add_reaction("❌")
            await message.channel.send("Fuck off loner")
        else:
            emoji = random.choice(message.guild.emojis)
            await message.add_reaction(emoji)
            current_index += 1
            last_user_id = message.author.id
            user_scores[message.author.id] += 1
            update_user_score(message.author.id)
    else:
        await message.add_reaction("❌")
        await message.channel.send("You ruined it asshole 😡 next alphabet is A")
        current_index = 0
        last_user_id = None
        ruined = True

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
@bot.event
async def on_message_edit(_, after):
    global current_index, last_user_id, ruined
    
    # Only process if this is in the alphabet channel
    allowed_channel_id = load_channel_id()
    if allowed_channel_id is None or after.channel.id != allowed_channel_id:
        return
        
    await after.clear_reactions()
    await after.add_reaction("❌")
    await after.channel.send("You ruined it asshole 😡 next alphabet is A (editing won't save you)")
    current_index = 0
    last_user_id = None
    ruined = True
# 🔢 Command: Leaderboard
@bot.command(name="leaderboard")
async def leaderboard(ctx):
    leaderboard_data = set_leaderboard()
    #print(f"Leaderboard data: {leaderboard_data}")  # Debugging line
    if not leaderboard_data:
        await ctx.send("No one has scored yet!")
        return

    view = LeaderboardView(leaderboard_data, bot)
    embed = await view.get_embed()
    #print(f"Embed: {embed.to_dict()}")  # Debugging line
    # Send the embed with the view
    if embed is None:
        embed = discord.Embed(title="🏆 Leaderboard", description="No scores yet!", color=0x00ff00)
    elif isinstance(embed, discord.Embed):
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    else:
        # If embed is not an Embed object, create a default one
        embed = discord.Embed(title="🏆 Leaderboard", description="No scores yet!", color=0x00ff00)
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else ctx.guild.default_avatar.url)
    embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else ctx.guild.default_avatar.url)
    embed.color = discord.Color.blue()
    embed.timestamp = ctx.message.created_at
    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    await ctx.send(embed=embed, view=view)

# 👤 Command: My Stats
@bot.command(name="mystats")
async def mystats(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    score = get_user_score(member.id)
    player_score = calculate_score(member.id)
    description = (
        f"👤 **{member.name}**'s Stats:\n ✅ Correct: {score['correct']}\n ❌ Wrong: {score['wrong']}\n 📊 Accuracy: {score['accuracy']:.2f}%\n 🏆 Score: {player_score}\n"
    )
    if player_score > 0:
        description += " (Keep it up!)"
    else:
        description += " (You can do better!)"
    
    print(f" {description}")  # Debugging line
    # Create an embed for the stats
    embed = discord.Embed(
        title=f"{member.name}'s Stats",
        description=description,
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
    # Send the embed
    await ctx.send(embed=embed)

# =========================
# ▶️ RUN BOT
# =========================
if __name__ == "__main__":
    bot.run(os.getenv('TOKEN'))