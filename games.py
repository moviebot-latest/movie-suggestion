# ╔════════════════════════════════════════════════════════════╗
# ║  games.py — CineBot v10 — Advanced Games Module           ║
# ║                                                            ║
# ║  🎮 Quiz         — AI-generated, Difficulty levels        ║
# ║  🏆 Daily Chall  — 1 question/day, IST reset, leaderboard ║
# ║  🎬 Actor Connect — 2 actors ka connection dhundo         ║
# ║  🌐 Language     — User language preference               ║
# ║  🔍 Similar      — Genre filter + Vibe-based              ║
# ╚════════════════════════════════════════════════════════════╝
import asyncio, random, json, re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import now_ist, today_ist, GROQ_API
from storage import load_json, save_json, is_maintenance, is_admin
from helpers import progress_bar, animate_generic, FRAMES
from ai_engine import ai_ask, ai_similar_deep, ai_fix_movie_name


# ═══════════════════════════════════════════════════════════════
#  SECTION 1 — 🎮  QUIZ  (AI-generated, difficulty-aware)
# ═══════════════════════════════════════════════════════════════

_FALLBACK_QUESTIONS = {
    "easy": [
        {"q": "🎬 'Dilwale Dulhania Le Jayenge' ka hero kaun hai?",
         "opts": ["Salman Khan", "Shah Rukh Khan", "Aamir Khan", "Ajay Devgn"], "ans": 1},
        {"q": "🎬 'Bahubali' ka villain kaun hai?",
         "opts": ["Bhallaladeva", "Kattappa", "Bijjaladeva", "Inkoshi"], "ans": 0},
        {"q": "🎬 'Inception' ka director kaun hai?",
         "opts": ["Christopher Nolan", "Steven Spielberg", "James Cameron", "Ridley Scott"], "ans": 0},
        {"q": "🎬 'Sholay' mein Gabbar kaun bolta hai — 'Kitne Aadmi The?'",
         "opts": ["Jai", "Veeru", "Gabbar", "Thakur"], "ans": 2},
        {"q": "🎬 'Dangal' kis real person par based hai?",
         "opts": ["MS Dhoni", "Milkha Singh", "Mahavir Singh Phogat", "Saina Nehwal"], "ans": 2},
    ],
    "medium": [
        {"q": "🎬 'RRR' movie kab release hui?",
         "opts": ["2021", "2022", "2023", "2020"], "ans": 1},
        {"q": "🎬 'Andhadhun' mein main actor kaun hai?",
         "opts": ["Ayushmann Khurrana", "Rajkummar Rao", "Vicky Kaushal", "Irrfan Khan"], "ans": 0},
        {"q": "🎬 'Tumbbad' konse genre ki movie hai?",
         "opts": ["Action", "Comedy", "Horror/Fantasy", "Romance"], "ans": 2},
        {"q": "🎬 'KGF Chapter 2' mein villain kaun hai?",
         "opts": ["Rocky", "Adheera", "Garuda", "Andrews"], "ans": 1},
        {"q": "🎬 'Taare Zameen Par' kis ne direct kiya?",
         "opts": ["Rajkumar Hirani", "Aamir Khan", "Zoya Akhtar", "Vishal Bhardwaj"], "ans": 1},
    ],
    "hard": [
        {"q": "🎬 'Pyaasa' (1957) ka director kaun tha?",
         "opts": ["Bimal Roy", "Guru Dutt", "Mehboob Khan", "Raj Kapoor"], "ans": 1},
        {"q": "🎬 'Mughal-E-Azam' (1960) mein Salim ka role kisne kiya?",
         "opts": ["Dilip Kumar", "Raj Kumar", "Dev Anand", "Balraj Sahni"], "ans": 0},
        {"q": "🎬 'Pather Panchali' ka director kaun tha?",
         "opts": ["Mrinal Sen", "Ritwik Ghatak", "Satyajit Ray", "Tapan Sinha"], "ans": 2},
        {"q": "🎬 First Indian film jisne Cannes mein award jeeta?",
         "opts": ["Boot Polish", "Mother India", "Do Bigha Zamin", "Devdas"], "ans": 2},
        {"q": "🎬 'Sholay' (1975) ke cinematographer kaun the?",
         "opts": ["V.K. Murthy", "Dwarka Divecha", "Faredoon Irani", "Ramchandra"], "ans": 0},
    ],
}

_DIFF_EMOJIS   = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}
_DIFF_POINTS   = {"easy": 10,   "medium": 20,   "hard": 35}
_DIFF_LABELS   = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}

_CATEGORIES_BY_DIFF = {
    "easy": [
        "Popular Bollywood movies (2010-2024) — basic facts",
        "Popular South Indian movies — basic facts",
        "Famous Hollywood movies — basic facts",
        "Famous movie characters and actors",
    ],
    "medium": [
        "Bollywood classic movies (1970s-1990s)",
        "Award winning Indian movies (Filmfare/National Awards)",
        "Movie directors and their famous works",
        "Movie music composers and soundtracks",
        "Marvel and DC superhero movies — details",
    ],
    "hard": [
        "Rare Bollywood trivia from 1940s-1960s",
        "International cinema and arthouse films",
        "Oscars and Cannes — Indian films history",
        "Cinematography, editing, screenplay trivia",
        "Lesser-known facts about cult classic movies",
    ],
}


async def _ai_quiz_question(difficulty: str, asked_before: list) -> dict | None:
    """Groq se difficulty-aware unique MCQ banao."""
    if not GROQ_API:
        return None

    category  = random.choice(_CATEGORIES_BY_DIFF[difficulty])
    avoid_str = ""
    if asked_before:
        sample    = asked_before[-15:]
        avoid_str = "\n".join(f"- {q}" for q in sample)
        avoid_str = f"\n\nIn questions se BILKUL ALAG raho:\n{avoid_str}"

    diff_instruction = {
        "easy":   "Bahut simple question — popular movies, well-known facts. Koi bhi jawab de sake.",
        "medium": "Moderate difficulty — thoda soochna padega. General movie fan answer kar sake.",
        "hard":   "Bahut hard question — rare trivia, technical facts, classic cinema. Sirf expert answer kar sake.",
    }[difficulty]

    prompt = (
        f"You are a movie trivia quiz master.\n"
        f"Difficulty: {difficulty.upper()} — {diff_instruction}\n"
        f"Category: {category}{avoid_str}\n\n"
        f"Generate ONE unique MCQ question.\n"
        f"Rules:\n"
        f"- Hinglish mein (Hindi+English mix)\n"
        f"- Exactly 4 options\n"
        f"- Only ONE correct answer\n"
        f"- Start question with 🎬\n\n"
        f"Respond ONLY in this exact JSON, nothing else:\n"
        f'{{"q":"question","opts":["a","b","c","d"],"ans":0}}\n'
        f"ans = index of correct option (0-3)"
    )
    try:
        raw   = await ai_ask(prompt, max_tokens=300)
        if not raw:
            return None
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return None
        data  = json.loads(match.group())
        if (isinstance(data.get("q"), str) and
            isinstance(data.get("opts"), list) and len(data["opts"]) == 4 and
            isinstance(data.get("ans"), int) and 0 <= data["ans"] <= 3):
            return data
    except Exception as e:
        print(f"[QUIZ AI] {e}")
    return None


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /quiz            — difficulty selector
    /quiz easy       — easy question
    /quiz medium     — medium question
    /quiz hard       — hard question
    """
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return

    args       = context.args
    difficulty = args[0].lower() if args and args[0].lower() in ("easy", "medium", "hard") else None

    if not difficulty:
        keyboard = [[
            InlineKeyboardButton("🟢 Easy (+10)",   callback_data="quiz_diff_easy"),
            InlineKeyboardButton("🟡 Medium (+20)", callback_data="quiz_diff_medium"),
            InlineKeyboardButton("🔴 Hard (+35)",   callback_data="quiz_diff_hard"),
        ]]
        await update.message.reply_text(
            "╔══════════════════╗\n║  🎮  *MOVIE QUIZ*  ║\n╚══════════════════╝\n\n"
            "Difficulty choose karo 👇\n\n"
            "🟢 *Easy*   — Sabke liye, +10 pts\n"
            "🟡 *Medium* — Movie fans ke liye, +20 pts\n"
            "🔴 *Hard*   — Experts only, +35 pts",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await _send_quiz_question(update.message, context, difficulty)


async def quiz_diff_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Difficulty button callback."""
    query      = update.callback_query
    await query.answer()
    difficulty = query.data.replace("quiz_diff_", "")
    await query.message.delete()
    await _send_quiz_question(query.message, context, difficulty, chat_id=query.message.chat_id)


async def _send_quiz_question(msg, context, difficulty: str, chat_id=None):
    """Core: question fetch + send."""
    bot     = msg.get_bot() if hasattr(msg, "get_bot") else context.bot
    _chat   = chat_id or msg.chat_id

    loader  = await bot.send_message(
        chat_id=_chat,
        text=f"{_DIFF_EMOJIS[difficulty]} *{_DIFF_LABELS[difficulty]} question load ho raha hai...*\n" + progress_bar(0, 3),
        parse_mode="Markdown"
    )
    await animate_generic(loader, FRAMES["quiz"])
    try: await loader.delete()
    except: pass

    asked = context.user_data.get(f"quiz_asked_{difficulty}", [])
    total = context.user_data.get("quiz_total", 0)

    q = await _ai_quiz_question(difficulty, asked)
    if q is None:
        pool      = _FALLBACK_QUESTIONS[difficulty]
        remaining = [fq for fq in pool if fq["q"] not in asked] or pool
        q         = random.choice(remaining)
        source    = "📋"
    else:
        source = "🤖"

    asked.append(q["q"])
    if len(asked) > 60:
        asked = asked[-60:]
    total += 1

    context.user_data[f"quiz_asked_{difficulty}"] = asked
    context.user_data["quiz_total"]    = total
    context.user_data["quiz_ans"]      = q["ans"]
    context.user_data["quiz_q"]        = q["q"]
    context.user_data["quiz_opts"]     = q["opts"]
    context.user_data["quiz_diff"]     = difficulty

    keyboard = [
        [InlineKeyboardButton(f"{['A','B','C','D'][i]}. {opt}", callback_data=f"quiz_ans_{i}")]
        for i, opt in enumerate(q["opts"])
    ]
    await bot.send_message(
        chat_id=_chat,
        text=(
            f"╔══════════════════╗\n║  🎮  *MOVIE QUIZ*  ║\n╚══════════════════╝\n\n"
            f"{source} {_DIFF_EMOJIS[difficulty]} *{_DIFF_LABELS[difficulty]}* | Q #{total}\n\n"
            f"{q['q']}\n\n"
            f"_Sahi jawab = +{_DIFF_POINTS[difficulty]} points_ ⭐\n\nChoose your answer 👇"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def quiz_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    ans_idx    = int(query.data.replace("quiz_ans_", ""))
    correct    = context.user_data.get("quiz_ans", -1)
    difficulty = context.user_data.get("quiz_diff", "medium")
    uid        = str(query.from_user.id)
    total      = context.user_data.get("quiz_total", 1)
    opts       = context.user_data.get("quiz_opts", [])
    correct_text = opts[correct] if opts and 0 <= correct < len(opts) else "N/A"
    pts        = _DIFF_POINTS[difficulty]

    diff_again_btn = [[InlineKeyboardButton(
        f"🔁 Aur {_DIFF_LABELS[difficulty]} ({_DIFF_EMOJIS[difficulty]})",
        callback_data=f"quiz_diff_{difficulty}"
    )]]

    if ans_idx == correct:
        users = load_json("users")
        if uid in users:
            users[uid]["points"] = users[uid].get("points", 0) + pts
            save_json("users", users)
        await query.message.edit_text(
            f"✅ *SAHI JAWAB!* 🎉\n\n"
            f"+{pts} points! {_DIFF_EMOJIS[difficulty]} {_DIFF_LABELS[difficulty]}\n\n"
            f"_{context.user_data.get('quiz_q', '')}_\n\n"
            f"📊 Total played: *{total}* questions",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(diff_again_btn)
        )
    else:
        await query.message.edit_text(
            f"❌ *GALAT JAWAB!*\n\n"
            f"✅ Sahi tha: *{correct_text}*\n\n"
            f"_{context.user_data.get('quiz_q', '')}_\n\n"
            f"📊 Total played: *{total}* questions",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(diff_again_btn)
        )


# ═══════════════════════════════════════════════════════════════
#  SECTION 2 — 🏆  DAILY CHALLENGE
#  One question per day (IST), global leaderboard
# ═══════════════════════════════════════════════════════════════

async def _get_or_create_daily_challenge() -> dict:
    """
    Aaj ki daily challenge fetch/create karo.
    Stored in daily_challenge.json: { "date": "YYYY-MM-DD", "q": ..., "opts": [...], "ans": 0 }
    """
    today_str = str(today_ist())
    data      = load_json("daily_challenge", {})

    if data.get("date") == today_str and data.get("q"):
        return data  # already generated today

    # Generate new question (hard difficulty for daily)
    q = await _ai_quiz_question("hard", asked_before=[])
    if q is None:
        pool = _FALLBACK_QUESTIONS["hard"]
        q    = random.choice(pool)

    new_data = {
        "date":      today_str,
        "q":         q["q"],
        "opts":      q["opts"],
        "ans":       q["ans"],
        "scorers":   {},   # uid -> {"name": ..., "correct": bool, "time": ...}
    }
    save_json("daily_challenge", new_data)
    return new_data


async def daily_challenge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/daily_challenge — Aaj ka special question."""
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return

    uid  = str(update.effective_user.id)
    name = update.effective_user.full_name

    loader = await update.message.reply_text(
        "🏆 *Aaj ka Daily Challenge load ho raha hai...*\n" + progress_bar(0, 3),
        parse_mode="Markdown"
    )
    await animate_generic(loader, FRAMES["quiz"])
    try: await loader.delete()
    except: pass

    data = await _get_or_create_daily_challenge()

    # Check if already attempted today
    if uid in data.get("scorers", {}):
        entry   = data["scorers"][uid]
        result  = "✅ Sahi" if entry["correct"] else "❌ Galat"
        correct_opt = data["opts"][data["ans"]]
        await update.message.reply_text(
            f"🏆 *Daily Challenge* — {data['date']}\n\n"
            f"Tumne aaj pehle hi participate kar liya!\n\n"
            f"Tumhara jawab: {result}\n"
            f"✅ Sahi jawab: *{correct_opt}*\n\n"
            f"_/dc_leaderboard — Aaj ki ranking dekho_",
            parse_mode="Markdown"
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"{['A','B','C','D'][i]}. {opt}", callback_data=f"dc_ans_{i}")]
        for i, opt in enumerate(data["opts"])
    ]
    await update.message.reply_text(
        f"╔══════════════════════════╗\n"
        f"║  🏆  *DAILY CHALLENGE*    ║\n"
        f"╚══════════════════════════╝\n\n"
        f"📅 *{data['date']}* | 🔴 Hard Level\n\n"
        f"{data['q']}\n\n"
        f"_Sirf ek chance! Sahi = +50 pts_ ⭐\n\n"
        f"Choose your answer 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def dc_answer_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daily Challenge answer callback."""
    query   = update.callback_query
    await query.answer()
    ans_idx = int(query.data.replace("dc_ans_", ""))
    uid     = str(query.from_user.id)
    name    = query.from_user.full_name

    data = load_json("daily_challenge", {})
    if not data or data.get("date") != str(today_ist()):
        await query.message.edit_text("⚠️ Challenge expire ho gaya. Kal dobara aana!")
        return

    if uid in data.get("scorers", {}):
        await query.answer("Tumne pehle hi answer kar diya aaj!", show_alert=True)
        return

    correct    = data["ans"]
    is_correct = (ans_idx == correct)
    correct_opt = data["opts"][correct]

    scorers = data.get("scorers", {})
    scorers[uid] = {
        "name":    name,
        "correct": is_correct,
        "time":    now_ist().strftime("%I:%M %p"),
    }
    data["scorers"] = scorers
    save_json("daily_challenge", data)

    if is_correct:
        users = load_json("users")
        if uid in users:
            users[uid]["points"] = users[uid].get("points", 0) + 50
            save_json("users", users)
        msg = (
            f"✅ *SAHI JAWAB!* 🎉\n\n"
            f"+50 points! 🏆\n\n"
            f"_{data['q']}_\n\n"
            f"_/dc_leaderboard — Dekho tum kaun se rank par ho_"
        )
    else:
        msg = (
            f"❌ *GALAT JAWAB!*\n\n"
            f"✅ Sahi tha: *{correct_opt}*\n\n"
            f"_{data['q']}_\n\n"
            f"_Kal phir try karna!_ 🗓️\n"
            f"_/dc_leaderboard — Aaj ki ranking_"
        )
    await query.message.edit_text(msg, parse_mode="Markdown")


async def dc_leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dc_leaderboard — Aaj ke Daily Challenge ke winners."""
    data = load_json("daily_challenge", {})
    if not data or data.get("date") != str(today_ist()):
        await update.message.reply_text("🏆 Aaj ka challenge abhi start nahi hua. `/daily_challenge` try karo!", parse_mode="Markdown")
        return

    scorers  = data.get("scorers", {})
    winners  = [(uid, v) for uid, v in scorers.items() if v["correct"]]
    losers   = [(uid, v) for uid, v in scorers.items() if not v["correct"]]

    lines = [
        f"╔══════════════════════════╗\n"
        f"║  🏆 DAILY CHALLENGE BOARD ║\n"
        f"╚══════════════════════════╝\n\n"
        f"📅 *{data['date']}*\n"
        f"👥 Total attempts: *{len(scorers)}*\n"
        f"✅ Correct: *{len(winners)}* | ❌ Wrong: *{len(losers)}*\n\n"
    ]
    if winners:
        lines.append("🥇 *Sahi jawab dene wale:*\n")
        for i, (uid, v) in enumerate(winners[:10], 1):
            medal = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"{i}."
            lines.append(f"{medal} {v['name']} — _{v['time']}_\n")
    else:
        lines.append("_Abhi koi sahi jawab nahi diya._\n")

    lines.append(f"\n_Aaj ka question:_\n_{data['q']}_\n✅ _{data['opts'][data['ans']]}_")
    await update.message.reply_text("".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════
#  SECTION 3 — 🎬  ACTOR CONNECT
#  AI 2 actors ke beech connection dhundega
# ═══════════════════════════════════════════════════════════════

_ACTOR_PAIRS = [
    ("Shah Rukh Khan",   "Aamir Khan"),
    ("Amitabh Bachchan", "Rajesh Khanna"),
    ("Deepika Padukone", "Priyanka Chopra"),
    ("Ranbir Kapoor",    "Ranveer Singh"),
    ("Akshay Kumar",     "Salman Khan"),
    ("Irrfan Khan",      "Nawazuddin Siddiqui"),
    ("Vidya Balan",      "Kangana Ranaut"),
    ("Hrithik Roshan",   "Tiger Shroff"),
    ("Tom Hanks",        "Leonardo DiCaprio"),
    ("Meryl Streep",     "Cate Blanchett"),
    ("Rajinikanth",      "Kamal Haasan"),
    ("Prabhas",          "Allu Arjun"),
    ("Mohanlal",         "Mammootty"),
    ("Ayushmann Khurrana","Rajkummar Rao"),
    ("Tabu",             "Konkona Sen Sharma"),
]


async def actor_connect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /actorconnect                     — random pair
    /actorconnect <Actor1>, <Actor2>  — custom pair
    """
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return

    raw = " ".join(context.args).strip() if context.args else ""

    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        actor1, actor2 = parts[0], parts[1]
    else:
        actor1, actor2 = random.choice(_ACTOR_PAIRS)

    loader = await update.message.reply_text(
        f"🎬 *{actor1}* aur *{actor2}* ka connection dhundh raha hoon...\n" + progress_bar(0, 4),
        parse_mode="Markdown"
    )
    await animate_generic(loader, FRAMES["ai"])
    try: await loader.delete()
    except: pass

    prompt = (
        f"You are a movie expert. Find the cinematic connection between these two actors:\n"
        f"Actor 1: {actor1}\n"
        f"Actor 2: {actor2}\n\n"
        f"Give a creative, interesting answer covering:\n"
        f"🎬 *Common Movie(s)*: [koi shared film hai to bolo, warna N/A]\n"
        f"🎭 *Director Link*: [kisi common director ke saath kaam kiya?]\n"
        f"🏆 *Award Connection*: [koi shared award category ya year?]\n"
        f"🌟 *Interesting Fact*: [ek surprising connection]\n"
        f"🔗 *Verdict*: [1-2 lines mein puri connection summarize karo]\n\n"
        f"Hinglish mein jawab do. Fun aur engaging raho."
    )

    result = await ai_ask(prompt, max_tokens=500)
    if not result:
        result = "_AI se connection fetch nahi ho payi. Dobara try karo._"

    keyboard = [[
        InlineKeyboardButton("🔀 Random Pair", callback_data="ac_random"),
        InlineKeyboardButton("🎮 Quiz Khelo",  callback_data="quiz_diff_medium"),
    ]]
    await update.message.reply_text(
        f"╔══════════════════════════╗\n"
        f"║  🎬  *ACTOR CONNECT*      ║\n"
        f"╚══════════════════════════╝\n\n"
        f"👤 *{actor1}*\n"
        f"🔗 *vs*\n"
        f"👤 *{actor2}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{result}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 `/actorconnect Actor1, Actor2` — Custom pair try karo",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def ac_random_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Actor Connect random pair button."""
    query = update.callback_query
    await query.answer("🎬 Nayi pair load ho rahi hai...")
    actor1, actor2 = random.choice(_ACTOR_PAIRS)

    loader = await query.message.reply_text(
        f"🎬 *{actor1}* aur *{actor2}* ka connection...\n" + progress_bar(0, 4),
        parse_mode="Markdown"
    )
    await animate_generic(loader, FRAMES["ai"])
    try: await loader.delete()
    except: pass

    prompt = (
        f"Find cinematic connection between {actor1} and {actor2}.\n"
        f"🎬 *Common Movie(s)*: [ya N/A]\n"
        f"🎭 *Director Link*: [...]\n"
        f"🏆 *Award Connection*: [...]\n"
        f"🌟 *Interesting Fact*: [...]\n"
        f"🔗 *Verdict*: [...]\n"
        f"Hinglish mein. Short aur fun."
    )
    result = await ai_ask(prompt, max_tokens=500)
    if not result:
        result = "_Connection fetch nahi ho payi. Dobara try karo._"

    keyboard = [[
        InlineKeyboardButton("🔀 Random Pair", callback_data="ac_random"),
        InlineKeyboardButton("🎮 Quiz Khelo",  callback_data="quiz_diff_medium"),
    ]]
    await query.message.reply_text(
        f"👤 *{actor1}*  🔗 vs 🔗  👤 *{actor2}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{result}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ═══════════════════════════════════════════════════════════════
#  SECTION 4 — 🌐  LANGUAGE FILTER
# ═══════════════════════════════════════════════════════════════

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇮🇳 Hindi",   callback_data="setlang_Hindi"),
         InlineKeyboardButton("🇺🇸 English", callback_data="setlang_English")],
        [InlineKeyboardButton("🎬 Tamil",    callback_data="setlang_Tamil"),
         InlineKeyboardButton("🎬 Telugu",   callback_data="setlang_Telugu")],
        [InlineKeyboardButton("🎬 Punjabi",  callback_data="setlang_Punjabi"),
         InlineKeyboardButton("🌍 Any",      callback_data="setlang_Any")],
    ]
    await update.message.reply_text(
        "🌐 *Language Preference*\n━━━━━━━━━━━━━━━━━━\n\nDefault language filter select karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setlang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang  = query.data.replace("setlang_", "")
    uid   = str(query.from_user.id)
    users = load_json("users")
    if uid in users:
        users[uid]["lang"] = lang
        save_json("users", users)
    await query.message.edit_text(
        f"✅ *Language set:* `{lang}`\n\n_Ab tumhari AI suggestions {lang} prefer karengi._",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════
#  SECTION 5 — 🔍  SIMILAR MOVIES (Genre + Vibe-based)
# ═══════════════════════════════════════════════════════════════

_SIMILAR_GENRES  = ["Bollywood", "Hollywood", "South Indian", "Any"]
_SIMILAR_VIBES   = ["Same Director", "Same Actor", "Same Feel/Mood", "Any"]

_GENRE_EMOJIS    = {"Bollywood": "🇮🇳", "Hollywood": "🇺🇸", "South Indian": "🎬", "Any": "🌍"}
_VIBE_EMOJIS     = {"Same Director": "🎥", "Same Actor": "👤", "Same Feel/Mood": "🎭", "Any": "🔗"}


async def similar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /similar <movie name>  — genre + vibe selector dikhao phir search karo
    """
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "🎬 *Similar Movies*\n━━━━━━━━━━━━━━━━━━\n\n"
            "Usage: `/similar <movie name>`\n\n"
            "Examples:\n• `/similar Inception`\n• `/similar KGF Chapter 2`",
            parse_mode="Markdown"
        )
        return

    raw_title = " ".join(args).strip()
    context.user_data["similar_raw_title"] = raw_title

    # Show genre + vibe filter buttons
    genre_row = [
        InlineKeyboardButton(f"{_GENRE_EMOJIS[g]} {g}", callback_data=f"sim_g_{g}")
        for g in _SIMILAR_GENRES
    ]
    vibe_row  = [
        InlineKeyboardButton(f"{_VIBE_EMOJIS[v]} {v}", callback_data=f"sim_v_{v}")
        for v in _SIMILAR_VIBES
    ]
    await update.message.reply_text(
        f"🎬 *'{raw_title}'* jaisi movies:\n\n"
        f"*Genre filter* choose karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([genre_row])
    )
    # Store defaults
    context.user_data["similar_genre"] = "Any"
    context.user_data["similar_vibe"]  = "Any"


async def sim_genre_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genre select → then show vibe options."""
    query = update.callback_query
    await query.answer()
    genre = query.data.replace("sim_g_", "")
    context.user_data["similar_genre"] = genre

    vibe_row = [
        InlineKeyboardButton(f"{_VIBE_EMOJIS[v]} {v}", callback_data=f"sim_v_{v}")
        for v in _SIMILAR_VIBES
    ]
    raw_title = context.user_data.get("similar_raw_title", "movie")
    await query.message.edit_text(
        f"🎬 *'{raw_title}'* — Genre: *{_GENRE_EMOJIS[genre]} {genre}*\n\n"
        f"*Vibe* choose karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([vibe_row])
    )


async def sim_vibe_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vibe select → fetch similar movies."""
    query = update.callback_query
    await query.answer("🔍 Dhundh raha hoon...")

    vibe      = query.data.replace("sim_v_", "")
    genre     = context.user_data.get("similar_genre", "Any")
    raw_title = context.user_data.get("similar_raw_title", "")
    context.user_data["similar_vibe"] = vibe

    await query.message.edit_text(
        f"🔍 *Searching...*\n"
        f"Movie: *{raw_title}* | Genre: *{genre}* | Vibe: *{vibe}*\n"
        + progress_bar(1, 3),
        parse_mode="Markdown"
    )

    # Fix spelling
    fixed_title = await ai_fix_movie_name(raw_title)

    # Build enhanced prompt
    genre_instruction = "" if genre == "Any" else f"Sirf {genre} movies recommend karo."
    vibe_instruction  = {
        "Same Director": "Same director ki doosri movies prefer karo.",
        "Same Actor":    "Same lead actor ki doosri movies prefer karo.",
        "Same Feel/Mood":"Same emotional tone, atmosphere, aur feel wali movies recommend karo.",
        "Any":           "",
    }[vibe]

    prompt = (
        f"'{fixed_title}' jaisi 5 movies recommend karo.\n"
        f"{genre_instruction} {vibe_instruction}\n\n"
        f"Har movie ke liye ek solid reason do kyun similar hai.\n\n"
        f"Format:\n"
        f"🎬 1. Title (Year) — [reason, 1 line]\n"
        f"🎬 2. Title (Year) — [reason, 1 line]\n"
        f"🎬 3. Title (Year) — [reason, 1 line]\n"
        f"🎬 4. Title (Year) — [reason, 1 line]\n"
        f"🎬 5. Title (Year) — [reason, 1 line]\n\n"
        f"Hinglish mein. Interesting aur specific raho."
    )
    result = await ai_ask(prompt, max_tokens=500)

    if not result:
        await query.message.edit_text(
            f"😔 Similar movies nahi mil payi. Dobara try karo.\n"
            f"_/similar {raw_title}_",
            parse_mode="Markdown"
        )
        return

    title_display = fixed_title
    if fixed_title.lower() != raw_title.lower():
        title_display = f"{fixed_title} _(auto-corrected)_"

    genre_tag = f"{_GENRE_EMOJIS[genre]} {genre}" if genre != "Any" else "🌍 Any"
    vibe_tag  = f"{_VIBE_EMOJIS[vibe]} {vibe}"   if vibe  != "Any" else "🔗 Any"

    # Quick re-search buttons
    keyboard = [[
        InlineKeyboardButton("🔀 Change Filter", callback_data=f"sim_restart_{raw_title}"),
        InlineKeyboardButton("🎮 Quiz Khelo",    callback_data="quiz_diff_medium"),
    ]]

    await query.message.edit_text(
        f"╔══════════════════════╗\n"
        f"║  🎬  *SIMILAR MOVIES*  ║\n"
        f"╚══════════════════════╝\n\n"
        f"🎯 *'{title_display}'*\n"
        f"📂 Genre: {genre_tag} | 🎭 Vibe: {vibe_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{result}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 `/movie <title>` — Kisi bhi movie ki full info",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def sim_restart_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'Change Filter' button — genre picker phir dikhao."""
    query     = update.callback_query
    await query.answer()
    raw_title = query.data.replace("sim_restart_", "")
    context.user_data["similar_raw_title"] = raw_title

    genre_row = [
        InlineKeyboardButton(f"{_GENRE_EMOJIS[g]} {g}", callback_data=f"sim_g_{g}")
        for g in _SIMILAR_GENRES
    ]
    await query.message.edit_text(
        f"🎬 *'{raw_title}'* — Nayi search\n\n*Genre filter* choose karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([genre_row])
    )


async def similar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Inline button from movie card:
    callback_data = 'similar_<title>|<year>|<genre>'
    """
    query = update.callback_query
    await query.answer("🔍 Similar movies dhundh raha hoon...")
    try:
        payload = query.data.replace("similar_", "", 1)
        parts   = payload.split("|")
        title   = parts[0] if len(parts) > 0 else "Unknown"
        year    = parts[1] if len(parts) > 1 else ""
        genre   = parts[2] if len(parts) > 2 else ""
    except Exception:
        title, year, genre = "Unknown", "", ""

    loader = await query.message.reply_text(
        f"🔍 *'{title}' jaisi movies...*\n" + progress_bar(0, 3),
        parse_mode="Markdown"
    )
    await animate_generic(loader, FRAMES["similar"])
    try: await loader.delete()
    except: pass

    result = await ai_similar_deep(title=title, year=year, genre=genre)
    if not result:
        await query.message.reply_text("😔 Similar movies abhi nahi mil payi. Dobara try karo.", parse_mode="Markdown")
        return

    await query.message.reply_text(
        f"🎬 *'{title}'* jaisi movies:\n━━━━━━━━━━━━━━━━━━━━━━\n\n{result}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n💡 `/movie <title>` — Full details",
        parse_mode="Markdown"
    )
