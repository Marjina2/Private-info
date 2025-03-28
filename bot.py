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
from typing import List, Dict
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
    update_trigger
)
import aiohttp  # Add this to your imports
import google.generativeai as genai
from fpdf import FPDF
import io
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket
import time

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

# Run the bot
bot.run(TOKEN) 