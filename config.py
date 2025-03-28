from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Discord bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID'))
BOT_PREFIX = os.getenv('BOT_PREFIX')
HENRIK_API_KEY = os.getenv('HENRIK_API_KEY') 