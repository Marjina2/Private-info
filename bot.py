import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
from config import TOKEN, OWNER_ID, BOT_PREFIX, HENRIK_API_KEY
from settings import Settings
import asyncio
import logging
import requests
from typing import List, Dict, Optional, Literal
from discord.ui import Button, View
from database import (
    log_unauthorized_access, 
    get_unauthorized_users,
    save_gemini_key,
    get_gemini_key,
    save_bot_prefix,
    get_bot_prefix,
    save_allowed_users,
    get_allowed_users,
    add_allowed_user,
    remove_allowed_user,
    save_note,
    get_notes,
    update_note,
    delete_note,
    save_trigger,
    get_triggers,
    delete_trigger,
    update_trigger,
    add_to_blacklist,
    remove_from_blacklist,
    is_blacklisted,
    get_blacklist
)
import aiohttp
import google.generativeai as genai
import io
import random
from memes import MEME_TEMPLATES, get_random_templates
from urllib.parse import quote
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import yt_dlp
import telegram
from telegram.error import TelegramError

# Setup logging
logging.basicConfig(level=logging.INFO)

# Create intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True  # Add this for status/activity info

settings = Settings()

# Add these constants near the top of the file
HENRIK_API_BASE = "https://api.henrikdev.xyz/valorant"
HEADERS = {
    "Authorization": HENRIK_API_KEY
} if HENRIK_API_KEY != "your_henrik_api_key_here" else {}

# Add this constant with the regions
VALORANT_REGIONS = ['eu', 'na', 'ap', 'kr', 'latam', 'br']

# Add this near your other imports
LEONARDO_API_KEY = os.getenv("LEONARDO_API_KEY")  # Add this to your .env file
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")  # Add this to your .env file

# Add your TMDB API key to .env file
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# Add these streaming services to check
STREAMING_SERVICES = {
    "Netflix": "https://www.netflix.com/search?q={}",
    "Amazon Prime": "https://www.amazon.com/s?k={}&i=instant-video",
    "Disney+": "https://www.disneyplus.com/search?q={}",
    "Hulu": "https://www.hulu.com/search?q={}",
    "HBO Max": "https://play.hbomax.com/search?query={}"
}

# Add these aggregator sites that legally track where movies are available
MOVIE_SEARCH_SITES = {
    "JustWatch": "https://www.justwatch.com/us/search?q={}",
    "Reelgood": "https://reelgood.com/search?q={}",
    "MovieFone": "https://www.moviefone.com/search/?q={}",
    "Where to Watch": "https://www.wheretowatch.com/search?term={}"
}

# Replace the MOVIE_SITES dictionary with this code
def parse_movie_sites():
    movie_sites = {}
    sites_str = os.getenv("MOVIE_SITES", "")
    
    if not sites_str:
        return {}
        
    for site in sites_str.split(";"):
        if not site:
            continue
            
        try:
            name, url, movie_selector, title_selector, link_selector = site.split("|")
            movie_sites[name] = {
                "url": url,
                "movie_selector": movie_selector,
                "title_selector": title_selector,
                "link_selector": link_selector
            }
        except Exception as e:
            print(f"Error parsing movie site config: {e}")
            continue
            
    return movie_sites

# Initialize MOVIE_SITES from environment
MOVIE_SITES = parse_movie_sites()

# Add these near your other environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class PrivateBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=settings.get("prefix"),
            intents=intents,
            application_id=1355108574245814393
        )
        self.gemini_sessions = {}

    async def setup_hook(self):
        print("Loading settings from Supabase...")
        try:
            # Load settings from Supabase
            prefix = await get_bot_prefix()
            allowed_users = await get_allowed_users()
            
            # Update local settings
            settings.set("prefix", prefix)
            settings.set("allowed_users", allowed_users)
            
            print("Settings loaded successfully!")
            
            # Register commands
            print("Setting up commands...")
            try:
                commands = await self.tree.sync()
                print(f"Successfully synced {len(commands)} commands!")
            except Exception as e:
                print(f"Error syncing commands: {e}")
                
        except Exception as e:
            print(f"Error in setup: {e}")

# Create the bot instance before using it
bot = PrivateBot()

# Then add the events
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Game(name="Serving Shiraken12T"))
    print("Bot is ready!")

@bot.event
async def on_guild_join(guild: discord.Guild):
    # Scan for authorized users
    auth_users = []
    for member in guild.members:
        if member.id in settings.get("allowed_users"):
            auth_users.append(member.mention)

    # Create a single, clean embed
    embed = discord.Embed(
        title="👋 Hello! I'm Private Info Bot!",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    if auth_users:
        # Found authorized users
        embed.description = (
            "Thanks for inviting me! I'm ready to help.\n\n"
            f"**✅ Authorized Users Found:**\n{', '.join(auth_users)}\n\n"
            "Feel free to use my commands anytime!"
        )
    else:
        # No authorized users found
        embed.description = (
            "Thanks for the invitation! However, I couldn't find any authorized users in this server.\n\n"
            "⚠️ **Security Notice:**\n"
            "• For security reasons, I can only be used by authorized users\n"
            "• I'll stay for 5 minutes in case an authorized user joins\n"
            "• After that, I'll need to leave the server\n\n"
            "🔗 **While I'm here...**\n"
            "Check out [URA](https://urabeta.site), a revolutionary AI research platform!\n"
            "• Cutting-edge AI tools\n"
            "• Advanced analytics\n"
            "• Beta access available now"
        )
        embed.set_footer(text="I'll leave in 5 minutes if no authorized users join")

    # Find a suitable channel and send the embed
    welcome_channel = None
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            welcome_channel = channel
            break

    if welcome_channel:
        await welcome_channel.send(embed=embed)

        # If no auth users, wait and then leave
        if not auth_users:
            await asyncio.sleep(300)  # Wait 5 minutes
            if not any(member.id in settings.get("allowed_users") for member in guild.members):
                await guild.leave()

# Then add the commands
@bot.tree.command(
    name="hello",
    description="Get a greeting from the bot"
)
async def hello(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    await interaction.response.send_message(f"Hello {interaction.user.name}! How can I help you today?")

@bot.tree.command(
    name="status",
    description="Check bot status and latency"
)
async def status(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    await interaction.response.send_message(f"Bot is running normally\nLatency: {round(bot.latency * 1000)}ms")

@bot.tree.command(
    name="note",
    description="Save a private note"
)
async def note(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    
    modal = NoteModal()
    await interaction.response.send_modal(modal)

class NoteModal(discord.ui.Modal, title="Create Note"):
    note_title = discord.ui.TextInput(
        label="Title",
        placeholder="Enter note title",
        required=True,
        max_length=100
    )
    note_content = discord.ui.TextInput(
        label="Content",
        placeholder="Enter your note content",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if await save_note(self.note_title.value, self.note_content.value):
            await interaction.followup.send("Note saved successfully!", ephemeral=True)
        else:
            await interaction.followup.send("Error saving note.", ephemeral=True)

@bot.tree.command(
    name="viewnotes",
    description="View all saved notes"
)
async def viewnotes(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    class NotesView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)
            self.page = 0
            self.notes = []
            self.total_notes = 0
            
        async def load_page(self):
            self.notes, self.total_notes = await get_notes(self.page)
            
        @property
        def max_pages(self):
            return (self.total_notes - 1) // 5  # 5 notes per page
            
        def get_embed(self):
            embed = discord.Embed(
                title="📝 Your Notes",
                description="Select a note number to view its contents",
                color=int(settings.get("embed_color"), 16)
            )
            
            for idx, note in enumerate(self.notes, start=self.page * 5 + 1):
                embed.add_field(
                    name=f"#{idx}. {note['title']}",
                    value=f"Created: {note['created_at'][:19].replace('T', ' ')}",
                    inline=False
                )
            
            embed.set_footer(text=f"Page {self.page + 1}/{self.max_pages + 1}")
            return embed
        
        @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, disabled=True)
        async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = max(0, self.page - 1)
            await self.load_page()
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        
        @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = min(self.max_pages, self.page + 1)
            await self.load_page()
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        
        @discord.ui.button(label="View Note", style=discord.ButtonStyle.green)
        async def view_note(self, interaction: discord.Interaction, button: discord.ui.Button):
            modal = NoteNumberModal(self.notes)
            await interaction.response.send_modal(modal)
        
        @discord.ui.button(label="Delete Notes", style=discord.ButtonStyle.red)
        async def delete_notes(self, interaction: discord.Interaction, button: discord.ui.Button):
            modal = DeleteNotesModal(self.notes)
            await interaction.response.send_modal(modal)
        
        def update_buttons(self):
            self.prev_button.disabled = self.page == 0
            self.next_button.disabled = self.page >= self.max_pages

    # Create view and load first page
    view = NotesView()
    await view.load_page()
    
    if view.total_notes == 0:
        await interaction.response.send_message("No notes found!", ephemeral=True)
        return
        
    await interaction.response.send_message(
        embed=view.get_embed(),
        view=view,
        ephemeral=True
    )

class NoteNumberModal(discord.ui.Modal, title="View Note"):
    def __init__(self, notes):
        super().__init__()
        self.notes = notes
        self.note_number = discord.ui.TextInput(
            label="Note Number",
            placeholder=f"Enter a number between 1 and {len(notes)}",
            required=True
        )
        self.add_item(self.note_number)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            note_idx = int(self.note_number.value) - 1
            if 0 <= note_idx < len(self.notes):
                note = self.notes[note_idx]
                
                class NoteView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=180)
                    
                    @discord.ui.button(label="Edit", style=discord.ButtonStyle.primary)
                    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                        class EditNoteModal(discord.ui.Modal, title=f"Edit Note: {note['title']}"):
                            content = discord.ui.TextInput(
                                label="Content",
                                default=note['content'],
                                style=discord.TextStyle.paragraph,
                                required=True
                            )
                            
                            async def on_submit(self, interaction: discord.Interaction):
                                if await update_note(note['id'], self.content.value):
                                    await interaction.response.send_message("Note updated!", ephemeral=True)
                                else:
                                    await interaction.response.send_message("Error updating note.", ephemeral=True)
                        
                        await interaction.response.send_modal(EditNoteModal())
                
                # Create embed to show note
                embed = discord.Embed(
                    title=note['title'],
                    description=note['content'],
                    color=int(settings.get("embed_color"), 16)
                )
                embed.set_footer(text=f"Created: {note['created_at'][:19].replace('T', ' ')}")
                
                await interaction.response.send_message(
                    embed=embed,
                    view=NoteView(),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("Invalid note number!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number!", ephemeral=True)

@bot.tree.command(
    name="settings",
    description="Manage bot settings (Owner Only)"
)
async def settings_menu(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await unauthorized_message(interaction)
        return

    embed = discord.Embed(
        title="Bot Settings",
        description="Choose a setting to modify:",
        color=int(settings.get("embed_color"), 16)
    )
    embed.add_field(name="Current Settings", value=
        f"**Prefix:** {settings.get('prefix')}\n"
        f"**Status:** {settings.get('status_message')}\n"
        f"**Allowed Users:** {', '.join([f'<@{uid}>' for uid in settings.get('allowed_users')])}\n"
        f"**Embed Color:** {settings.get('embed_color')}"
    )

    class SettingsView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)  # 3 minutes timeout

        @discord.ui.button(label="Add User", style=discord.ButtonStyle.green)
        async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                modal = AddUserModal()
                await interaction.response.send_modal(modal)
            except Exception as e:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
                print(f"Error in add_user: {e}")

        @discord.ui.button(label="Remove User", style=discord.ButtonStyle.red)
        async def remove_user(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                modal = RemoveUserModal()
                await interaction.response.send_modal(modal)
            except Exception as e:
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
                print(f"Error in remove_user: {e}")

        @discord.ui.button(label="Set Gemini API Key", style=discord.ButtonStyle.gray)
        async def set_gemini_key(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                # Get current key from Supabase
                current_key = await get_gemini_key()
                modal = GeminiKeyModal(current_key)
                await interaction.response.send_modal(modal)
            except Exception as e:
                print(f"Error showing Gemini key modal: {e}")
                await interaction.response.send_message(
                    "An error occurred while loading the API key settings.",
                    ephemeral=True
                )

    # Make the settings menu ephemeral
    await interaction.response.send_message(
        embed=embed, 
        view=SettingsView(), 
        ephemeral=True
    )

class MatchView(View):
    def __init__(self, matches: List[Dict], current_index: int = 0):
        super().__init__(timeout=180)  # 3 minutes timeout
        self.matches = matches
        self.current_index = current_index
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.current_index > 0:
            self.add_item(Button(label="◀️ Previous", custom_id="prev", style=discord.ButtonStyle.blurple))
        if self.current_index < len(self.matches) - 1:
            self.add_item(Button(label="Next ▶️", custom_id="next", style=discord.ButtonStyle.blurple))

    async def create_match_embed(self, match: Dict) -> discord.Embed:
        meta = match.get('metadata', {})
        teams = match.get('teams', {})
        player_stats = match.get('player_stats', {})
        
        # Get map image for embed
        map_name = meta.get('map', 'Unknown')
        map_image = f"https://media.valorant-api.com/maps/{map_name.lower()}/splash.png"
        
        embed = discord.Embed(
            title=f"Match {self.current_index + 1}/5: {map_name}",
            description=f"**Mode:** {meta.get('mode')}\n─────────────",  # Divider line
            color=int(settings.get("embed_color"), 16)
        )
        
        # Set map image as embed image
        embed.set_image(url=map_image)
        
        # Player performance
        stats = player_stats.get('stats', {})
        team_color = "🔵" if player_stats.get('team', "").lower() == "blue" else "🔴"
        agent = player_stats.get('character', 'Unknown')
        
        # Try to add agent icon
        agent_icon_url = f"https://media.valorant-api.com/agents/{agent.lower()}/displayicon.png"
        embed.set_thumbnail(url=agent_icon_url)
        
        # Your performance with emojis
        embed.add_field(
            name="Your Performance",
            value=f"{team_color} **Agent:** {agent}\n"
                  f"🎯 **K/D/A:** {stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)}\n"
                  f"🎯 **HS%:** {stats.get('headshots', 0)}%\n"
                  f"📊 **Score:** {stats.get('score', 0)}\n"
                  f"**ACS:** {round(stats.get('score', 0) / max(meta.get('rounds_played', 1), 1), 1)}",
            inline=False
        )
        
        # Teams info with K/D/A
        blue_team = []
        red_team = []
        for player in match.get('players', {}).get('all_players', []):
            p_stats = player.get('stats', {})
            kda = f"{p_stats.get('kills', 0)}/{p_stats.get('deaths', 0)}/{p_stats.get('assists', 0)}"
            hs = p_stats.get('headshots', 0)
            player_info = f"• **{player.get('character')}** - {player.get('name')}#{player.get('tag')}\n"
            player_info += f"  └ K/D/A: {kda} | HS: {hs}%"
            
            if player.get('team').lower() == "blue":
                blue_team.append(player_info)
            else:
                red_team.append(player_info)
        
        # Add divider between sections
        embed.add_field(
            name="─────────────",
            value="",
            inline=False
        )
        
        # Add teams with better formatting
        embed.add_field(
            name="🔵 Your Team",
            value="\n".join(blue_team) or "No data",
            inline=False
        )
        
        embed.add_field(
            name="🔴 Enemy Team",
            value="\n".join(red_team) or "No data",
            inline=False
        )
        
        # Match result with emojis
        if teams:
            blue_score = teams.get('blue', {}).get('rounds_won', 0)
            red_score = teams.get('red', {}).get('rounds_won', 0)
            winner = "Blue" if teams.get('blue', {}).get('has_won', False) else "Red"
            winner_emoji = "🏆" if (winner == "Blue" and team_color == "🔵") or (winner == "Red" and team_color == "🔴") else "❌"
            
            embed.add_field(
                name="Match Result",
                value=f"{winner_emoji} **{blue_score}** - **{red_score}**\n"
                      f"{'Victory' if (winner == 'Blue' and team_color == '🔵') or (winner == 'Red' and team_color == '🔴') else 'Defeat'}",
                inline=False
            )
        
        # Add timestamp and match ID
        embed.set_footer(text=f"Played: {meta.get('game_start_patched', 'Unknown')} • Match ID: {meta.get('matchid', 'Unknown')}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["custom_id"] == "prev":
            self.current_index = max(0, self.current_index - 1)
        elif interaction.data["custom_id"] == "next":
            self.current_index = min(len(self.matches) - 1, self.current_index + 1)
        
        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_match_embed(self.matches[self.current_index]), 
            view=self
        )
        return True

class ValorantIDModal(discord.ui.Modal, title="Enter Valorant ID"):
    player_name = discord.ui.TextInput(
        label="Valorant Name",
        placeholder="Enter name (e.g., Shiraboi)",
        required=True
    )
    player_tag = discord.ui.TextInput(
        label="Valorant Tag",
        placeholder="Enter tag without # (e.g., cute)",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # Make it ephemeral
        try:
            # Get account data
            account_response = requests.get(
                f"{HENRIK_API_BASE}/v1/account/{self.player_name.value}/{self.player_tag.value}",
                headers=HEADERS
            )
            account_data = account_response.json()
            
            if account_response.status_code != 200:
                await interaction.followup.send(f"Error: Could not find player {self.player_name.value}#{self.player_tag.value}")
                return
            
            player_region = account_data.get('data', {}).get('region', 'eu').lower()
            
            # Get MMR data
            mmr_response = requests.get(
                f"{HENRIK_API_BASE}/v2/mmr/{player_region}/{self.player_name.value}/{self.player_tag.value}",
                headers=HEADERS
            )
            mmr_data = mmr_response.json()
            
            # Create profile embed
            profile_embed = discord.Embed(
                title=f"Valorant Profile: {self.player_name.value}#{self.player_tag.value}",
                color=int(settings.get("embed_color"), 16)
            )
            
            # Add account info
            account = account_data.get('data', {})
            card_url = account.get('card', {}).get('small')
            if card_url:
                profile_embed.set_thumbnail(url=card_url)
            
            # Get current rank from latest competitive match
            current_rank = "Unknown"
            matches_response = requests.get(
                f"{HENRIK_API_BASE}/v3/matches/{player_region}/{self.player_name.value}/{self.player_tag.value}?size=1&mode=competitive",
                headers=HEADERS
            )
            if matches_response.status_code == 200:
                matches_data = matches_response.json()
                if matches_data.get('data'):
                    match = matches_data['data'][0]
                    for player in match.get('players', {}).get('all_players', []):
                        if player.get('name').lower() == self.player_name.value.lower() and player.get('tag').lower() == self.player_tag.value.lower():
                            current_rank = player.get('currenttier_patched', 'Unknown')
                            break
            
            # Add rank info
            peak_rank = "Unknown"
            if mmr_data.get('data'):
                mmr = mmr_data['data']
                peak_rank = mmr.get('highest_rank', {}).get('patched_tier', 'Unknown')
            
            profile_embed.add_field(
                name="📊 Player Info",
                value=f"👤 **Level:** {account.get('account_level')}\n"
                      f"🌍 **Region:** {account.get('region', 'Unknown').upper()}\n"
                      f"📜 **Title:** {account.get('title', 'No Title')}\n"
                      f"🏆 **Current Rank:** {current_rank}\n"
                      f"⭐ **Peak Rank:** {peak_rank}",
                inline=False
            )
            
            view = MatchDetailsButton(self.player_name.value, self.player_tag.value)
            await interaction.followup.send(embed=profile_embed, view=view, ephemeral=True)  # Make it ephemeral
            
        except Exception as e:
            print(f"Error fetching Valorant info: {str(e)}")
            await interaction.followup.send("An error occurred while fetching Valorant information. Please try again later.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.followup.send('Oops! Something went wrong.', ephemeral=True)

class MatchDetailsButton(discord.ui.View):
    def __init__(self, name: str, tag: str):
        super().__init__(timeout=180)
        self.name = name
        self.tag = tag
        self.matches_shown = False

    @discord.ui.button(label="Show Match Details", style=discord.ButtonStyle.blurple, emoji="🎮")
    async def show_matches(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.matches_shown:
            await interaction.response.send_message("Match details already shown!", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        try:
            await show_match_details(interaction, self.name, self.tag)
            self.matches_shown = True
        except Exception as e:
            print(f"Error showing match details: {str(e)}")
            await interaction.followup.send("Failed to load match details. Please try again.", ephemeral=True)

async def show_match_details(interaction: discord.Interaction, name: str, tag: str):
    try:
        # First get account data to get region
        account_response = requests.get(
            f"{HENRIK_API_BASE}/v1/account/{name}/{tag}",
            headers=HEADERS
        )
        if account_response.status_code != 200:
            await interaction.followup.send("Could not fetch player data.")
            return
            
        account_data = account_response.json()
        player_region = account_data.get('data', {}).get('region', 'eu').lower()
        
        # Get match history
        matches_response = requests.get(
            f"{HENRIK_API_BASE}/v3/matches/{player_region}/{name}/{tag}?size=5",
            headers=HEADERS
        )
        matches_data = matches_response.json()
        
        if not matches_data.get('data'):
            await interaction.followup.send("No recent matches found.", ephemeral=True)
            return
        
        # Process matches
        processed_matches = []
        for match in matches_data['data'][:5]:
            for player in match.get('players', {}).get('all_players', []):
                if player.get('name').lower() == name.lower() and player.get('tag').lower() == tag.lower():
                    match['player_stats'] = player
                    break
            processed_matches.append(match)
        
        # Create match view with first match
        match_view = MatchView(processed_matches)
        first_embed = await match_view.create_match_embed(processed_matches[0])
        await interaction.followup.send(embed=first_embed, view=match_view, ephemeral=True)  # Make it ephemeral
        
    except Exception as e:
        print(f"Error fetching match details: {str(e)}")
        await interaction.followup.send("An error occurred while fetching match details. Please try again later.", ephemeral=True)

async def unauthorized_message(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚠️ Access Denied",
        description="This is a private bot for authorized users only.",
        color=0xFF3333
    )
    
    embed.add_field(
        name="Your Info",
        value=f"User: {interaction.user.mention}\nID: {interaction.user.id}",
        inline=False
    )
    
    embed.set_footer(text="🔒 Private Bot | Made by Shiraken12T")
    
    # Log unauthorized access
    await log_unauthorized_access(
        interaction.user.id,
        f"{interaction.user.name}#{interaction.user.discriminator}",
        interaction.guild.name if interaction.guild else "DM"
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(
    name="valoinfo",
    description="Get Valorant player information"
)
async def valoinfo(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    
    modal = ValorantIDModal()
    await interaction.response.send_modal(modal)

class UnauthorizedUsersView(discord.ui.View):
    def __init__(self, total_pages: int):
        super().__init__(timeout=180)
        self.current_page = 0
        self.total_pages = total_pages
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.current_page > 0:
            self.add_item(discord.ui.Button(label="◀️ Previous", custom_id="prev", style=discord.ButtonStyle.blurple))
        if self.current_page < self.total_pages - 1:
            self.add_item(discord.ui.Button(label="Next ▶️", custom_id="next", style=discord.ButtonStyle.blurple))

    async def create_embed(self, users) -> discord.Embed:
        embed = discord.Embed(
            title="Unauthorized Access Attempts",
            description=f"Page {self.current_page + 1}/{self.total_pages}",
            color=int(settings.get("embed_color"), 16)
        )

        for user in users:
            access_time = datetime.fromisoformat(user['access_time']).strftime("%Y-%m-%d %H:%M:%S")
            embed.add_field(
                name=f"User: {user['username']}",
                value=f"🆔 ID: {user['user_id']}\n"
                      f"🏠 Server: {user['server']}\n"
                      f"⏰ Time: {access_time}",
                inline=False
            )

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["custom_id"] == "prev":
            self.current_page = max(0, self.current_page - 1)
        elif interaction.data["custom_id"] == "next":
            self.current_page = min(self.total_pages - 1, self.current_page + 1)

        users, _ = await get_unauthorized_users(self.current_page)
        self.update_buttons()
        await interaction.response.edit_message(
            embed=await self.create_embed(users),
            view=self
        )
        return True

@bot.tree.command(
    name="unauthusers",
    description="View list of unauthorized users who tried to use the bot"
)
async def unauthusers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await unauthorized_message(interaction)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        users, total = await get_unauthorized_users()
        total_pages = (total + 4) // 5  # Ceiling division by 5
        
        if not users:
            await interaction.followup.send("No unauthorized access attempts recorded.", ephemeral=True)
            return
        
        view = UnauthorizedUsersView(total_pages)
        embed = await view.create_embed(users)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        print(f"Error showing unauthorized users: {e}")
        await interaction.followup.send("An error occurred while fetching the data.", ephemeral=True)

class MinecraftServerModal(discord.ui.Modal, title="Enter Minecraft Server Details"):
    server_ip = discord.ui.TextInput(
        label="Server IP/Address",
        placeholder="e.g., play.example.com or 192.168.1.1",
        required=True
    )
    server_port = discord.ui.TextInput(
        label="Server Port (Optional)",
        placeholder="Leave empty for auto-detection",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            ip = self.server_ip.value.strip()
            port = self.server_port.value.strip() if self.server_port.value else None
            address = f"{ip}:{port}" if port else ip
            
            async with aiohttp.ClientSession() as session:
                java_response = await session.get(f"https://api.mcsrvstat.us/3/{address}")
                java_data = await java_response.json()
                bedrock_response = await session.get(f"https://api.mcsrvstat.us/bedrock/3/{address}")
                bedrock_data = await bedrock_response.json()
            
            # Create main embed
            embed = discord.Embed(
                title="🎮 Minecraft Server Status",
                description=(
                    f"**Server Address**\n"
                    f"```{ip}```\n"
                    f"**Port:** `{port if port else 'Auto-detected'}`\n"
                    f"**SRV Record:** `{'✓' if java_data.get('srv', False) else '✗'}`"
                ),
                color=int(settings.get("embed_color"), 16)
            )

            # Try to add server icon if available and valid
            icon = java_data.get('icon', '')
            if icon and icon.startswith('data:image/png;base64,'):
                # Skip setting thumbnail if it's a base64 image
                pass
            elif icon and (icon.startswith('http://') or icon.startswith('https://')):
                try:
                    embed.set_thumbnail(url=icon)
                except Exception as e:
                    print(f"Error setting server icon: {e}")

            # Java Edition Status
            java_status = "🟢 Online" if java_data.get('online', False) else "🔴 Offline"
            if java_data.get('online', False):
                players = java_data.get('players', {})
                motd = java_data.get('motd', {}).get('clean', ['No MOTD'])[0]
                version = java_data.get('version', 'Unknown')
                
                java_section = [
                    f"**Status:** {java_status}",
                    f"**Version:** `{version}`",
                    "",
                    "**Players**",
                    f"`{players.get('online', 0)}/{players.get('max', 0)}` online",
                ]
                
                if players.get('list'):
                    player_list = players.get('list')[:10]
                    java_section.append("\n**Online Players**")
                    java_section.append(f"```{', '.join(player_list)}```")
                    if len(players.get('list')) > 10:
                        java_section.append(f"*and {len(players.get('list')) - 10} more...*")
                
                java_section.extend([
                    "",
                    "**MOTD**",
                    f"```{motd}```"
                ])
            else:
                java_section = [f"**Status:** {java_status}"]
            
            embed.add_field(
                name="☕ Java Edition",
                value="\n".join(java_section),
                inline=False
            )
            
            # Add separator
            embed.add_field(name="━━━━━━━━━━", value="", inline=False)
            
            # Bedrock Edition Status
            bedrock_status = "🟢 Online" if bedrock_data.get('online', False) else "🔴 Offline"
            if bedrock_data.get('online', False):
                players = bedrock_data.get('players', {})
                motd = bedrock_data.get('motd', {}).get('clean', ['No MOTD'])[0]
                version = bedrock_data.get('version', 'Unknown')
                
                bedrock_section = [
                    f"**Status:** {bedrock_status}",
                    f"**Version:** `{version}`",
                    "",
                    "**Players**",
                    f"`{players.get('online', 0)}/{players.get('max', 0)}` online",
                ]
                
                if players.get('list'):
                    player_list = players.get('list')[:10]
                    bedrock_section.append("\n**Online Players**")
                    bedrock_section.append(f"```{', '.join(player_list)}```")
                    if len(players.get('list')) > 10:
                        bedrock_section.append(f"*and {len(players.get('list')) - 10} more...*")
                
                bedrock_section.extend([
                    "",
                    "**MOTD**",
                    f"```{motd}```"
                ])
            else:
                bedrock_section = [f"**Status:** {bedrock_status}"]
            
            embed.add_field(
                name="📱 Bedrock Edition",
                value="\n".join(bedrock_section),
                inline=False
            )
            
            # Add footer with cache info
            embed.set_footer(
                text=f"Data cached for 1 minute • Last checked: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error checking server status: {e}")
            await interaction.followup.send(
                "Failed to check server status. Please verify the server address is correct.",
                ephemeral=True
            )

@bot.tree.command(
    name="mcserverstatus",
    description="Check Minecraft server status (Java & Bedrock)"
)
async def mcserverstatus(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    
    modal = MinecraftServerModal()
    await interaction.response.send_modal(modal)

class GeminiChatView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for chat session
        self.chat_history = []

@bot.tree.command(
    name="geminichat",
    description="Start a chat session with Gemini AI"
)
async def geminichat(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    
    # Get API key from Supabase
    api_key = await get_gemini_key()
    if not api_key:
        await interaction.response.send_message(
            "Gemini API key not found. Please set it in settings first.", 
            ephemeral=True
        )
        return
        
    # Configure Gemini
    genai.configure(api_key=api_key)
    # Update to use Gemini 1.5
    model = genai.GenerativeModel('gemini-1.5-pro')  # Updated model name
    
    embed = discord.Embed(
        title="💬 Gemini Chat Session",
        description=(
            "Chat session started! You can:\n"
            "- Send messages to chat\n"
            "- Attach images to your messages\n"
            "- Use /geminichatend to end session"
        ),
        color=int(settings.get("embed_color"), 16)
    )
    
    view = GeminiChatView()
    await interaction.response.send_message(embed=embed, view=view)
    
    # Store chat session info in bot's dictionary with start time
    chat = model.start_chat(history=[])
    bot.gemini_sessions[interaction.channel.id] = {
        'chat': chat,
        'history': [],
        'start_time': datetime.now(),
        'start_message_id': interaction.id
    }

@bot.tree.command(
    name="geminichatend",
    description="End current Gemini chat session"
)
async def geminichatend(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
        
    if interaction.channel.id not in bot.gemini_sessions:
        await interaction.response.send_message("No active chat session found!", ephemeral=True)
        return
    
    class EndChatView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            
        @discord.ui.button(label="Download Chat", style=discord.ButtonStyle.green, emoji="📥")
        async def download(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            try:
                session = bot.gemini_sessions[interaction.channel.id]
                
                # Create text file instead of PDF
                chat_content = "\n".join(session['history'])
                buffer = io.BytesIO(chat_content.encode('utf-8'))
                
                # Send file
                await interaction.followup.send(
                    "Here's your chat history:",
                    file=discord.File(buffer, "chat_history.txt"),
                    ephemeral=True
                )
                await self.delete_chat(interaction)
            except Exception as e:
                print(f"Error saving chat history: {e}")
                await interaction.followup.send("Error saving chat history.", ephemeral=True)
            
        @discord.ui.button(label="Delete Chat", style=discord.ButtonStyle.red, emoji="🗑️")
        async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            await self.delete_chat(interaction)
            await interaction.followup.send("Chat deleted!", ephemeral=True)
            
        async def delete_chat(self, interaction: discord.Interaction):
            try:
                session = bot.gemini_sessions[interaction.channel.id]
                start_time = session['start_time']
                
                # Delete messages after the chat started
                async for message in interaction.channel.history(limit=None, after=start_time):
                    if (message.author == bot.user or 
                        message.content.startswith('/geminichat') or
                        (message.author == interaction.user and 
                         interaction.channel.id in bot.gemini_sessions)):
                        try:
                            await message.delete()
                        except discord.NotFound:
                            pass  # Message already deleted
                        except discord.Forbidden:
                            print("Missing permissions to delete message")
                        except Exception as e:
                            print(f"Error deleting message: {e}")
                
                # Clear chat data
                del bot.gemini_sessions[interaction.channel.id]
            except Exception as e:
                print(f"Error deleting chat: {e}")
    
    await interaction.response.send_message(
        "What would you like to do with the chat?",
        view=EndChatView(),
        ephemeral=True
    )

# Update message handler for image support
@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Process commands first
    await bot.process_commands(message)
    
    try:
        # Get server-specific triggers
        triggers = await get_triggers(message.guild.id if message.guild else 0)
        
        # Get the raw message content (shows <@id> instead of resolved mentions)
        raw_message = message.content
        
        # Get the cleaned message content (with resolved mentions)
        cleaned_message = message.clean_content.lower()
        
        # Check each trigger
        for trigger in triggers:
            trigger_name = trigger['name'].lower()
            
            # Handle different types of triggers
            is_triggered = False
            
            if trigger_name.startswith('@'):
                # This is a mention trigger
                mention_part = trigger_name[1:]  # Remove @ symbol
                
                # Check if this is in the raw message (handles actual mentions)
                if any(mention_part.lower() in member.name.lower() 
                      for member in message.mentions):
                    is_triggered = True
                    
                # Also check the cleaned content (handles text that looks like mentions)
                elif mention_part.lower() in cleaned_message:
                    is_triggered = True
                    
            else:
                # Regular trigger matching
                is_triggered = (
                    trigger_name == cleaned_message or  # Exact match
                    trigger_name in cleaned_message.split() or  # Word match
                    trigger_name in cleaned_message  # Substring match
                )
            
            if is_triggered:
                # Add a small delay to seem more natural
                await asyncio.sleep(0.5)
                async with message.channel.typing():
                    await asyncio.sleep(0.5)
                    
                # Format response
                response = trigger['response']
                # Replace {user} with message author's mention
                response = response.replace("{user}", message.author.mention)
                # Replace {channel} with channel mention
                response = response.replace("{channel}", message.channel.mention)
                # Replace {server} with server name
                response = response.replace("{server}", message.guild.name if message.guild else "DM")
                
                await message.channel.send(response)
                break  # Stop after first matching trigger
                
    except Exception as e:
        print(f"Error checking triggers: {e}")

class AddUserModal(discord.ui.Modal, title="Add User"):
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Enter user ID to add",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = int(self.user_id.value)
            if await add_allowed_user(user_id):
                # Update local settings too
                allowed_users = settings.get("allowed_users")
                allowed_users.append(user_id)
                settings.set("allowed_users", allowed_users)
                await interaction.followup.send(f"Added user <@{user_id}> to allowed users.", ephemeral=True)
            else:
                await interaction.followup.send("User already in allowed list.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Invalid user ID.", ephemeral=True)

class RemoveUserModal(discord.ui.Modal, title="Remove User"):
    user_id = discord.ui.TextInput(
        label="User ID",
        placeholder="Enter user ID to remove",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = int(self.user_id.value)
            if await remove_allowed_user(user_id):
                # Update local settings too
                allowed_users = settings.get("allowed_users")
                allowed_users.remove(user_id)
                settings.set("allowed_users", allowed_users)
                await interaction.followup.send(f"Removed user <@{user_id}> from allowed users.", ephemeral=True)
            else:
                await interaction.followup.send("Cannot remove owner or user not in allowed list.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Invalid user ID.", ephemeral=True)

class GeminiKeyModal(discord.ui.Modal, title="Set Gemini API Key"):
    def __init__(self, current_key: str = None):
        super().__init__()
        self.current_key = discord.ui.TextInput(
            label="Current API Key (Read Only)",
            placeholder="No key set" if not current_key else f"Current: {current_key[:30]}...",
            default=current_key if current_key else "",
            required=False
        )
        self.new_key = discord.ui.TextInput(
            label="New API Key",
            placeholder="Enter your new Gemini API key",
            required=True
        )
        self.add_item(self.current_key)
        self.add_item(self.new_key)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # Ignore if they didn't change the key
            if self.new_key.value == self.current_key.value:
                await interaction.followup.send("No changes made to API key.", ephemeral=True)
                return

            # Save to Supabase
            if await save_gemini_key(self.new_key.value):
                # Update local settings
                settings.set("gemini_api_key", self.new_key.value)
                await interaction.followup.send("Gemini API key updated successfully!", ephemeral=True)
            else:
                await interaction.followup.send("Failed to save API key. Please try again.", ephemeral=True)
        except Exception as e:
            print(f"Error saving Gemini key: {e}")
            await interaction.followup.send("An error occurred while saving the API key.", ephemeral=True)

class DeleteNotesModal(discord.ui.Modal, title="Delete Notes"):
    def __init__(self, notes):
        super().__init__()
        self.notes = notes
        self.note_numbers = discord.ui.TextInput(
            label="Note Numbers",
            placeholder="Enter numbers separated by commas (e.g., 1,3,6)",
            required=True
        )
        self.add_item(self.note_numbers)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # Parse the numbers
            numbers = [int(num.strip()) for num in self.note_numbers.value.split(',')]
            deleted_count = 0
            errors = []
            
            for num in numbers:
                idx = num - 1
                if 0 <= idx < len(self.notes):
                    note = self.notes[idx]
                    if await delete_note(note['id']):
                        deleted_count += 1
                    else:
                        errors.append(f"#{num}")
                else:
                    errors.append(f"#{num}")
            
            # Prepare response message
            msg_parts = []
            if deleted_count > 0:
                msg_parts.append(f"Successfully deleted {deleted_count} note{'s' if deleted_count != 1 else ''}.")
            if errors:
                msg_parts.append(f"Failed to delete notes: {', '.join(errors)}")
            
            await interaction.followup.send('\n'.join(msg_parts), ephemeral=True)
            
            # Refresh the notes view if any notes were deleted
            if deleted_count > 0:
                # Create new view and load updated data
                new_view = NotesView()
                await new_view.load_page()
                
                # Update the message with new view
                await interaction.message.edit(
                    embed=new_view.get_embed(),
                    view=new_view
                )
                
        except ValueError:
            await interaction.followup.send(
                "Invalid input. Please enter numbers separated by commas (e.g., 1,3,6).",
                ephemeral=True
            )

# Add this class near your other modals
class UserSearchModal(discord.ui.Modal, title="Search Discord User"):
    user_input = discord.ui.TextInput(
        label="Enter Discord User ID or Username",
        placeholder="Enter a user ID (preferred) or username",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Try to fetch by ID first
            if self.user_input.value.isdigit():
                user = await interaction.client.fetch_user(int(self.user_input.value))
            else:
                # Try to find in client users
                user = discord.utils.get(interaction.client.users, name=self.user_input.value)
                if not user:
                    await interaction.followup.send("User not found. Try using their Discord ID for better results.", ephemeral=True)
                    return

            # Try to get member object from the current server (if available)
            member = None
            if interaction.guild:
                try:
                    member = await interaction.guild.fetch_member(user.id)
                except discord.NotFound:
                    pass  # User is not in this server

            # Create embed with user info
            embed = discord.Embed(
                title=f"User Information: {user}",
                color=int(settings.get("embed_color"), 16)
            )
            
            # Basic user information (always available)
            embed.add_field(name="Username", value=str(user), inline=True)
            embed.add_field(name="User ID", value=user.id, inline=True)
            embed.add_field(name="Bot Account", value="Yes" if user.bot else "No", inline=True)
            embed.add_field(name="Account Created", value=user.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"), inline=True)

            # Fetch additional user info
            try:
                fetched_user = await user.fetch()  # Fetch to get banner and more details
                print(f"Fetched user avatar URL: {fetched_user.avatar.url if fetched_user.avatar else 'No avatar'}")
                
                # Add badges if available
                badges = []
                if hasattr(fetched_user, 'public_flags'):
                    flag_attrs = [
                        'staff', 'partner', 'hypesquad', 'bug_hunter', 
                        'hypesquad_bravery', 'hypesquad_brilliance', 'hypesquad_balance',
                        'early_supporter', 'verified_bot_developer', 'verified_bot',
                        'active_developer'
                    ]
                    for flag in flag_attrs:
                        if hasattr(fetched_user.public_flags, flag) and getattr(fetched_user.public_flags, flag):
                            badges.append(flag.replace('_', ' ').title())
                    
                    if badges:
                        embed.add_field(name="Badges", value=", ".join(badges), inline=False)

                # Avatar handling
                if fetched_user.avatar:
                    avatar_url = fetched_user.avatar.url
                    print(f"Setting avatar URL: {avatar_url}")
                    embed.set_thumbnail(url=avatar_url)
                    embed.add_field(name="Avatar URL", value=f"[Click Here]({avatar_url})", inline=False)
                elif fetched_user.default_avatar:
                    avatar_url = fetched_user.default_avatar.url
                    print(f"Setting default avatar URL: {avatar_url}")
                    embed.set_thumbnail(url=avatar_url)
                    embed.add_field(name="Avatar", value="Default Avatar", inline=False)

                # Banner handling
                if fetched_user.banner:
                    banner_url = fetched_user.banner.url
                    print(f"Setting banner URL: {banner_url}")
                    embed.set_image(url=banner_url)
                    embed.add_field(name="Banner URL", value=f"[Click Here]({banner_url})", inline=False)

                # Accent color
                if fetched_user.accent_color:
                    embed.add_field(name="Accent Color", value=f"#{fetched_user.accent_color.value:06x}", inline=True)

            except Exception as e:
                print(f"Error fetching additional user info: {e}")
                # Try fallback avatar method
                try:
                    avatar_url = user.avatar.url if user.avatar else user.default_avatar.url
                    print(f"Using fallback avatar URL: {avatar_url}")
                    embed.set_thumbnail(url=avatar_url)
                except Exception as e:
                    print(f"Error setting fallback avatar: {e}")

            # Server-specific information (if user is in the server)
            if member:
                embed.add_field(name="Server Member", value="Yes", inline=True)
                
                # Status and Activity
                status_emoji = {
                    discord.Status.online: "🟢",
                    discord.Status.idle: "🟡",
                    discord.Status.dnd: "🔴",
                    discord.Status.offline: "⚫"
                }
                status = f"{status_emoji.get(member.status, '⚪')} {str(member.status).title()}"
                embed.add_field(name="Status", value=status, inline=True)

                # Current activities
                if member.activities:
                    activities = []
                    for activity in member.activities:
                        if isinstance(activity, discord.Spotify):
                            activities.append(f"Listening to {activity.title} by {activity.artist}")
                        elif isinstance(activity, discord.Game):
                            activities.append(f"Playing {activity.name}")
                        elif isinstance(activity, discord.Streaming):
                            activities.append(f"Streaming {activity.name}")
                        elif isinstance(activity, discord.CustomActivity) and activity.name:
                            activities.append(f"Custom Status: {activity.name}")
                        elif not isinstance(activity, discord.CustomActivity):
                            activities.append(str(activity))
                    
                    if activities:
                        embed.add_field(name="Activities", value="\n".join(activities), inline=False)

                # Roles
                if member.roles[1:]:  # Skip @everyone role
                    roles = ", ".join([role.name for role in reversed(member.roles[1:])])
                    embed.add_field(name="Roles", value=roles, inline=False)

                # Server join date
                join_date = member.joined_at.strftime("%Y-%m-%d %H:%M:%S UTC") if member.joined_at else "Unknown"
                embed.add_field(name="Joined Server", value=join_date, inline=True)
            else:
                embed.add_field(name="Server Member", value="No", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.NotFound:
            await interaction.followup.send("User not found. Please check the ID/username and try again.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
        except Exception as e:
            print(f"Error in user search: {e}")
            await interaction.followup.send("An unexpected error occurred while searching for the user.", ephemeral=True)

# Add these classes near your other modals
class TriggerCreateModal(discord.ui.Modal, title="Create Trigger"):
    trigger_name = discord.ui.TextInput(
        label="Trigger Name",
        placeholder="Enter word/phrase or @username for mentions",
        required=True,
        style=discord.TextStyle.short
    )
    trigger_response = discord.ui.TextInput(
        label="Trigger Response",
        placeholder="Enter response (Use {user} for mention, {channel} for channel)",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            if await save_trigger(
                self.trigger_name.value, 
                self.trigger_response.value,
                interaction.guild_id
            ):
                await interaction.followup.send(f"Trigger '{self.trigger_name.value}' created successfully!", ephemeral=True)
            else:
                await interaction.followup.send("Failed to create trigger. Please try again.", ephemeral=True)
        except Exception as e:
            print(f"Error creating trigger: {e}")
            await interaction.followup.send("An error occurred while creating the trigger.", ephemeral=True)

class TriggerEditModal(discord.ui.Modal, title="Edit Trigger"):
    def __init__(self, trigger_id: int, current_name: str, current_response: str):
        super().__init__()
        self.trigger_id = trigger_id
        self.add_item(discord.ui.TextInput(
            label="Trigger Name",
            default=current_name,
            required=True,
            style=discord.TextStyle.short,
            min_length=1
        ))
        self.add_item(discord.ui.TextInput(
            label="Trigger Response",
            default=current_response,
            required=True,
            style=discord.TextStyle.paragraph,
            min_length=1
        ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get values from the inputs
            name = self.children[0].value
            response = self.children[1].value
            
            if await update_trigger(self.trigger_id, name, response):
                await interaction.followup.send(f"Trigger updated successfully!", ephemeral=True)
                # Refresh the trigger list
                view = TriggerListView(guild_id=interaction.guild_id)
                await view.load_page()
                await interaction.message.edit(embed=view.get_embed(), view=view)
            else:
                await interaction.followup.send("Failed to update trigger. Please try again.", ephemeral=True)
        except Exception as e:
            print(f"Error updating trigger: {e}")
            await interaction.followup.send("An error occurred while updating the trigger.", ephemeral=True)

class TriggerDeleteModal(discord.ui.Modal, title="Delete Trigger"):
    def __init__(self, triggers: list):
        super().__init__()
        self.triggers = triggers
        self.add_item(discord.ui.TextInput(
            label="Trigger Number",
            placeholder="Enter the number of the trigger to delete",
            required=True,
            custom_id="trigger_number",
            style=discord.TextStyle.short
        ))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            num = int(self.children[0].value)
            if 1 <= num <= len(self.triggers):
                trigger = self.triggers[num-1]
                if await delete_trigger(trigger['id']):
                    await interaction.followup.send(f"Trigger '{trigger['name']}' deleted successfully!", ephemeral=True)
                    # Refresh the trigger list
                    view = TriggerListView(guild_id=interaction.guild_id)
                    await view.load_page()
                    await interaction.message.edit(embed=view.get_embed(), view=view)
                else:
                    await interaction.followup.send("Failed to delete trigger. Please try again.", ephemeral=True)
            else:
                await interaction.followup.send("Invalid trigger number. Please try again.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error deleting trigger: {e}")
            await interaction.followup.send("An error occurred while deleting the trigger.", ephemeral=True)

class TriggerListView(discord.ui.View):
    def __init__(self, guild_id: int):
        # Remove timeout to make the view persistent
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.page = 0
        self.triggers = []
        self.per_page = 5

    async def load_page(self):
        self.triggers = await get_triggers(self.guild_id)

    def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Trigger List",
            description="Current auto-responder triggers:",  # Add description
            color=int(settings.get("embed_color"), 16)
        )

        start = self.page * self.per_page
        end = start + self.per_page
        page_triggers = self.triggers[start:end]

        if not page_triggers:
            embed.description = "No triggers found."
            return embed

        for i, trigger in enumerate(page_triggers, start=start+1):
            embed.add_field(
                name=f"{i}. {trigger['name']}", 
                value=trigger['response'], 
                inline=False
            )

        embed.set_footer(text=f"Page {self.page + 1}/{max(1, (len(self.triggers) + self.per_page - 1) // self.per_page)}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            # Keep the edited message ephemeral
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.page + 1) * self.per_page < len(self.triggers):
            self.page += 1
            # Keep the edited message ephemeral
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Delete Trigger", style=discord.ButtonStyle.red)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.triggers:
            await interaction.response.send_message("No triggers to delete.", ephemeral=True)
            return
        
        modal = TriggerDeleteModal(self.triggers)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Trigger", style=discord.ButtonStyle.green)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.triggers:
            await interaction.response.send_message("No triggers to edit.", ephemeral=True)
            return

        modal = SelectTriggerModal(self.triggers)
        await interaction.response.send_modal(modal)

# Add this class with your other modal classes (near TriggerCreateModal, TriggerEditModal, etc.)
class SelectTriggerModal(discord.ui.Modal, title="Select Trigger to Edit"):
    def __init__(self, triggers):
        super().__init__()
        self.triggers = triggers
        self.number = discord.ui.TextInput(  # Changed name to avoid conflicts
            label="Trigger Number",
            placeholder="Enter the number of the trigger to edit",
            required=True,
            min_length=1,
            max_length=2,
            style=discord.TextStyle.short
        )
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            num = int(self.number.value)
            if 1 <= num <= len(self.triggers):
                trigger = self.triggers[num-1]
                # Create edit modal
                edit_modal = TriggerEditModal(
                    trigger_id=trigger['id'],
                    current_name=trigger['name'],
                    current_response=trigger['response']
                )
                # Send a temporary message
                await interaction.followup.send(
                    f"Editing trigger: {trigger['name']}", 
                    ephemeral=True,
                    view=EditModalView(edit_modal)
                )
            else:
                await interaction.followup.send("Invalid trigger number. Please try again.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error selecting trigger: {e}")
            await interaction.followup.send("An error occurred while selecting the trigger.", ephemeral=True)

# Add this helper class
class EditModalView(discord.ui.View):
    def __init__(self, modal):
        super().__init__(timeout=60)
        self.modal = modal

    @discord.ui.button(label="Edit Trigger", style=discord.ButtonStyle.green)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.modal)

# Add these commands back
@bot.tree.command(
    name="triggercreate",
    description="Create a new auto-responder trigger"
)
async def triggercreate(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    
    modal = TriggerCreateModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(
    name="triggerlist",
    description="Show list of auto-responder triggers"
)
async def triggerlist(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
    
    view = TriggerListView(guild_id=interaction.guild_id)
    await view.load_page()
    await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

# Add these classes near your other modal/view classes (before the sync command)
class ImageUploadView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Select Format", style=discord.ButtonStyle.primary, emoji="🔄")
    async def format_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageFormatModal())

class ImageFormatModal(discord.ui.Modal, title="Select Format"):
    def __init__(self):
        super().__init__()
        self.format = discord.ui.TextInput(
            label="Target Format",
            placeholder="Enter format: png, jpg, webp, gif, etc.",
            required=True,
            max_length=10,
            style=discord.TextStyle.short
        )
        self.add_item(self.format)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate format first
        target_format = self.format.value.lower()
        supported_formats = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'ico']
        
        if target_format not in supported_formats:
            await interaction.response.send_message(
                f"❌ Unsupported format! Supported formats: {', '.join(supported_formats)}", 
                ephemeral=True
            )
            return

        # If format is valid, show upload options
        await interaction.response.send_message(
            "Choose how to upload your image:",
            view=ImageUploadMethodView(target_format),
            ephemeral=True
        )

class ImageUploadMethodView(discord.ui.View):
    def __init__(self, target_format):
        super().__init__(timeout=300)
        self.target_format = target_format

    @discord.ui.button(label="Upload File", style=discord.ButtonStyle.primary, emoji="📁")
    async def file_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Please upload your image file now. I'll wait for your upload...",
            ephemeral=True
        )
        
        def check(m):
            return (m.author.id == interaction.user.id and 
                   m.attachments and 
                   m.channel.id == interaction.channel.id)
        
        try:
            message = await interaction.client.wait_for('message', timeout=60.0, check=check)
            await self.process_image(interaction, message.attachments[0])
        except asyncio.TimeoutError:
            await interaction.followup.send("Upload timed out. Please try again.", ephemeral=True)

    @discord.ui.button(label="Upload by URL", style=discord.ButtonStyle.secondary, emoji="🔗")
    async def url_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageURLModal(self.target_format))

    async def process_image(self, interaction, attachment):
        try:
            await interaction.followup.send("⏳ Processing your image...", ephemeral=True)
            
            # Download image
            image_data = await attachment.read()
            
            # Process and convert
            image = Image.open(io.BytesIO(image_data))
            output = io.BytesIO()
            
            if self.target_format == 'jpg':
                if image.mode in ('RGBA', 'P'):
                    image = image.convert('RGB')
            
            image.save(output, format=self.target_format.upper())
            output.seek(0)

            # Send converted image
            await interaction.followup.send(
                f"✅ Here's your converted image in {self.target_format.upper()} format:",
                file=discord.File(output, f"converted.{self.target_format}"),
                ephemeral=True
            )

        except Exception as e:
            print(f"Error processing image: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing the image. Please try again.",
                ephemeral=True
            )

    async def process_url(self, interaction, url):
        try:
            await interaction.followup.send("⏳ Processing your image...", ephemeral=True)
            
            # Download from URL
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        await interaction.followup.send("❌ Failed to download image from URL.", ephemeral=True)
                        return
                    image_data = await response.read()

            # Process and convert
            image = Image.open(io.BytesIO(image_data))
            output = io.BytesIO()
            
            if self.target_format == 'jpg':
                if image.mode in ('RGBA', 'P'):
                    image = image.convert('RGB')
            
            image.save(output, format=self.target_format.upper())
            output.seek(0)

            # Send converted image
            await interaction.followup.send(
                f"✅ Here's your converted image in {self.target_format.upper()} format:",
                file=discord.File(output, f"converted.{self.target_format}"),
                ephemeral=True
            )

        except Exception as e:
            print(f"Error processing URL: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing the image. Please try again.",
                ephemeral=True
            )

class ImageURLModal(discord.ui.Modal, title="Image URL"):
    def __init__(self, target_format):
        super().__init__()
        self.target_format = target_format
        self.url = discord.ui.TextInput(
            label="Image URL",
            placeholder="Enter the direct URL to your image",
            required=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.url)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = ImageUploadMethodView(self.target_format)
        await view.process_url(interaction, self.url.value)

@bot.tree.command(
    name="imageconvert",
    description="Convert images between different formats (PNG, JPG, WEBP, GIF, etc.)"
)
async def imageconvert(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    embed = discord.Embed(
        title="🖼️ Image Converter",
        description=(
            "Convert your images between different formats!\n\n"
            "**Supported formats:**\n"
            "• PNG - Best for graphics with transparency\n"
            "• JPG - Good for photos, smaller file size\n"
            "• WEBP - Modern format, good compression\n"
            "• GIF - For animated images\n"
            "• BMP - Uncompressed format\n"
            "• ICO - For icons\n\n"
            "**How to use:**\n"
            "1. Upload your image\n"
            "2. Click the button below\n"
            "3. Enter desired format\n"
            "4. Get your converted image!"
        ),
        color=int(settings.get("embed_color"), 16)
    )
    embed.set_footer(text="Note: All conversions are private and ephemeral")

    await interaction.response.send_message(
        embed=embed,
        view=ImageUploadView(),
        ephemeral=True
    )

# Then your sync command follows...
@bot.tree.command(
    name="sync",
    description="Sync all commands (Owner Only)"
)
async def sync(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await unauthorized_message(interaction)
        return
        
    try:
        print("Syncing commands...")
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
        await interaction.response.send_message(
            f"✅ Successfully synced {len(synced)} commands!", 
            ephemeral=True
        )
    except Exception as e:
        print(f"Error syncing commands: {e}")
        await interaction.response.send_message(
            "❌ Error syncing commands", 
            ephemeral=True
        )

# Replace the dummy server code with this simpler version
def run_dummy_server():
    """Run a simple TCP server to satisfy Render's port requirement"""
    port = int(os.environ.get("PORT", 10000))
    
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', port))
        server.listen(1)
        print(f"TCP Server listening on port {port}")
        
        while True:
            try:
                client, addr = server.accept()
                client.send(b"Bot is running\n")
                client.close()
            except:
                pass
                
    except Exception as e:
        print(f"Server error: {e}")
        # Don't raise - let the bot continue

# Start the server before running the bot
if os.environ.get("IS_RENDER"):
    print("Starting TCP server for Render...")
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()
    
    # Wait a moment to ensure the server starts
    time.sleep(2)
    
    # Test the connection
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.connect(('localhost', int(os.environ.get("PORT", 10000))))
        test_socket.close()
        print("TCP Server is running!")
    except Exception as e:
        print(f"Warning: Could not verify server: {e}")

class ImagesToPDFView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)  # 10 minute timeout
        self.images = []
        self.waiting_for_images = False

    @discord.ui.button(label="Upload Images", style=discord.ButtonStyle.primary, emoji="📸")
    async def upload_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.waiting_for_images = True
        await interaction.response.send_message(
            "Please upload your images now. You can upload multiple images.\n"
            "Type `done` when you've finished uploading, or `cancel` to abort.",
            ephemeral=True
        )
        
        while self.waiting_for_images:
            def check(m):
                return (m.author.id == interaction.user.id and 
                       m.channel.id == interaction.channel.id and
                       (m.attachments or m.content.lower() in ['done', 'cancel']))
            
            try:
                message = await interaction.client.wait_for('message', timeout=300.0, check=check)
                
                if message.content.lower() == 'done':
                    if not self.images:
                        await interaction.followup.send("No images were uploaded. Please try again.", ephemeral=True)
                        self.waiting_for_images = False
                        return
                    await self.create_pdf(interaction)
                    self.waiting_for_images = False
                    return
                
                elif message.content.lower() == 'cancel':
                    await interaction.followup.send("Operation cancelled.", ephemeral=True)
                    self.waiting_for_images = False
                    return
                
                elif message.attachments:
                    for attachment in message.attachments:
                        if attachment.content_type.startswith('image/'):
                            self.images.append(attachment)
                            await interaction.followup.send(
                                f"✅ Added image: {attachment.filename}\n"
                                f"Total images: {len(self.images)}\n"
                                "Keep uploading or type `done` when finished.",
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                f"❌ Skipped {attachment.filename}: Not an image file.",
                                ephemeral=True
                            )
                
            except asyncio.TimeoutError:
                await interaction.followup.send("Timed out. Please try again.", ephemeral=True)
                self.waiting_for_images = False
                return

    async def create_pdf(self, interaction):
        try:
            await interaction.followup.send("⏳ Creating PDF...", ephemeral=True)
            
            # Create a PDF
            pdf = FPDF()
            temp_files = []  # Keep track of temp files
            
            for attachment in self.images:
                try:
                    # Download image
                    image_data = await attachment.read()
                    image = Image.open(io.BytesIO(image_data))
                    
                    # Convert to RGB if necessary
                    if image.mode in ('RGBA', 'P'):
                        image = image.convert('RGB')
                    
                    # Save as temporary JPG with unique name
                    temp_jpg = f'temp_{len(temp_files)}_{attachment.filename}.jpg'
                    temp_files.append(temp_jpg)
                    image.save(temp_jpg, 'JPEG')
                    
                    # Add to PDF
                    pdf.add_page()
                    
                    # Get image dimensions
                    img_width, img_height = image.size
                    aspect = img_height / img_width
                    
                    # Calculate dimensions to fit page
                    pdf_width = pdf.w - 20  # margins
                    pdf_height = pdf_width * aspect
                    
                    # Add image to page
                    pdf.image(temp_jpg, x=10, y=10, w=pdf_width)
                    
                except Exception as e:
                    print(f"Error processing image {attachment.filename}: {e}")
                    continue
            
            # Save PDF to temporary file
            temp_pdf = 'temp_output.pdf'
            pdf.output(temp_pdf)
            
            # Read the PDF and send it
            with open(temp_pdf, 'rb') as f:
                pdf_data = f.read()
                await interaction.followup.send(
                    f"✅ Created PDF with {len(self.images)} images!",
                    file=discord.File(io.BytesIO(pdf_data), "combined_images.pdf"),
                    ephemeral=True
                )
            
            # Clean up all temporary files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)
            
        except Exception as e:
            print(f"Error creating PDF: {e}")
            # Clean up any remaining temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)
            await interaction.followup.send(
                "❌ An error occurred while creating the PDF. Please try again.",
                ephemeral=True
            )

@bot.tree.command(
    name="imagestopdf",
    description="Combine multiple images into a single PDF file"
)
async def imagestopdf(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    embed = discord.Embed(
        title="📸 Images to PDF Converter",
        description=(
            "Combine multiple images into a single PDF file!\n\n"
            "**Features:**\n"
            "• Upload multiple images\n"
            "• Maintains image quality\n"
            "• Automatic page sizing\n"
            "• Supports most image formats\n\n"
            "**How to use:**\n"
            "1. Click the Upload button\n"
            "2. Upload your images\n"
            "3. Type `done` when finished\n"
            "4. Get your PDF file!\n\n"
            "**Note:**\n"
            "• Type `cancel` to abort\n"
            "• Maximum time: 5 minutes\n"
            "• Images are added in upload order"
        ),
        color=int(settings.get("embed_color"), 16)
    )
    embed.set_footer(text="All conversions are private and ephemeral")

    await interaction.response.send_message(
        embed=embed,
        view=ImagesToPDFView(),
        ephemeral=True
    )

# Add after ImagesToPDFView class
class DocConvertView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Upload Document", style=discord.ButtonStyle.primary, emoji="📄")
    async def upload_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Please upload your DOCX file. I'll convert it to PDF.",
            ephemeral=True
        )
        
        def check(m):
            return (m.author.id == interaction.user.id and 
                   m.attachments and 
                   m.channel.id == interaction.channel.id)
        
        try:
            message = await interaction.client.wait_for('message', timeout=60.0, check=check)
            attachment = message.attachments[0]
            
            # Verify file type
            if not attachment.filename.lower().endswith('.docx'):
                await interaction.followup.send(
                    "❌ Please upload a DOCX file.",
                    ephemeral=True
                )
                return
                
            await self.convert_to_pdf(interaction, attachment)
            
        except asyncio.TimeoutError:
            await interaction.followup.send("Upload timed out. Please try again.", ephemeral=True)

    async def convert_to_pdf(self, interaction, attachment):
        try:
            await interaction.followup.send("⏳ Converting document to PDF...", ephemeral=True)
            
            # Download the DOCX file
            docx_data = await attachment.read()
            temp_docx = 'temp_document.docx'
            temp_pdf = 'temp_document.pdf'
            
            # Save DOCX temporarily
            with open(temp_docx, 'wb') as f:
                f.write(docx_data)
            
            try:
                # Open the Word document
                doc = docx.Document(temp_docx)
                
                # Create PDF
                c = canvas.Canvas(temp_pdf, pagesize=letter)
                width, height = letter
                
                # Convert each paragraph
                y = height - 40  # Start from top with margin
                for para in doc.paragraphs:
                    if y < 40:  # Bottom margin
                        c.showPage()
                        y = height - 40
                    
                    # Add text
                    text = para.text
                    if text.strip():  # Only process non-empty paragraphs
                        # Handle different paragraph styles
                        if para.style.name.startswith('Heading'):
                            c.setFont("Helvetica-Bold", 14)
                        else:
                            c.setFont("Helvetica", 12)
                        
                        # Word wrap and write text
                        words = text.split()
                        line = []
                        for word in words:
                            line.append(word)
                            line_text = ' '.join(line)
                            if c.stringWidth(line_text, "Helvetica", 12) > width - 80:
                                # Write line and move down
                                c.drawString(40, y, ' '.join(line[:-1]))
                                y -= 20
                                line = [word]
                        
                        if line:  # Write remaining text
                            c.drawString(40, y, ' '.join(line))
                            y -= 20
                    
                    # Add extra space between paragraphs
                    y -= 10
                
                c.save()
                
                # Read the PDF
                with open(temp_pdf, 'rb') as f:
                    pdf_data = f.read()
                
                # Send the converted PDF
                await interaction.followup.send(
                    "✅ Here's your converted PDF file:",
                    file=discord.File(io.BytesIO(pdf_data), "converted.pdf"),
                    ephemeral=True
                )
                
            finally:
                # Clean up temp files
                if os.path.exists(temp_docx):
                    os.remove(temp_docx)
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
            
        except Exception as e:
            print(f"Error converting document: {e}")
            await interaction.followup.send(
                "❌ An error occurred while converting the document. Please try again.",
                ephemeral=True
            )

@bot.tree.command(
    name="docconvert",
    description="Convert DOCX documents to PDF"
)
async def docconvert(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    embed = discord.Embed(
        title="📄 Document Converter",
        description=(
            "Convert your DOCX documents to PDF!\n\n"
            "**Features:**\n"
            "• Maintains formatting\n"
            "• Preserves images\n"
            "• Keeps tables and styles\n"
            "• Fast conversion\n\n"
            "**How to use:**\n"
            "1. Click the Upload button\n"
            "2. Upload your DOCX file\n"
            "3. Get your PDF file!\n\n"
            "**Note:**\n"
            "• Only DOCX files are supported\n"
            "• Maximum file size: 8MB\n"
            "• All conversions are private"
        ),
        color=int(settings.get("embed_color"), 16)
    )
    embed.set_footer(text="All conversions are private and ephemeral")

    await interaction.response.send_message(
        embed=embed,
        view=DocConvertView(),
        ephemeral=True
    )

class BlacklistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.danger, emoji="🚫")
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ Only the owner can add users to blacklist.", ephemeral=True)
            return
        await interaction.response.send_modal(BlacklistAddModal())

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.success, emoji="✅")
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("❌ Only the owner can remove users from blacklist.", ephemeral=True)
            return
        await interaction.response.send_modal(BlacklistRemoveModal())

    @discord.ui.button(label="Refresh List", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.refresh_blacklist(interaction)

    async def refresh_blacklist(self, interaction: discord.Interaction):
        blacklisted_users = await get_blacklist()
        
        if not blacklisted_users:
            embed = discord.Embed(
                title="📋 Blacklisted Users",
                description="No users are currently blacklisted.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="📋 Blacklisted Users",
                color=discord.Color.red()
            )
            
            for user in blacklisted_users:
                try:
                    user_obj = await bot.fetch_user(user['user_id'])
                    username = f"{user_obj.name} ({user_obj.id})"
                except:
                    username = f"Unknown User ({user['user_id']})"
                
                embed.add_field(
                    name=username,
                    value=f"**Reason:** {user['reason']}\n**Date:** {user['timestamp'][:10]}",
                    inline=False
                )

        embed.set_footer(text="Use the buttons below to manage the blacklist")
        await interaction.response.edit_message(embed=embed, view=self)

class BlacklistAddModal(discord.ui.Modal, title="Add User to Blacklist"):
    def __init__(self):
        super().__init__()
        self.user_id = discord.ui.TextInput(
            label="User ID",
            placeholder="Enter the user ID to blacklist",
            required=True,
            min_length=17,
            max_length=20
        )
        self.reason = discord.ui.TextInput(
            label="Reason",
            placeholder="Enter the reason for blacklisting",
            required=True,
            max_length=100,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.user_id)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            
            # Check if user is already blacklisted
            if await is_blacklisted(user_id):
                await interaction.response.send_message(
                    "❌ This user is already blacklisted.",
                    ephemeral=True
                )
                return

            # Don't allow blacklisting the owner
            if user_id == OWNER_ID:
                await interaction.response.send_message(
                    "❌ You cannot blacklist the bot owner.",
                    ephemeral=True
                )
                return

            if await add_to_blacklist(user_id, self.reason.value):
                # Remove from allowed users if present
                allowed_users = settings.get("allowed_users")
                if user_id in allowed_users:
                    allowed_users.remove(user_id)
                    await save_allowed_users(allowed_users)
                
                user_obj = await bot.fetch_user(user_id)
                embed = discord.Embed(
                    title="✅ User Blacklisted",
                    description=f"Successfully blacklisted {user_obj.name} ({user_id})",
                    color=discord.Color.green()
                )
                embed.add_field(name="Reason", value=self.reason.value)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "❌ Failed to add user to blacklist.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid user ID format.",
                ephemeral=True
            )

class BlacklistRemoveModal(discord.ui.Modal, title="Remove User from Blacklist"):
    def __init__(self):
        super().__init__()
        self.user_id = discord.ui.TextInput(
            label="User ID",
            placeholder="Enter the user ID to remove from blacklist",
            required=True,
            min_length=17,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id.value)
            if await is_blacklisted(user_id):
                if await remove_from_blacklist(user_id):
                    user_obj = await bot.fetch_user(user_id)
                    embed = discord.Embed(
                        title="✅ User Removed from Blacklist",
                        description=f"Successfully removed {user_obj.name} ({user_id}) from blacklist",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        "❌ Failed to remove user from blacklist.",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    "❌ This user is not blacklisted.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid user ID format.",
                ephemeral=True
            )

@bot.tree.command(
    name="blacklist",
    description="View and manage blacklisted users (Owner Only)"
)
async def blacklist(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await unauthorized_message(interaction)
        return

    blacklisted_users = await get_blacklist()
    
    if not blacklisted_users:
        embed = discord.Embed(
            title="📋 Blacklisted Users",
            description="No users are currently blacklisted.",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="📋 Blacklisted Users",
            color=discord.Color.red()
        )
        
        for user in blacklisted_users:
            try:
                user_obj = await bot.fetch_user(user['user_id'])
                username = f"{user_obj.name} ({user_obj.id})"
            except:
                username = f"Unknown User ({user['user_id']})"
            
            embed.add_field(
                name=username,
                value=f"**Reason:** {user['reason']}\n**Date:** {user['timestamp'][:10]}",
                inline=False
            )

    embed.set_footer(text="Use the buttons below to manage the blacklist")
    
    await interaction.response.send_message(
        embed=embed,
        view=BlacklistView(),
        ephemeral=True
    )

class ImagineModal(discord.ui.Modal, title="Generate Image"):
    def __init__(self):
        super().__init__()
        self.prompt = discord.ui.TextInput(
            label="Prompt",
            placeholder="Describe the image you want to generate...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.prompt)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Generate image using Stable Diffusion API
            url = "https://api.stability.ai/v1/generation/stable-diffusion-v1-6/text-to-image"
            
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {STABILITY_API_KEY}",
            }

            body = {
                "steps": 30,
                "width": 512,
                "height": 512,
                "seed": 0,
                "cfg_scale": 7,
                "samples": 4,
                "text_prompts": [
                    {
                        "text": self.prompt.value,
                        "weight": 1
                    }
                ],
            }
            
            async with aiohttp.ClientSession() as session:
                await interaction.followup.send("🎨 Generating your images... Please wait!", ephemeral=True)
                
                async with session.post(url, headers=headers, json=body) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        print(f"API Error: {error_data}")
                        await interaction.followup.send(
                            "❌ Failed to generate images. Please try again.",
                            ephemeral=True
                        )
                        return
                    
                    data = await response.json()
                    
                    # Create a temporary message to store images
                    temp_message = await interaction.channel.send("🎨 Processing images...")
                    
                    # Process and upload images
                    images = []
                    files = []
                    for i, image in enumerate(data["artifacts"]):
                        try:
                            # Convert base64 to file
                            image_data = base64.b64decode(image["base64"])
                            file = discord.File(
                                io.BytesIO(image_data), 
                                f"image_{i}.png",
                                description=self.prompt.value
                            )
                            files.append(file)
                        except Exception as e:
                            print(f"Error processing image {i}: {e}")
                            continue
                    
                    # Upload all images in one message
                    if files:
                        msg = await temp_message.edit(content="", attachments=files)
                        images = [{
                            'src': attachment.url,
                            'prompt': self.prompt.value
                        } for attachment in msg.attachments]
                    
                    # Clean up temp message if no images
                    if not images:
                        await temp_message.delete()
                        await interaction.followup.send(
                            "❌ Failed to process images. Please try again.",
                            ephemeral=True
                        )
                        return
                    
                    # Create embed with results
                    embed = discord.Embed(
                        title="🎨 Generated Images",
                        description=f"**Your Prompt:** {self.prompt.value}",
                        color=discord.Color.blue()
                    )
                    
                    # Set first image and create view
                    embed.set_image(url=images[0]['src'])
                    embed.set_footer(text=f"Image 1/{len(images)} • Use buttons to navigate")
                    
                    # Send result and delete temp message
                    await interaction.followup.send(
                        embed=embed,
                        view=ImageResultView(images),
                        ephemeral=True
                    )
                    await temp_message.delete()
                    
        except Exception as e:
            print(f"Error generating images: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating images. Please try again.",
                ephemeral=True
            )

class ImageResultView(discord.ui.View):
    def __init__(self, images):
        super().__init__(timeout=300)
        self.images = images
        self.current = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current - 1) % len(self.images)
        await self.update_image(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.images)
        await self.update_image(interaction)

    @discord.ui.button(label="Save", style=discord.ButtonStyle.primary, emoji="💾")
    async def save_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_image = self.images[self.current]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(current_image['src']) as response:
                    if response.status != 200:
                        await interaction.response.send_message(
                            "❌ Failed to download image.",
                            ephemeral=True
                        )
                        return
                    
                    image_data = await response.read()
                    await interaction.response.send_message(
                        "✅ Here's your image:",
                        file=discord.File(io.BytesIO(image_data), "generated_image.png"),
                        ephemeral=True
                    )
        except Exception as e:
            print(f"Error saving image: {e}")
            await interaction.response.send_message(
                "❌ Failed to save image.",
                ephemeral=True
            )

    async def update_image(self, interaction: discord.Interaction):
        """Update the embed with the current image"""
        try:
            current_image = self.images[self.current]
            embed = interaction.message.embeds[0]
            embed.set_image(url=current_image['src'])
            embed.set_footer(text=f"Image {self.current + 1}/{len(self.images)} • Use buttons to navigate")
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"Error updating image: {e}")
            await interaction.response.send_message(
                "❌ Failed to update image. Please try again.",
                ephemeral=True
            )

@bot.tree.command(
    name="imagine",
    description="Generate images from text descriptions"
)
async def imagine(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    modal = ImagineModal()
    await interaction.response.send_modal(modal)

class MemeTemplateView(discord.ui.View):
    def __init__(self, text: str):
        super().__init__(timeout=300)
        self.text = text
        self.current = 0
        # Remove the hardcoded templates since we're using memes.py
        self.templates = {}
        self.template_list = []

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current - 1) % len(self.templates)
        await self.update_preview(interaction)

    @discord.ui.button(label="Use Template", style=discord.ButtonStyle.primary, emoji="✨")
    async def use_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        template_name, template = self.template_list[self.current]
        await interaction.response.send_modal(
            MemeTextModal(
                template["id"],
                template_name,
                template["parts"],
                template["labels"]
            )
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.templates)
        await self.update_preview(interaction)

    async def update_preview(self, interaction: discord.Interaction):
        template_name, template = self.template_list[self.current]
        
        embed = discord.Embed(
            title="🎭 Meme Generator",
            description=f"**Current Template:** {template_name}\n{template['description']}",
            color=discord.Color.blue()
        )
        
        # Add template info
        embed.add_field(
            name="Number of Text Parts",
            value=str(template["parts"]),
            inline=True
        )
        embed.add_field(
            name="Text Fields",
            value="\n".join(template["labels"]),
            inline=True
        )
        
        # Set preview image using the URL from our templates
        embed.set_image(url=template["preview"])
        embed.set_footer(text=f"Template {self.current + 1}/4 • Click 'Use Template' to create meme")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.InteractionResponded:
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)

class MemeTextModal(discord.ui.Modal):
    def __init__(self, template_id: str, template_name: str, num_parts: int, labels: list):
        super().__init__(title=f"Create {template_name} Meme")
        self.template_id = template_id
        self.template_name = template_name
        
        # Dynamically add text inputs based on number of parts
        for i in range(num_parts):
            setattr(self, f"text{i}", discord.ui.TextInput(
                label=labels[i],
                placeholder=f"Enter text for {labels[i]}...",
                required=True,
                max_length=50
            ))
            self.add_item(getattr(self, f"text{i}"))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            # Create meme using imgflip API
            url = "https://api.imgflip.com/caption_image"
            
            # Collect all text inputs
            texts = {}
            for i in range(len(self.children)):
                texts[f"text{i}"] = getattr(self, f"text{i}").value
            
            # Create params
            params = {
                "template_id": self.template_id,
                "username": os.getenv("IMGFLIP_USERNAME"),
                "password": os.getenv("IMGFLIP_PASSWORD")
            }
            # Add text fields
            for key, value in texts.items():
                params[key] = value
            
            print(f"Sending request with params: {params}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=params) as response:
                    data = await response.json()
                    print(f"API Response: {data}")
                    
                    if not data['success']:
                        error_msg = data.get('error_message', 'Unknown error')
                        print(f"API Error: {error_msg}")
                        await interaction.followup.send(
                            f"❌ Failed to generate meme: {error_msg}",
                            ephemeral=True
                        )
                        return
                    
                    # Create embed with meme
                    embed = discord.Embed(
                        title=f"🎭 {self.template_name} Meme",
                        description=f"Created by {interaction.user.name}",
                        color=discord.Color.random()
                    )
                    embed.set_image(url=data['data']['url'])
                    
                    # Send as public message
                    await interaction.channel.send(embed=embed)
                    
        except Exception as e:
            print(f"Error generating meme: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the meme. Please try again.",
                ephemeral=True
            )

@bot.tree.command(
    name="meme",
    description="Generate a meme with your text"
)
async def meme(interaction: discord.Interaction):
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    # Get random templates from memes.py
    selected_templates = get_random_templates(4)
    
    view = MemeTemplateView(interaction.user.id)
    view.templates = selected_templates
    view.template_list = list(selected_templates.items())
    template_name, template = view.template_list[0]
    
    embed = discord.Embed(
        title="🎭 Meme Generator",
        description=f"**Current Template:** {template_name}\n{template['description']}",
        color=discord.Color.blue()
    )
    
    # Add template info
    embed.add_field(
        name="Number of Text Parts",
        value=str(template["parts"]),
        inline=True
    )
    embed.add_field(
        name="Text Fields",
        value="\n".join(template["labels"]),
        inline=True
    )
    
    # Set preview image
    embed.set_image(url=template["preview"])
    embed.set_footer(text=f"Template 1/4 • Click 'Use Template' to create meme")
    
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )

class MovieView(discord.ui.View):
    def __init__(self, movie_data: list):
        super().__init__(timeout=300)
        self.current = 0
        self.movies = movie_data

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current - 1) % len(self.movies)
        await self.update_movie(interaction)

    @discord.ui.button(label="More Info", style=discord.ButtonStyle.primary, emoji="🎬")
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        movie = self.movies[self.current]
        tmdb_url = f"https://www.themoviedb.org/movie/{movie['id']}"
        await interaction.response.send_message(f"View more details at: {tmdb_url}", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = (self.current + 1) % len(self.movies)
        await self.update_movie(interaction)

    async def update_movie(self, interaction: discord.Interaction):
        movie = self.movies[self.current]
        
        embed = discord.Embed(
            title=f"🎬 {movie['title']} ({movie['release_date'][:4]})",
            description=movie['overview'],
            color=discord.Color.blue()
        )
        
        if movie['poster_path']:
            embed.set_image(url=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}")
        
        embed.add_field(
            name="Rating",
            value=f"⭐ {movie['vote_average']}/10",
            inline=True
        )
        embed.add_field(
            name="Votes",
            value=f"👥 {movie['vote_count']}",
            inline=True
        )
        
        embed.set_footer(text=f"Movie {self.current + 1}/{len(self.movies)} • Click 'More Info' for details")
        
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(
    name="searchmovie",
    description="Search for a movie across streaming sites"
)
async def searchmovie(interaction: discord.Interaction, movie: str):
    """Search for movie streaming links"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    await interaction.response.defer()

    try:
        embed = discord.Embed(
            title=f"🎬 Search results for: {movie}",
            description="Searching for streaming links...",
            color=discord.Color.blue()
        )

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            for site_name, site_info in MOVIE_SITES.items():
                try:
                    search_url = site_info["url"].format(quote(movie))
                    async with session.get(search_url) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # Find movie items using the site's selectors
                            movies = soup.select(site_info["movie_selector"])
                            if movies:
                                movie_item = movies[0]  # Get first result
                                title = movie_item.select_one(site_info["title_selector"]).text.strip()
                                link = movie_item.select_one(site_info["link_selector"])["href"]
                                if not link.startswith("http"):
                                    link = urljoin(search_url, link)
                                
                                embed.add_field(
                                    name=f"{site_name}",
                                    value=f"[{title}]({link})",
                                    inline=False
                                )
                except Exception as e:
                    print(f"Error searching {site_name}: {e}")
                    continue

        if len(embed.fields) > 0:
            embed.set_footer(text="⚠️ Please verify links before using them")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ No streaming links found. Try another movie title.",
                ephemeral=True
            )

    except Exception as e:
        print(f"Error searching movie: {e}")
        await interaction.followup.send(
            "❌ An error occurred while searching. Please try again.",
            ephemeral=True
        )

class YoutubeModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="YouTube Downloader")
        self.url = discord.ui.TextInput(
            label="YouTube URL",
            placeholder="Enter YouTube video URL...",
            required=True
        )
        self.timestamp = discord.ui.TextInput(
            label="Timestamp (optional)",
            placeholder="Example: 1:30-2:45 or leave empty for full video",
            required=False
        )
        self.add_item(self.url)
        self.add_item(self.timestamp)

    def parse_timestamp(self, timestamp: str) -> tuple:
        if not timestamp or '-' not in timestamp:
            return None, None
            
        try:
            start, end = timestamp.split('-')
            
            # Convert timestamps to seconds
            def to_seconds(ts):
                parts = ts.strip().split(':')
                if len(parts) == 2:
                    m, s = map(int, parts)
                    return m * 60 + s
                elif len(parts) == 3:
                    h, m, s = map(int, parts)
                    return h * 3600 + m * 60 + s
                return int(ts)
                
            start_seconds = to_seconds(start)
            end_seconds = to_seconds(end)
            return start_seconds, end_seconds
            
        except:
            return None, None

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            # Extract video info first
            with yt_dlp.YoutubeDL() as ydl:
                info = ydl.extract_info(self.url.value, download=False)
                
                # Get more detailed info
                title = info['title']
                thumbnail = info.get('thumbnail', '')
                duration = info['duration']
                channel = info.get('uploader', 'Unknown')
                views = info.get('view_count', 0)
                likes = info.get('like_count', 0)
                upload_date = info.get('upload_date', '')
                
                # Format upload date
                if upload_date:
                    upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
                
                # Parse timestamps
                start_time, end_time = self.parse_timestamp(self.timestamp.value)
                
                # Create embed with more details
                embed = discord.Embed(
                    title=title,
                    url=self.url.value,
                    description=info.get('description', '')[:200] + "...",  # First 200 chars of description
                    color=discord.Color.red()
                )
                
                # Set large thumbnail
                if thumbnail:
                    embed.set_image(url=thumbnail)
                
                # Add video details
                embed.add_field(
                    name="Channel",
                    value=channel,
                    inline=True
                )
                embed.add_field(
                    name="Duration",
                    value=f"{duration//60}:{duration%60:02d}",
                    inline=True
                )
                embed.add_field(
                    name="Views",
                    value=f"{views:,}",
                    inline=True
                )
                if likes:
                    embed.add_field(
                        name="Likes",
                        value=f"👍 {likes:,}",
                        inline=True
                    )
                if upload_date:
                    embed.add_field(
                        name="Upload Date",
                        value=upload_date,
                        inline=True
                    )
                
                if start_time is not None and end_time is not None:
                    embed.add_field(
                        name="Selected Clip",
                        value=f"From {start_time}s to {end_time}s",
                        inline=True
                    )
                
                embed.set_footer(text="Select a download option below")
                
                # Create view with download options
                view = YoutubeDownloadView(self.url.value, info, start_time, end_time)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Error processing YouTube URL: {e}")
            await interaction.followup.send(
                "❌ Error processing video. Make sure the URL and timestamp format are valid.",
                ephemeral=True
            )

class YoutubeDownloadView(discord.ui.View):
    def __init__(self, url: str, info: dict, start_time: int = None, end_time: int = None):
        super().__init__(timeout=300)
        self.url = url
        self.info = info
        self.start_time = start_time
        self.end_time = end_time

    @discord.ui.button(label="Download MP4", style=discord.ButtonStyle.primary, emoji="🎥")
    async def mp4_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await interaction.followup.send(
                "⏳ Processing video... Please wait.",
                ephemeral=True
            )

            ydl_opts = {
                'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b',
                'outtmpl': '%(title)s.%(ext)s',
                'quiet': False,
                'no_warnings': False,
                'merge_output_format': 'mp4',
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                filename = ydl.prepare_filename(info)
                
                if not filename.endswith('.mp4'):
                    filename = filename.rsplit('.', 1)[0] + '.mp4'

                if not os.path.exists(filename):
                    raise Exception("Download failed - file not found")

                # If timestamps are provided, trim the video
                if self.start_time is not None and self.end_time is not None:
                    output_filename = f"trimmed_{filename}"
                    ffmpeg_cmd = [
                        'ffmpeg', '-i', filename,
                        '-ss', str(self.start_time),
                        '-t', str(self.end_time - self.start_time),
                        '-c', 'copy',
                        output_filename
                    ]
                    
                    process = await asyncio.create_subprocess_exec(
                        *ffmpeg_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    await process.communicate()
                    os.remove(filename)
                    filename = output_filename

                # Check file size and compress if needed
                file_size = os.path.getsize(filename)
                if file_size > 50 * 1024 * 1024:  # If larger than 50MB
                    compressed_filename = f"compressed_{filename}"
                    compress_cmd = [
                        'ffmpeg', '-i', filename,
                        '-vf', 'scale=1280:-2',  # Scale to 720p
                        '-c:v', 'libx264',
                        '-crf', '28',  # Higher CRF = more compression
                        '-c:a', 'aac',
                        '-b:a', '128k',
                        compressed_filename
                    ]
                    
                    process = await asyncio.create_subprocess_exec(
                        *compress_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    await process.communicate()
                    os.remove(filename)
                    filename = compressed_filename

                # Initialize Telegram bot and send video with longer timeout
                bot = telegram.Bot(TELEGRAM_BOT_TOKEN)
                
                try:
                    with open(filename, 'rb') as video_file:
                        message = await bot.send_video(
                            chat_id=TELEGRAM_CHAT_ID,
                            video=video_file,
                            caption=f"🎥 {info['title']}\n\nRequested by: {interaction.user.name}",
                            read_timeout=300,  # 5 minutes timeout
                            write_timeout=300,
                            connect_timeout=300,
                            pool_timeout=300
                        )
                        
                        video_link = f"https://t.me/c/{TELEGRAM_CHAT_ID.replace('-100', '')}/{message.message_id}"
                        
                        embed = discord.Embed(
                            title="✅ Video Downloaded Successfully!",
                            description=f"Video was uploaded to Telegram.\n\n[Click here to watch/download]({video_link})",
                            color=discord.Color.green()
                        )
                        if self.start_time is not None and self.end_time is not None:
                            embed.add_field(
                                name="Clip Duration", 
                                value=f"From {self.start_time}s to {self.end_time}s"
                            )
                        embed.set_footer(text="The video will be available on Telegram")
                        
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        
                except TelegramError as e:
                    print(f"Telegram Error: {e}")
                    await interaction.followup.send(
                        "❌ Error uploading to Telegram. The file might be too large even after compression.",
                        ephemeral=True
                    )
                
                # Clean up
                os.remove(filename)
                
        except Exception as e:
            print(f"Error downloading MP4: {e}")
            await interaction.followup.send(
                f"❌ Error downloading video: {str(e)}. Try downloading as audio instead.",
                ephemeral=True
            )

    @discord.ui.button(label="Download MP3", style=discord.ButtonStyle.success, emoji="🎵")
    async def mp3_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': '%(title)s.%(ext)s',
            }
            
            # Add timestamp options if provided
            if self.start_time is not None and self.end_time is not None:
                def download_range(info):
                    return [{
                        'start_time': self.start_time,
                        'end_time': self.end_time
                    }]
                
                ydl_opts['download_ranges'] = download_range
                ydl_opts['force_keyframes_at_cuts'] = True
                ydl_opts['postprocessor_args'] = [
                    '-ss', str(self.start_time),
                    '-t', str(self.end_time - self.start_time)
                ]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                filename = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
                
            # Send the file
            await interaction.followup.send(
                "✅ Here's your audio:",
                file=discord.File(filename),
                ephemeral=True
            )
            # Clean up
            os.remove(filename)
            
        except Exception as e:
            print(f"Error downloading MP3: {e}")
            await interaction.followup.send(
                "❌ Error downloading audio. Try a different format.",
                ephemeral=True
            )

    @discord.ui.button(label="Download Thumbnail", style=discord.ButtonStyle.secondary, emoji="🖼️")
    async def thumbnail_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            thumbnail_url = self.info['thumbnail']
            async with aiohttp.ClientSession() as session:
                async with session.get(thumbnail_url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        await interaction.followup.send(
                            "✅ Here's the thumbnail:",
                            file=discord.File(io.BytesIO(data), 'thumbnail.jpg'),
                            ephemeral=True
                        )
                    else:
                        raise Exception(f"HTTP {resp.status}")
                        
        except Exception as e:
            print(f"Error downloading thumbnail: {e}")
            await interaction.followup.send(
                "❌ Error downloading thumbnail.",
                ephemeral=True
            )

@bot.tree.command(
    name="ytdownload",
    description="Download YouTube videos as MP4/MP3"
)
async def ytdownload(interaction: discord.Interaction):
    """Download videos from YouTube"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    modal = YoutubeModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(
    name="help",
    description="Show all available commands"
)
async def help_command(interaction: discord.Interaction):
    """Shows all available commands"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    embed = discord.Embed(
        title="🤖 Bot Commands",
        description="Here are all the available commands:",
        color=discord.Color.blue()
    )

    # Utility Commands
    utility = """
`/help` - Show this help message
`/ping` - Check bot's latency
`/prefix` - Change bot prefix
`/settings` - View/edit bot settings
`/adduser` - Add allowed user
`/removeuser` - Remove allowed user
"""
    embed.add_field(name="⚙️ Utility", value=utility, inline=False)

    # Media Commands
    media = """
`/ytdownload` - Download YouTube videos/audio
• Supports timestamps (e.g., 1:30-2:45)
• Auto-uploads large videos to Telegram
• Supports MP4/MP3/Thumbnail download

`/movie` - Search for movies and streaming links
`/meme` - Create custom memes from templates
"""
    embed.add_field(name="🎬 Media", value=media, inline=False)

    # AI & Generation
    ai = """
`/imagine` - Generate images from text
`/gemini` - Chat with Google's Gemini AI
`/draw` - Create AI art with Stable Diffusion
"""
    embed.add_field(name="🤖 AI & Generation", value=ai, inline=False)

    # Notes & Triggers
    notes = """
`/note` - Create/manage notes
`/trigger` - Create/manage auto-responses
`/blacklist` - Manage blacklisted words
"""
    embed.add_field(name="📝 Notes & Triggers", value=notes, inline=False)

    # Gaming
    gaming = """
`/valorant` - Get Valorant player stats
`/valstats` - Detailed Valorant statistics
"""
    embed.add_field(name="🎮 Gaming", value=gaming, inline=False)

    # File Operations
    files = """
`/pdf` - Create/convert PDF files
`/docx` - Create/edit Word documents
`/csv` - Handle CSV files
"""
    embed.add_field(name="📁 Files", value=files, inline=False)

    embed.set_footer(text="All commands are slash commands • Some commands require specific permissions")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# Add these near your other commands
@bot.tree.command(
    name="hack",
    description="Fake a hacking animation on someone"
)
async def hack(interaction: discord.Interaction, user: discord.Member):
    """Pretends to hack someone with a fun animation"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
        
    await interaction.response.send_message(f"**{interaction.user.name}** is attempting to hack **{user.name}**...")
    
    # Pool of possible steps with their success rates
    possible_steps = [
        ("Accessing mainframe...", 90),
        ("Bypassing firewall...", 40),
        ("Cracking password hash...", 70),
        ("Accessing user files...", 50),
        ("Downloading personal data...", 60),
        ("Accessing Discord token...", 80),
        ("Stealing browser cookies...", 85),
        ("Injecting RAT malware...", 45),
        ("Encrypting user files...", 75),
        (f"Scanning {user.name}'s network...", 65),
        ("Bypassing 2FA...", 30),
        ("Accessing email accounts...", 55),
        ("Checking for vulnerabilities...", 70),
        ("Exploiting security holes...", 40),
        ("Installing backdoor...", 60)
    ]
    
    # Randomly select 6-10 steps
    num_steps = random.randint(6, 10)
    selected_steps = random.sample(possible_steps, num_steps)
    
    msg = await interaction.channel.send("```ini\n[Starting hack sequence...]```")
    progress = ""
    
    for step, success_rate in selected_steps:
        # Longer delay for downloading steps
        if "Downloading" in step:
            await asyncio.sleep(random.uniform(5, 10))
        else:
            await asyncio.sleep(random.uniform(1.5, 3))
            
        success = random.randint(1, 100) <= success_rate
        
        if success:
            progress += f"\n[+] {step}"
        else:
            progress += f"\n[-] {step} [FAILED]"
            # Add retry for failed steps (50% chance)
            if random.choice([True, False]):
                await asyncio.sleep(random.uniform(1, 2))
                progress += f"\n[+] Retrying {step.lower()}"
                
        await msg.edit(content=f"```ini\n{progress}```")
    
    # Always end with upload and success
    await asyncio.sleep(random.uniform(2, 4))
    progress += f"\n[+] Uploading {user.name}'s data to Dark Web..."
    await msg.edit(content=f"```ini\n{progress}```")
    
    await asyncio.sleep(2)
    progress += f"\n[+] ✅ Successfully hacked {user.name}!"
    await msg.edit(content=f"```ini\n{progress}```")
    
    # Show data upload summary
    summary = f"""```ini
[Hack Complete]
Target: {user.name}
Files Stolen: {random.randint(10000,99999)} files
Uploaded to {random.randint(8,21)} Dark Web sites
Server: #{''.join(random.choices('0123456789ABCDEF', k=8))}
Time: {random.randint(30,120)} seconds```"""
    
    await interaction.channel.send(summary)

@bot.tree.command(
    name="ip",
    description="Pretend to find someone's IP address (joke command)"
)
async def ip(interaction: discord.Interaction, user: discord.Member):
    """Generates a fake IP address for the joke"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return
        
    # Generate a random fake IP
    fake_ip = f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
    
    embed = discord.Embed(
        title="IP Address Found",
        description=f"**{interaction.user.name}** found **{user.name}**'s IP address:",
        color=discord.Color.red()
    )
    
    embed.add_field(
        name="IP Address",
        value=f"```{fake_ip}```",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(
    name="cardgen",
    description="Generate fake card details (joke command)"
)
async def cardgen(interaction: discord.Interaction, card_type: Literal["Visa", "Mastercard", "American Express", "Rupay"]):
    """Generates fake card details"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    # Card number patterns
    card_patterns = {
        "Visa": "4",
        "Mastercard": "5",
        "American Express": "3",
        "Rupay": "6"
    }

    # Card details based on type
    card_lengths = {
        "Visa": 16,
        "Mastercard": 16,
        "American Express": 15,
        "Rupay": 16
    }

    # Generate card number
    card_number = card_patterns[card_type]
    remaining_length = card_lengths[card_type] - len(card_number)
    card_number += ''.join([str(random.randint(0, 9)) for _ in range(remaining_length)])

    # Format card number
    if card_type == "American Express":
        formatted_number = f"{card_number[:4]} {card_number[4:10]} {card_number[10:]}"
    else:
        formatted_number = ' '.join([card_number[i:i+4] for i in range(0, len(card_number), 4)])

    # Generate expiry date (1-4 years from now)
    future_date = datetime.now() + timedelta(days=random.randint(365, 1460))
    expiry = future_date.strftime("%m/%y")

    # Generate CVV
    cvv = ''.join([str(random.randint(0, 9)) for _ in range(3 if card_type != "American Express" else 4)])

    # Card issuer names
    issuers = {
        "Visa": ["Chase", "Bank of America", "Wells Fargo", "Citibank"],
        "Mastercard": ["Capital One", "HSBC", "Barclays", "Deutsche Bank"],
        "American Express": ["American Express", "American Express", "American Express", "American Express"],
        "Rupay": ["SBI", "HDFC", "ICICI", "Punjab National Bank"]
    }

    # Create embed
    card_colors = {
        "Visa": discord.Color.blue(),
        "Mastercard": discord.Color.orange(),
        "American Express": discord.Color.dark_green(),
        "Rupay": discord.Color.dark_red()
    }

    # Add random person names
    first_names = [
        "John", "Emma", "Michael", "Sophia", "William", "Olivia", 
        "James", "Ava", "Alexander", "Isabella", "David", "Mia",
        "Daniel", "Charlotte", "Joseph", "Amelia", "Henry", "Emily"
    ]
    
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
        "Miller", "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor",
        "Thomas", "Moore", "Jackson", "Martin", "Lee", "Thompson"
    ]

    # Generate random name
    cardholder = f"{random.choice(first_names)} {random.choice(last_names)}"

    embed = discord.Embed(
        title=f"💳 Generated {card_type} Card",
        color=card_colors[card_type]
    )

    embed.add_field(
        name="Cardholder",
        value=f"```{cardholder}```",
        inline=False
    )

    embed.add_field(
        name="Card Number",
        value=f"```{formatted_number}```",
        inline=False
    )

    embed.add_field(
        name="Expiry",
        value=f"```{expiry}```",
        inline=True
    )

    embed.add_field(
        name="CVV",
        value=f"```{cvv}```",
        inline=True
    )

    embed.add_field(
        name="Issuer",
        value=f"```{random.choice(issuers[card_type])}```",
        inline=True
    )

    embed.set_footer(text="🎭 This is a joke command! All details are fake and randomly generated.")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(
    name="fakenitro",
    description="Send a fake Nitro gift (Rickroll)"
)
async def fakenitro(interaction: discord.Interaction):
    """Sends a fake Nitro gift that Rickrolls"""
    if interaction.user.id not in settings.get("allowed_users"):
        await unauthorized_message(interaction)
        return

    # Create a fake gift link
    gift_codes = [
        "xPvPfJNMhKqW9dzj",
        "nB8Vk7YtLmQc4RxH",
        "gT5wZsXnCj2KpFvM",
        "dW3hR9yUqA6NmEbG",
        "kY8xJ4fPtS7VcLwD"
    ]
    
    fake_code = random.choice(gift_codes)
    rickroll_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    embed = discord.Embed(
        title="You've been gifted a subscription!",
        description=(
            "🎮 **Discord Nitro Classic** (1 Month)\n\n"
            f"[`https://discord.gift/{fake_code}`]({rickroll_url})"
        ),
        color=0x2F3136  # Discord's dark theme color
    )
    
    embed.set_thumbnail(url="https://i.imgur.com/w9aiD6F.png")  # Discord Nitro logo
    
    # Random expiry time between 23-48 hours
    expires_in = random.randint(23, 48)
    embed.set_footer(text=f"Expires in {expires_in} hours")

    await interaction.response.send_message(embed=embed)

# Run the bot
bot.run(TOKEN) 