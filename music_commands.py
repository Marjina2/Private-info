import discord
from discord import app_commands
import wavelink
from settings import Settings

settings = Settings()

def setup_music_commands(bot):
    @bot.tree.command(name="play", description="Play a song from YouTube")
    @app_commands.describe(query="Song name or YouTube URL")
    async def play(interaction: discord.Interaction, query: str):
        if interaction.user.id not in settings.get("allowed_users"):
            await unauthorized_message(interaction)
            return
        
        if not wavelink.NodePool.get_node():
            await interaction.response.send_message("Music system is still starting up. Please try again in a few seconds.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=False)
        await bot.music.play_track(interaction, query)

    @bot.tree.command(name="stop", description="Stop playing music")
    async def stop(interaction: discord.Interaction):
        if interaction.user.id not in settings.get("allowed_users"):
            await unauthorized_message(interaction)
            return
            
        if not interaction.guild.voice_client:
            await interaction.response.send_message("Not playing anything!", ephemeral=True)
            return
            
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Stopped playing music!", ephemeral=True)

async def unauthorized_message(interaction):
    await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True) 