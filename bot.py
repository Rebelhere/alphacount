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
def checkuser(user_id, guild_id):
    doc = scores_collection.find_one({"_id": user_id})
    if doc is None:
        scores_collection.insert_one({"_id": user_id, "correct": 0, "wrong": 0,"stats": {"guild_id":guild_id ,"correct": 0, "wrong": 0,}})
        return False
    doc = scores_collection.find_one({"_id": user_id, "stats.guild_id": guild_id})
    if doc is None:
        scores_collection.insert_one(
            {"_id": user_id},
            {"$push": {"stats": {"guild_id": guild_id, "correct": 0, "wrong": 0}}}
        )
        return False
    return True

    

def update_user_score(user_id,guild_id):
    checkuser(user_id,guild_id)  # Ensure user exists in the collection
    scores_collection.update_one(
        {"_id": user_id ,"stats.guild_id": guild_id},
        {"$inc": {"correct": 1,"stats.$.correct": 1}},
        upsert=True
    )

def update_wrong_score(user_id,guild_id):
    checkuser(user_id,guild_id)  # Ensure user exists in the collection
    scores_collection.update_one(
        {"_id": user_id , "stats.guild_id": guild_id},
        {"$inc": {"wrong": 1 ,"stats.$.wrong": 1}},
        upsert=True
    )   

def get_user_score(user_id, guild_id):
    doc = scores_collection.find_one({"_id": user_id})
    if doc is None:
        return {"correct": 0, "wrong": 0, "accuracy": 0}
    
    correct = doc.get("correct", 0)
    wrong = doc.get("wrong", 0)
    total = correct + wrong
    accuracy = (correct / total) * 100 if total > 0 else 0
    doc_stats = doc.get("stats", [])
    guild_stats = next((stat for stat in doc_stats if stat.get("guild_id") == guild_id), None)
    if guild_stats:
        guild_correct = guild_stats.get("correct", 0)
        guild_wrong = guild_stats.get("wrong", 0)
        guild_total = guild_correct + guild_wrong
        guild_accuracy = (guild_correct / guild_total) * 100 
    return {"correct": correct, "wrong": wrong, "accuracy": accuracy,"guild_correct": guild_stats.get("correct", 0) if guild_stats else 0, "guild_wrong": guild_stats.get("wrong", 0) if guild_stats else 0, "guild_accuracy": guild_accuracy if guild_stats else 0}

def calculate_score(user_id):
    doc = scores_collection.find_one({"_id": user_id})
    if doc is None:
        return 0
    return doc.get("correct", 0) - doc.get("wrong", 0)

def get_leaderboard():
    return list(scores_collection.find())

def set_leaderboard():
    users = get_leaderboard()
    print(f"Users in leaderboard: {users}")  # Debugging line
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
    def __init__(self, bot, guild_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id # Convert to string for consistent comparison
        self.current_page = 0
        self.entries_per_page = 10
        self.is_global = False  # Start with global leaderboard
        self.leaderboard_data = self.get_leaderboard_data()
        self.max_pages = max(1, (len(self.leaderboard_data) - 1) / self.entries_per_page + 1)
        self.update_buttons()
    
    def get_leaderboard_data(self):
        if self.is_global:
            return self.get_global_leaderboard()
        else:
            return self.get_server_leaderboard()
    
    def get_global_leaderboard(self):
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
    
    def get_server_leaderboard(self):
        users = get_leaderboard()
        leaderboard_data = []
        for user in users:
            print(f"Processing user: {user}  lala  ")  # Debugging line
            user_id = user['_id']
            if(user.get('stats') is None):
                continue
            hellos = user.get('stats')
            print(f"User stats: {hellos}")  # Debugging line
            for hello in hellos:
                if not isinstance(hello, dict):
                    continue
                print(f"Processing hello: {hello.get('guild_id',0)}  ")  # Debugging line
                gu = hello.get('guild_id', 0)
                print(f"Guild ID: {gu}, Current Guild ID: {self.guild_id}")  # Debugging line
                if gu != self.guild_id:
                    continue  # Skip users who don't have stats for this guild
                correct = hello.get('correct', 0)
                wrong = hello.get('wrong', 0)
                score = correct - wrong
                leaderboard_data.append({
                    '_id': user_id,
                    'correct': correct,
                    'wrong': wrong,
                    'score': score
            })
        return sorted(leaderboard_data, key=lambda x: x['score'], reverse=True)
    
    def update_buttons(self):
        self.clear_items()
        
        # Toggle button
        toggle_button = Button(
            label="Server Leaderboard" if self.is_global else "Global Leaderboard", 
            style=discord.ButtonStyle.primary
        )
        toggle_button.callback = self.toggle_leaderboard
        self.add_item(toggle_button)
        
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
    
    async def toggle_leaderboard(self, interaction):
        # Defer the response first
        await interaction.response.defer()
    
        self.is_global = not self.is_global
        self.current_page = 0
        self.leaderboard_data = self.get_leaderboard_data()
        self.max_pages = max(1, (len(self.leaderboard_data) - 1) // self.entries_per_page + 1)
        self.update_buttons()
    
        # Use edit_original_response instead of edit_message
        await interaction.edit_original_response(embed=await self.get_embed(), view=self)
    
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
        
        guild = self.bot.get_guild(self.guild_id)
        
        # Create a cleaner, more visually spaced description
        description = ""
        for i, entry in enumerate(self.leaderboard_data[start_idx:end_idx], start=start_idx + 1):
            try:
                user = await self.bot.fetch_user(entry['_id'])
                username = user.name
            except:
                username = f"User {entry['_id']}"
            
            # Add medal emojis for top 3
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = f"`#{i}`"
            
            # Format each entry with proper spacing and alignment
            description += f"{medal} **{username}** → **{entry['score']}** points\n"
        
        if not description:
            description = "No scores yet!"
            
        # Enhanced title and appearance
        if self.is_global:
            title = "🌎 Global Alphabet Masters"
            color = discord.Color.blue()
            thumbnail = "https://media.discordapp.net/attachments/1383926759866765554/1385324596047249438/1000306135-removebg-preview.png?ex=6855a791&is=68545611&hm=78a365dc3e4b30838bac82b43e6d71f7bee22399fd790e024e7937a8d1be5baa&=&width=281&height=281"  # Globe icon
        else:
            title = f"🏆 {guild.name} Leaderboard"
            color = discord.Color.gold()
            thumbnail = guild.icon.url if guild and guild.icon else None
        
        embed = discord.Embed(
            title=title, 
            description=description, 
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        # Ensure thumbnail is displayed
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        # Add header to make the leaderboard more readable
        embed.set_author(name=f"Top Alphabet Counters", 
                        icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        
        # Improved footer with pagination info
        embed.set_footer(text=f"Page {self.current_page+1}/{self.max_pages} • Use buttons to navigate")
        
        return embed




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
            update_user_score(message.author.id,message.guild.id)
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
            update_wrong_score(message.author.id,message.guild.id)
        else:
            emoji = random.choice(message.guild.emojis)
            await message.add_reaction(emoji)
            current_index += 1
            last_user_id = message.author.id
            user_scores[message.author.id] += 1
            update_user_score(message.author.id,message.guild.id)
    else:
        await message.add_reaction("❌")
        await message.channel.send("You ruined it asshole 😡 next alphabet is A")
        update_wrong_score(message.author.id,message.guild.id)
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

    view = LeaderboardView( bot, ctx.guild.id)
    embed = await view.get_embed()
    await ctx.send(embed=embed, view=view)

# 👤 Command: My Stats
@bot.command(name="mystats")
async def mystats(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    guild_id = ctx.guild.id
    
    # Ensure the user exists in the scores collection
    if not checkuser(member.id, guild_id):
        await ctx.send(f"No stats found for {member.name}.")
        return
    
    # Get the user's score
    score = get_user_score(member.id, guild_id)
    global_score = score['correct'] - score['wrong']
    server_score = score['guild_correct'] - score['guild_wrong']
    
    # Determine color based on score performance
    if global_score > 20:
        color = discord.Color.gold()
    elif global_score > 10:
        color = discord.Color.green()
    elif global_score > 0:
        color = discord.Color.blue()
    else:
        color = discord.Color.red()
    
    # Create embed
    embed = discord.Embed(
        title=f"📊 {member.name}'s Alphabet Counting Stats",
        color=color
    )
    
    # Add user avatar
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    
    # Add global stats
    embed.add_field(
        name="🌍 Global Stats",
        value=(
            f"✅ **Correct**: {score['correct']}\n"
            f"❌ **Wrong**: {score['wrong']}\n"
            f"📊 **Accuracy**: {score['accuracy']:.1f}%\n"
            f"🏆 **Score**: {global_score}"
        ),
        inline=True
    )
    
    # Add server stats
    embed.add_field(
        name=f"🏠 Server Stats",
        value=(
            f"✅ **Correct**: {score['guild_correct']}\n"
            f"❌ **Wrong**: {score['guild_wrong']}\n"
            f"📊 **Accuracy**: {score['guild_accuracy']:.1f}%\n"
            f"🏆 **Score**: {server_score}"
        ),
        inline=True
    )
    
    # Add a visual performance indicator
    performance_message = ""
    if global_score > 20:
        performance_message = "🌟 You're a counting master!"
    elif global_score > 10:
        performance_message = "✨ Great job keeping the alphabet going!"
    elif global_score > 0:
        performance_message = "👍 You're contributing positively!"
    else:
        performance_message = "💪 Keep practicing, you'll improve!"
    
    embed.add_field(
        name="💬 Performance",
        value=performance_message,
        inline=False
    )
    
    # Create a visual representation of accuracy
    global_bar = "■" * int(score['accuracy'] / 10) + "□" * (10 - int(score['accuracy'] / 10))
    server_bar = "■" * int(score['guild_accuracy'] / 10) + "□" * (10 - int(score['guild_accuracy'] / 10))
    
    embed.add_field(
        name="📈 Accuracy Visualization",
        value=(
            f"Global: {global_bar} {score['accuracy']:.1f}%\n"
            f"Server: {server_bar} {score['guild_accuracy']:.1f}%"
        ),
        inline=False
    )
    
    embed.set_footer(
        text=f"Requested by {ctx.author.name}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )
    
    embed.timestamp = ctx.message.created_at
    
    await ctx.send(embed=embed)

# =========================
# ▶️ RUN BOT
# =========================
if __name__ == "__main__":
    bot.run(os.getenv('TOKEN'))