import random

MEME_TEMPLATES = {
    # Popular Reaction Memes
    "Drake": {"id": "181913649", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/30b1gx.jpg", "description": "Drake preferring one thing over another"},
    "Woman Yelling at Cat": {"id": "188390779", "parts": 2, "labels": ["Woman", "Cat"], "preview": "https://i.imgflip.com/2puag9.jpg", "description": "Woman yelling at confused cat"},
    "Distracted Boyfriend": {"id": "112126428", "parts": 3, "labels": ["Other Girl", "Boyfriend", "Girlfriend"], "preview": "https://i.imgflip.com/1ur9b0.jpg", "description": "Guy looking back at another girl"},
    "Two Buttons": {"id": "87743020", "parts": 2, "labels": ["Left Button", "Right Button"], "preview": "https://i.imgflip.com/1g8my4.jpg", "description": "Sweating guy choosing buttons"},
    "Expanding Brain": {"id": "93895088", "parts": 4, "labels": ["Small Brain", "Normal", "Expanding", "Cosmic"], "preview": "https://i.imgflip.com/1jwhww.jpg", "description": "Brain expansion stages"},
    "Buff Doge vs. Cheems": {"id": "247375501", "parts": 2, "labels": ["Strong", "Weak"], "preview": "https://i.imgflip.com/43a45p.png", "description": "Strong vs weak comparison"},
    "Always Has Been": {"id": "252600902", "parts": 2, "labels": ["Reality", "Always has been"], "preview": "https://i.imgflip.com/46e43q.png", "description": "Astronaut realization"},
    "Gru's Plan": {"id": "131940431", "parts": 4, "labels": ["Step 1", "Step 2", "Step 3", "Realization"], "preview": "https://i.imgflip.com/26jxvz.jpg", "description": "Plan backfiring"},
    
    # Classic Memes
    "One Does Not Simply": {"id": "61579", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/1bij.jpg", "description": "Boromir's warning"},
    "Success Kid": {"id": "61544", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/1bhk.jpg", "description": "Victory baby"},
    "Ancient Aliens": {"id": "101470", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/26am.jpg", "description": "History Channel guy"},
    "Y U No": {"id": "61527", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/1bh3.jpg", "description": "Why you no guy"},
    "Bad Luck Brian": {"id": "61585", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/1bip.jpg", "description": "Unfortunate events"},
    
    # Modern Memes
    "Change My Mind": {"id": "129242436", "parts": 1, "labels": ["Opinion"], "preview": "https://i.imgflip.com/24y43o.jpg", "description": "Change my mind"},
    "Left Exit 12": {"id": "124822590", "parts": 2, "labels": ["Exit", "Straight"], "preview": "https://i.imgflip.com/22bdq6.jpg", "description": "Car taking exit"},
    "They're The Same Picture": {"id": "180190441", "parts": 2, "labels": ["Image 1", "Image 2"], "preview": "https://i.imgflip.com/2za3u1.jpg", "description": "Same pictures"},
    "Surprised Pikachu": {"id": "155067746", "parts": 1, "labels": ["Caption"], "preview": "https://i.imgflip.com/2kbn1e.jpg", "description": "Shocked Pikachu"},
    "Panik Kalm Panik": {"id": "226297822", "parts": 3, "labels": ["Panik", "Kalm", "Panik"], "preview": "https://i.imgflip.com/3qqcim.png", "description": "Panic stages"},
    
    # Gaming Memes
    "Pro Gamer Move": {"id": "214181568", "parts": 2, "labels": ["Setup", "Pro Gamer Move"], "preview": "https://i.imgflip.com/3ig4kv.jpg", "description": "Outstanding move"},
    "Among Us Emergency Meeting": {"id": "256775966", "parts": 1, "labels": ["Text"], "preview": "https://i.imgflip.com/4gah7q.jpg", "description": "Emergency meeting"},
    "Press F": {"id": "252758727", "parts": 1, "labels": ["Caption"], "preview": "https://i.imgflip.com/46hhvr.jpg", "description": "Press F to pay respects"},
    
    # Movie/TV Memes
    "This Is Fine": {"id": "55311130", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/wxica.jpg", "description": "Dog in burning room"},
    "Batman Slapping Robin": {"id": "438680", "parts": 2, "labels": ["Robin", "Batman"], "preview": "https://i.imgflip.com/9ehk.jpg", "description": "Batman slap"},
    "Anakin Padme": {"id": "322841258", "parts": 4, "labels": ["Anakin", "Padme", "Anakin 2", "Padme 2"], "preview": "https://i.imgflip.com/5c7lwq.jpg", "description": "Right? meme"},
    
    # Social Media Memes
    "Disaster Girl": {"id": "97984", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/23ls.jpg", "description": "Girl smiling at fire"},
    "Hide the Pain Harold": {"id": "27813981", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/gk5el.jpg", "description": "Harold hiding pain"},
    "Roll Safe": {"id": "89370399", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/1h7in3.jpg", "description": "Smart thinking"},
    
    # Animal Memes
    "Grumpy Cat": {"id": "405658", "parts": 2, "labels": ["Top", "Bottom"], "preview": "https://i.imgflip.com/8p0a.jpg", "description": "Grumpy Cat"},
    "Doge": {"id": "8072285", "parts": 5, "labels": ["Top", "Bottom", "Left", "Right", "Center"], "preview": "https://i.imgflip.com/4t0m5.jpg", "description": "Such wow"},
    "Evil Kermit": {"id": "84341851", "parts": 2, "labels": ["Me", "Evil Me"], "preview": "https://i.imgflip.com/1e7ql7.jpg", "description": "Dark side Kermit"},

    # Would you like me to continue with more templates? I can add:
    # - More gaming memes
    # - More movie/TV show memes
    # - More classic memes
    # - More current trending memes
    # - Specific themed memes (sports, school, work, etc.)
}

def get_random_templates(count=4):
    """Get a random selection of meme templates"""
    return dict(random.sample(list(MEME_TEMPLATES.items()), count))

def get_template_by_id(template_id):
    """Get a specific template by its ID"""
    for template in MEME_TEMPLATES.values():
        if template["id"] == template_id:
            return template
    return None 