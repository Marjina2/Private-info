import os
from dotenv import load_dotenv

# Load .env file if it exists (for local development)
load_dotenv()

# Get environment variables with fallbacks
TOKEN = os.environ.get('TOKEN') or os.getenv('TOKEN')
OWNER_ID = int(os.environ.get('OWNER_ID', 0)) or int(os.getenv('OWNER_ID', 0))
BOT_PREFIX = os.environ.get('BOT_PREFIX', '!') or os.getenv('BOT_PREFIX', '!')
HENRIK_API_KEY = os.environ.get('HENRIK_API_KEY', '') or os.getenv('HENRIK_API_KEY', '')

# Supabase configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL') or os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY') or os.getenv('SUPABASE_KEY')

# Print environment variable status (for debugging)
print("Environment Variables Status:")
print(f"TOKEN: {'Set' if TOKEN else 'Missing'}")
print(f"OWNER_ID: {'Set' if OWNER_ID else 'Missing'}")
print(f"SUPABASE_URL: {'Set' if SUPABASE_URL else 'Missing'}")
print(f"SUPABASE_KEY: {'Set' if SUPABASE_KEY else 'Missing'}")

# Validate required environment variables
if not all([TOKEN, OWNER_ID, SUPABASE_URL, SUPABASE_KEY]):
    missing_vars = []
    if not TOKEN: missing_vars.append("TOKEN")
    if not OWNER_ID: missing_vars.append("OWNER_ID")
    if not SUPABASE_URL: missing_vars.append("SUPABASE_URL")
    if not SUPABASE_KEY: missing_vars.append("SUPABASE_KEY")
    
    raise ValueError(
        f"Missing required environment variables: {', '.join(missing_vars)}\n"
        "Please check your environment variables in Render dashboard."
    ) 