import os
from dotenv import load_dotenv

# Load .env file if it exists (for local development)
load_dotenv()

# Get environment variables with fallbacks
TOKEN = os.getenv('TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))
BOT_PREFIX = os.getenv('BOT_PREFIX', '!')
HENRIK_API_KEY = os.getenv('HENRIK_API_KEY', '')

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Validate required environment variables
if not all([TOKEN, OWNER_ID, SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError(
        "Missing required environment variables. Please check:\n"
        "- TOKEN (Discord Bot Token)\n"
        "- OWNER_ID (Your Discord User ID)\n"
        "- SUPABASE_URL\n"
        "- SUPABASE_KEY"
    ) 