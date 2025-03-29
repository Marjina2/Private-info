from supabase import create_client
import os
from datetime import datetime
from dotenv import load_dotenv
import json
from config import OWNER_ID
from typing import List, Dict

# Load environment variables
load_dotenv()

# Get Supabase credentials
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    print("Warning: Supabase credentials not found in environment variables")
    url = "https://uuxmcnaxiukashdbhjly.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV1eG1jbmF4aXVrYXNoZGJoamx5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDMxNTk3NzcsImV4cCI6MjA1ODczNTc3N30.kvscQN7wnw-xYiNDqe2BWvYk0er3iKVhMI_2iNyE4Jw"

try:
    supabase = create_client(url, key)
except Exception as e:
    print(f"Error connecting to Supabase: {e}")
    raise

async def log_unauthorized_access(user_id: int, username: str, server_name: str):
    try:
        data = {
            "user_id": str(user_id),
            "username": username,
            "server": server_name,
            "access_time": datetime.now().isoformat()
        }
        supabase.table("unauthorized_access").insert(data).execute()
    except Exception as e:
        print(f"Error logging unauthorized access: {e}")

async def get_unauthorized_users(page: int = 0, per_page: int = 5):
    try:
        response = supabase.table("unauthorized_access") \
            .select("*") \
            .order("access_time", desc=True) \
            .range(page * per_page, (page + 1) * per_page - 1) \
            .execute()
        
        total = supabase.table("unauthorized_access").select("count", count="exact").execute()
        return response.data, total.count
    except Exception as e:
        print(f"Error fetching unauthorized users: {e}")
        return [], 0

async def save_gemini_key(api_key: str):
    try:
        # Check if key exists
        response = supabase.table("settings").select("*").eq("key", "gemini_api_key").execute()
        
        if response.data:
            # Update existing key
            supabase.table("settings").update({"value": api_key}).eq("key", "gemini_api_key").execute()
        else:
            # Insert new key
            supabase.table("settings").insert({"key": "gemini_api_key", "value": api_key}).execute()
        return True
    except Exception as e:
        print(f"Error saving Gemini API key: {e}")
        return False

async def get_gemini_key():
    try:
        response = supabase.table("settings").select("value").eq("key", "gemini_api_key").execute()
        if response.data:
            return response.data[0]['value']
        return None
    except Exception as e:
        print(f"Error getting Gemini API key: {e}")
        return None

async def save_bot_prefix(prefix: str):
    try:
        response = supabase.table("settings").select("*").eq("key", "bot_prefix").execute()
        if response.data:
            supabase.table("settings").update({"value": prefix}).eq("key", "bot_prefix").execute()
        else:
            supabase.table("settings").insert({"key": "bot_prefix", "value": prefix}).execute()
        return True
    except Exception as e:
        print(f"Error saving bot prefix: {e}")
        return False

async def get_bot_prefix():
    try:
        response = supabase.table("settings").select("value").eq("key", "bot_prefix").execute()
        if response.data:
            return response.data[0]['value']
        return "/"  # Default prefix
    except Exception as e:
        print(f"Error getting bot prefix: {e}")
        return "/"

async def save_allowed_users(users: list):
    try:
        response = supabase.table("settings").select("*").eq("key", "allowed_users").execute()
        if response.data:
            supabase.table("settings").update({"value": json.dumps(users)}).eq("key", "allowed_users").execute()
        else:
            supabase.table("settings").insert({"key": "allowed_users", "value": json.dumps(users)}).execute()
        return True
    except Exception as e:
        print(f"Error saving allowed users: {e}")
        return False

async def get_allowed_users():
    try:
        response = supabase.table("settings").select("value").eq("key", "allowed_users").execute()
        if response.data:
            return json.loads(response.data[0]['value'])
        # If no data in Supabase, initialize with owner ID
        users = [OWNER_ID]
        await save_allowed_users(users)
        return users
    except Exception as e:
        print(f"Error getting allowed users: {e}")
        # Always ensure owner has access
        return [OWNER_ID]

async def add_allowed_user(user_id: int):
    try:
        users = await get_allowed_users()
        if user_id not in users:
            users.append(user_id)
            await save_allowed_users(users)
            return True
        return False
    except Exception as e:
        print(f"Error adding allowed user: {e}")
        return False

async def remove_allowed_user(user_id: int):
    try:
        users = await get_allowed_users()
        if user_id in users and user_id != OWNER_ID:
            users.remove(user_id)
            await save_allowed_users(users)
            return True
        return False
    except Exception as e:
        print(f"Error removing allowed user: {e}")
        return False

async def save_note(title: str, content: str):
    try:
        timestamp = datetime.now().isoformat()
        data = {
            "title": title,
            "content": content,
            "created_at": timestamp
        }
        response = supabase.table("notes").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving note: {e}")
        return False

async def get_notes(page: int = 0, per_page: int = 5):
    try:
        start = page * per_page
        response = supabase.table("notes") \
            .select("*") \
            .order("created_at", desc=True) \
            .range(start, start + per_page - 1) \
            .execute()
        
        # Get total count
        total = supabase.table("notes").select("count", count="exact").execute()
        
        return response.data, total.count
    except Exception as e:
        print(f"Error getting notes: {e}")
        return [], 0

async def update_note(note_id: int, content: str):
    try:
        response = supabase.table("notes") \
            .update({"content": content}) \
            .eq("id", note_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Error updating note: {e}")
        return False

async def delete_note(note_id: int):
    try:
        response = supabase.table("notes") \
            .delete() \
            .eq("id", note_id) \
            .execute()
        return True
    except Exception as e:
        print(f"Error deleting note: {e}")
        return False

async def save_trigger(name: str, response: str, server_id: int) -> bool:
    try:
        data = supabase.table('triggers').insert({
            "name": name,
            "response": response,
            "server_id": server_id
        }).execute()
        return True
    except Exception as e:
        print(f"Error saving trigger: {e}")
        return False

async def get_triggers(server_id: int) -> list:
    try:
        response = supabase.table('triggers').select("*").eq('server_id', server_id).execute()
        return response.data
    except Exception as e:
        print(f"Error getting triggers: {e}")
        return []

async def delete_trigger(trigger_id: int) -> bool:
    try:
        supabase.table('triggers').delete().eq('id', trigger_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting trigger: {e}")
        return False

async def update_trigger(trigger_id: int, name: str, response: str) -> bool:
    try:
        supabase.table('triggers').update({
            "name": name,
            "response": response
        }).eq('id', trigger_id).execute()
        return True
    except Exception as e:
        print(f"Error updating trigger: {e}")
        return False

async def add_to_blacklist(user_id: int, reason: str = "Unauthorized action") -> bool:
    """Add a user to the blacklist"""
    try:
        response = supabase.table('blacklist').insert({
            'user_id': user_id,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        print(f"Error adding user to blacklist: {e}")
        return False

async def remove_from_blacklist(user_id: int) -> bool:
    """Remove a user from the blacklist"""
    try:
        response = supabase.table('blacklist').delete().eq('user_id', user_id).execute()
        return True
    except Exception as e:
        print(f"Error removing user from blacklist: {e}")
        return False

async def is_blacklisted(user_id: int) -> bool:
    """Check if a user is blacklisted"""
    try:
        response = supabase.table('blacklist').select('user_id').eq('user_id', user_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking blacklist: {e}")
        return False

async def get_blacklist() -> List[Dict]:
    """Get all blacklisted users"""
    try:
        response = supabase.table('blacklist').select('*').execute()
        return response.data
    except Exception as e:
        print(f"Error getting blacklist: {e}")
        return [] 