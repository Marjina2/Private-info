import discord
import wavelink
from datetime import timedelta
from settings import Settings

settings = Settings()

class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
    
    async def play_track(self, interaction, query: str):
        if not interaction.guild.voice_client:
            if interaction.user.voice:
                try:
                    await interaction.user.voice.channel.connect(cls=wavelink.Player)
                    print(f"Connected to voice channel: {interaction.user.voice.channel.name}")
                except Exception as e:
                    print(f"Error connecting to voice channel: {e}")
                    await interaction.followup.send(f"Error joining voice channel: {str(e)}", ephemeral=True)
                    return
            else:
                await interaction.followup.send("You need to be in a voice channel!", ephemeral=True)
                return

        player = interaction.guild.voice_client
        
        try:
            # Check if we have a valid node
            node = wavelink.NodePool.get_node()
            if not node:
                await interaction.followup.send("Music system is not ready. Please try again in a few seconds.", ephemeral=True)
                return

            try:
                # Handle YouTube URLs directly
                if "youtube.com" in query or "youtu.be" in query:
                    tracks = await wavelink.YouTubeTrack.search(query)
                else:
                    # Use YouTube search for non-URLs
                    tracks = await wavelink.YouTubeTrack.search(query)
                
                if not tracks:
                    # Try SoundCloud as fallback
                    tracks = await wavelink.SoundCloudTrack.search(query)
                    if not tracks:
                        await interaction.followup.send("No tracks found! Try a different search term.", ephemeral=True)
                        return
                
                track = tracks[0]
                print(f"Found track: {track.title} ({track.uri if hasattr(track, 'uri') else 'No URI'})")

                if player.is_playing():
                    await player.stop()

                await player.set_volume(100)
                await player.play(track)
                
                duration = timedelta(seconds=int(track.duration))
                
                embed = discord.Embed(
                    title="🎵 Now Playing",
                    description=f"**{track.title}**\nDuration: {str(duration)}",
                    color=int(settings.get("embed_color"), 16)
                )
                if hasattr(track, 'thumbnail') and track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                
                await interaction.followup.send(embed=embed)
                
            except Exception as e:
                print(f"Error searching/playing track: {e}")
                await interaction.followup.send(f"Error with track: {str(e)}", ephemeral=True)
            
        except Exception as e:
            print(f"Error in play_track: {e}")
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True) 