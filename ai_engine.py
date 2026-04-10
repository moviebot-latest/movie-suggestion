# ╔══════════════════════════════════════════╗
# ║  ai_engine.py — All Groq AI functions    ║
# ║  Edit to change AI prompts / model       ║
# ╚══════════════════════════════════════════╝
import asyncio, aiohttp, logging
from typing import Optional
from config import GROQ_API, GROQ_URL, GROQ_MODEL

async def ai_ask(prompt: str, max_tokens: int = 1000) -> Optional[str]:
    """Core async Groq API caller."""
    if not GROQ_API:
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_API}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.75,
    }
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(GROQ_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                elif resp.status == 429:
                    await asyncio.sleep(5)
                    return None
                else:
                    text = await resp.text()
                    print(f"⚠️ Groq API Error {resp.status}: {text[:200]}")
                    return None
    except asyncio.TimeoutError:
        print("⚠️ Groq API timeout")
        return None
    except Exception as e:
        print(f"⚠️ Groq API Exception: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════
#          GROQ AI — ORIGINAL FUNCTIONS (v9)
# ═══════════════════════════════════════════════════════════════════
async def ai_fix_movie_name(raw_name: str) -> str:
    if not GROQ_API:
        return raw_name
    result = await ai_ask(
        f"User typed this movie name: '{raw_name}'\n"
        "Fix spelling/Hinglish and return ONLY the correct English movie title.\n"
        "Examples: 'rrr' → 'RRR', 'kgf2' → 'KGF Chapter 2', 'andha dhun' → 'Andhadhun'\n"
        "Return ONLY the movie title, nothing else."
    )
    if result:
        fixed = result.strip().strip('"').strip("'")
        if len(fixed) < 60:
            return fixed
    return raw_name

async def ai_recommend(query: str) -> Optional[str]:
    return await ai_ask(
        f"You are a movie expert. {query}\n"
        "Give exactly 5 recommendations.\n"
        "Format: 🎬 Title (Year) — One line reason\n"
        "Be concise. Reply in same language as query."
    )

async def ai_plot_search(plot_desc: str) -> Optional[str]:
    return await ai_ask(
        f"A user describes a movie plot: '{plot_desc}'\n"
        "Identify the most likely movie(s) this refers to.\n"
        "Give top 3 guesses.\n"
        "Format: 🎬 Title (Year) — Why it matches\n"
        "Be concise."
    )

async def ai_movie_review(title: str, year: str, plot: str, rating: str) -> Optional[str]:
    return await ai_ask(
        f"Write a short, engaging movie review for '{title}' ({year}).\n"
        f"IMDb Rating: {rating}/10\nPlot summary: {plot}\n\n"
        "Write 3-4 sentences. Be honest, fun, and informative.\n"
        "End with a recommendation: Watch / Skip / Must Watch.\n"
        "Reply in Hinglish (mix of Hindi and English)."
    )

async def ai_fun_facts(title: str, year: str, director: str, actors: str) -> Optional[str]:
    return await ai_ask(
        f"Give 3 interesting behind-the-scenes fun facts about '{title}' ({year}).\n"
        f"Director: {director}, Cast: {actors}\n"
        "Format: 💡 Fact\nBe interesting and surprising. Keep each fact 1-2 lines.\n"
        "Reply in Hinglish (mix of Hindi and English)."
    )

async def ai_mood_recommend(mood: str) -> Optional[str]:
    return await ai_ask(
        f"User ka mood hai: '{mood}'\n"
        "Is mood ke hisaab se 5 perfect movies recommend karo.\n"
        "Format: 🎬 Title (Year) — Why perfect for this mood\n"
        "Be empathetic and fun. Reply in Hinglish."
    )

async def ai_compare_movies(movie1: str, movie2: str) -> Optional[str]:
    return await ai_ask(
        f"Compare these two movies in detail:\nMovie 1: {movie1}\nMovie 2: {movie2}\n\n"
        "Compare on: Story, Acting, Direction, Entertainment, Overall\n"
        "Format each point clearly. End with a winner recommendation.\n"
        "Reply in Hinglish (mix of Hindi and English). Be fun and opinionated."
    )


# ═══════════════════════════════════════════════════════════════════
#    ✅ NEW — FULL AI ANALYSIS FUNCTIONS (from movie_finder_groq)
# ═══════════════════════════════════════════════════════════════════
async def ai_full_review(title: str, year: str, genre: str, plot: str,
                         rating: str, director: str, actors: str, awards: str) -> Optional[str]:
    """Comprehensive review — positives, negatives, verdict, AI rating."""
    return await ai_ask(
        f"""Tum ek expert movie critic ho. Is movie ki detailed review likho:

Movie   : {title} ({year})
Genre   : {genre}
Rating  : {rating}/10
Director: {director}
Cast    : {actors}
Awards  : {awards}
Plot    : {plot[:400]}

BILKUL is format mein likho:

📝 *REVIEW:*
[3-4 lines, engaging aur honest]

✅ *POSITIVES:*
• [point 1]
• [point 2]
• [point 3]

❌ *NEGATIVES:*
• [point 1]
• [point 2]

🎯 *VERDICT:* [Watch / Skip / Must Watch / Wait for OTT]
⭐ *AI RATING:* [X/10]

Hinglish mein likho. Fun aur opinionated raho.""",
        max_tokens=900
    )

async def ai_similar_deep(title: str, year: str, genre: str) -> Optional[str]:
    """5 similar movies with solid reasons — deeper than basic similar."""
    return await ai_ask(
        f"""'{title}' ({year}) — Genre: {genre}

Is movie jaisi 5 movies recommend karo. Ek solid reason do kyun similar hai.

Format:
🎬 1. Title (Year) — [reason, 1 line]
🎬 2. Title (Year) — [reason, 1 line]
🎬 3. Title (Year) — [reason, 1 line]
🎬 4. Title (Year) — [reason, 1 line]
🎬 5. Title (Year) — [reason, 1 line]

Hinglish mein. Hindi aur English movies mix karo.""",
        max_tokens=450
    )

async def ai_mood_match(title: str, genre: str, plot: str) -> Optional[str]:
    """Perfect mood, time, company aur snack suggestion."""
    return await ai_ask(
        f"""Movie: '{title}'
Genre: {genre}
Plot: {plot[:300]}

Batao:
🎭 *Best Mood*     : [kaunsi feeling mein dekhni chahiye]
👥 *Best With*     : [akele / dost / family / couple]
🕐 *Best Time*     : [din / raat / weekend / rainy day]
🍿 *Snack Suggest* : [kya khana chahiye saath mein — fun answer]
💬 *One-Line Pitch*: [ek zabardast line jis se dost convince ho jaye]

Hinglish mein likho, creative aur fun raho.""",
        max_tokens=350
    )

async def ai_cast_analysis(title: str, actors: str, director: str) -> Optional[str]:
    """Director + cast ki performance analysis."""
    return await ai_ask(
        f"""Movie '{title}' mein in logon ki performance ke baare mein analysis karo:

Director : {director}
Cast     : {actors}

Har ek ke liye:
🎬 [Naam] — [1-2 line performance analysis ya career highlight]

End mein:
🏆 *Standout Performance:* [sabse acha kaun tha aur kyun — 2 lines]

Hinglish mein. Honest aur specific raho.""",
        max_tokens=600
    )

async def ai_trivia_quiz_movie(title: str, year: str, director: str, actors: str) -> Optional[str]:
    """Ek MCQ trivia question for this specific movie."""
    return await ai_ask(
        f"""Movie '{title}' ({year}) ke baare mein ek interesting MCQ trivia question banao.
Director: {director}, Cast: {actors}

EXACTLY is format mein:
❓ *Question:* [question]

   A) [option]
   B) [option]
   C) [option]
   D) [option]

✅ *Answer:* [correct option letter] — [correct answer]
💡 *Fact:* [ek interesting related fact, 1-2 lines]

Hinglish mein. Lesser-known fact pe based question banana.""",
        max_tokens=400
    )


# ═══════════════════════════════════════════════════════════════════
#         MOVIE INFO MODULE (TMDB-based)
# ═══════════════════════════════════════════════════════════════════
_mi_logger = logging.getLogger("movie_info")
_mi_logger.setLevel(logging.DEBUG)

TMDB_BASE      = "https://api.themoviedb.org/3"
TMDB_IMG_BASE  = "https://image.tmdb.org/t/p/w500"
OMDB_BASE      = "https://www.omdbapi.com"
MI_TIMEOUT     = aiohttp.ClientTimeout(total=8)
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 1.5
CACHE_TTL      = 3600

_mi_cache: dict = {}

