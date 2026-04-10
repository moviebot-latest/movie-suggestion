# ╔══════════════════════════════════════════╗
# ║  movie_search.py — Movie search & card   ║
# ║  Edit to change movie search UI/features ║
# ╚══════════════════════════════════════════╝
import asyncio, requests, re
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OMDB_API, TMDB_API, now_ist, GROQ_API
from config import (W_URL, W_NAME, W_MAINT_MSG, W_BROADCAST,
                    W_AI_QUERY, W_PLOT_SEARCH, W_LANG_FILTER,
                    W_ALERT_MOVIE, W_BAN_USER, W_QUIZ,
                    W_MOOD, W_COMPARE_1, W_COMPARE_2, W_RATE_MOVIE,
                    W_ADDADMIN)
from storage import (is_banned, is_maintenance, is_admin, register_user,
                     add_search_points, log_search, get_user_lang, load_servers, load_json)
from helpers import progress_bar, animate_search, animate_generic, FRAMES, get_badge, build_star_bar
from ai_engine import (ai_ask, ai_fix_movie_name, ai_movie_review, ai_fun_facts,
                       ai_full_review, ai_similar_deep, ai_mood_match,
                       ai_cast_analysis, ai_trivia_quiz_movie)
from movie_info import get_movie_info
from helpers import get_omdb, get_omdb_search

# ═══════════════════════════════════════════════════════════════════
#                    CONVERSATION STATES — defined in config.py
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════
#                    /start
# ═══════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_id = None
    if context.args:
        try: ref_id = int(context.args[0])
        except: pass
    register_user(user, ref_id)
    if is_banned(user.id):
        await update.message.reply_text("🚫 You are banned.")
        return
    if is_maintenance() and not is_admin(user.id):
        maint = load_json("maintenance", {"active": False, "message": "🔧 Maintenance..."})
        await update.message.reply_text(
            f"🚧 *CineBot — Maintenance*\n\n{maint.get('message', '')}",
            parse_mode="Markdown"
        )
        return
    users  = load_json("users")
    uid    = str(user.id)
    udata  = users.get(uid, {})
    points = udata.get("points", 0)
    refs   = udata.get("refs",   0)
    badge  = get_badge(points)
    ai_status = "✅ Groq AI" if GROQ_API else "⚠️ No AI"
    admin_btn = []
    if is_admin(user.id):
        admin_btn = [[InlineKeyboardButton("👑 Admin Panel", callback_data="open_admin")]]
    keyboard = [
        [InlineKeyboardButton("🔥 Trending",    callback_data="cmd_trending"),
         InlineKeyboardButton("🎲 Random",      callback_data="cmd_random")],
        [InlineKeyboardButton("📅 Upcoming",    callback_data="cmd_upcoming"),
         InlineKeyboardButton("🎯 Daily Pick",  callback_data="cmd_daily")],
        [InlineKeyboardButton("❤️ Watchlist",   callback_data="cmd_watchlist"),
         InlineKeyboardButton("📊 My Stats",    callback_data="cmd_mystats")],
        [InlineKeyboardButton("🤖 AI Suggest",  callback_data="cmd_suggest"),
         InlineKeyboardButton("🔍 Plot Search", callback_data="cmd_plotsearch")],
        [InlineKeyboardButton("🎭 Mood Pick",   callback_data="cmd_mood"),
         InlineKeyboardButton("⚖️ Compare",     callback_data="cmd_compare")],
        [InlineKeyboardButton("🎮 Quiz",        callback_data="cmd_quiz"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="cmd_leaderboard")],
        [InlineKeyboardButton("📜 History",     callback_data="cmd_history"),
         InlineKeyboardButton("👥 Refer",       callback_data="cmd_refer")],
    ] + admin_btn
    await update.message.reply_text(
        f"╔═══════════════════════╗\n"
        f"║   🎬  *C I N E B O T*  v9   ║\n"
        f"╚═══════════════════════╝\n\n"
        f"✨ *Welcome, {user.first_name}!*\n\n"
        f"┌─────────────────────┐\n"
        f"│  {badge}\n"
        f"│  ⭐ `{points}` Points  •  👥 `{refs}` Refers\n"
        f"│  🤖 {ai_status}\n"
        f"└─────────────────────┘\n\n"
        f"🔎 *Movie dhundhna ho?*\n"
        f"_Seedha movie ka naam type karo!_\n\n"
        f"🤖 *Groq AI Powered Search*\n"
        f"_Galat naam, Hinglish — sab samjha jayega!_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ═══════════════════════════════════════════════════════════════════
#              START BUTTON CALLBACKS
# ═══════════════════════════════════════════════════════════════════
async def start_btn_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cmd = query.data.replace("cmd_", "")
    fake_update = type('obj', (object,), {
        'effective_user': query.from_user,
        'message':        query.message,
        'effective_chat': query.message.chat,
    })()
    if   cmd == "trending":     await trending_cmd(fake_update, context)
    elif cmd == "random":       await random_cmd(fake_update, context)
    elif cmd == "upcoming":     await upcoming_cmd(fake_update, context)
    elif cmd == "daily":        await daily_cmd(fake_update, context)
    elif cmd == "watchlist":    await watchlist_cmd(fake_update, context)
    elif cmd == "mystats":      await mystats_cmd(fake_update, context)
    elif cmd == "refer":        await refer_cmd(fake_update, context)
    elif cmd == "leaderboard":  await leaderboard_cmd(fake_update, context)
    elif cmd == "history":      await history_cmd(fake_update, context)
    elif cmd == "quiz":         await quiz_cmd(fake_update, context)
    elif cmd == "open_admin":   await admin_panel(fake_update, context)
    elif cmd in ("suggest", "plotsearch", "mood", "compare"):
        pass


# ═══════════════════════════════════════════════════════════════════
#   MOVIE CARD (OMDB) — ✅ 2 naye rows added: Mood/Cast + Trivia/Package
# ═══════════════════════════════════════════════════════════════════
async def _send_movie_card(update, context, data, reply_to=None, is_search=False):
    title    = data.get("Title",      "N/A")
    year     = data.get("Year",       "N/A")
    rating   = data.get("imdbRating", "N/A")
    genre    = data.get("Genre",      "N/A")
    runtime  = data.get("Runtime",    "N/A")
    director = data.get("Director",   "N/A")
    actors   = data.get("Actors",     "N/A")
    plot     = data.get("Plot",       "N/A")
    language = data.get("Language",   "N/A")
    poster   = data.get("Poster",     "N/A")
    votes    = data.get("imdbVotes",  "N/A")
    awards   = data.get("Awards",     "N/A")
    rated    = data.get("Rated",      "N/A")
    boxoff   = data.get("BoxOffice",  "N/A")
    imdb_id  = data.get("imdbID",     "")

    rt_score = "N/A"
    for r in data.get("Ratings", []):
        if "Rotten Tomatoes" in r.get("Source", ""):
            rt_score = r["Value"]

    if not poster or poster == "N/A":
        poster = None
        if TMDB_API:
            try:
                r = requests.get(
                    f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API}&query={quote(title)}",
                    timeout=5
                )
                results = r.json().get("results", [])
                if results and results[0].get("poster_path"):
                    poster = f"https://image.tmdb.org/t/p/w500{results[0]['poster_path']}"
            except Exception:
                poster = None

    ratings_db  = load_json("ratings")
    movie_rates = ratings_db.get(title, {})
    if movie_rates:
        avg_rate = sum(movie_rates.values()) / len(movie_rates)
        comm_rat = f"⭐ `{avg_rate:.1f}/5` ({len(movie_rates)} votes)"
    else:
        comm_rat = "_No ratings yet_"

    star_bar     = build_star_bar(rating)
    search_query = quote(title)
    servers      = load_servers()
    urls         = [servers[f"s{i}"]["url"] + search_query for i in range(1, 7)]
    names        = [servers[f"s{i}"]["name"]               for i in range(1, 7)]
    trailer      = f"https://www.youtube.com/results?search_query={quote(title + ' trailer')}"
    subs_url     = f"https://subscene.com/subtitles/searchbytitle?query={search_query}"

    try:
        uid = str(update.effective_user.id)
    except Exception:
        uid = "0"

    log_search(title, uid)
    if is_search:
        add_search_points(uid)

    caption = (
        f"🎬 *{title}*  `{year}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{star_bar}\n"
        f"⭐ *IMDb:* `{rating}/10`   🍅 *RT:* `{rt_score}`\n"
        f"👥 *Community:* {comm_rat}\n"
        f"🗳 *Votes:* `{votes}`   🔞 *Rated:* `{rated}`\n\n"
        f"🎭 *Genre:*    `{genre}`\n"
        f"⏱ *Runtime:* `{runtime}`\n"
        f"🌍 *Lang:*     `{language}`\n"
        f"🎥 *Director:* `{director}`\n"
        f"👥 *Cast:*     `{actors}`\n"
        f"💰 *Box Office:* `{boxoff}`\n"
        f"🏆 *Awards:* `{awards}`\n\n"
        f"📖 *Story:*\n_{plot}_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ 6 Servers  •  🦁 Brave = No Ads"
    )

    msg_obj = reply_to if reply_to else update.message

    # Temp keyboard (before msg_id is known)
    temp_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title.replace('|','').replace('\\','')[:40]}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",    callback_data="s_tmp"),
         InlineKeyboardButton("🎯 Similar",          callback_data="sim_tmp")],
        [InlineKeyboardButton("🤖 AI Review",        callback_data="rev_tmp"),
         InlineKeyboardButton("💡 Fun Facts",        callback_data="fun_tmp")],
        [InlineKeyboardButton("⭐ Rate Movie",       callback_data="rate_tmp"),
         InlineKeyboardButton("🎥 Director Top 5",  callback_data=f"dir_{quote(director, safe='')}")],
        # ✅ NEW ROW 1 — Full Analysis
        [InlineKeyboardButton("📝 Full Review",      callback_data="frev_tmp"),
         InlineKeyboardButton("🎭 Mood Match",       callback_data="mood_match_tmp")],
        # ✅ NEW ROW 2
        [InlineKeyboardButton("🌟 Cast Analysis",    callback_data="cast_tmp"),
         InlineKeyboardButton("❓ Trivia Quiz",      callback_data="trivia_tmp")],
        # ✅ NEW ROW 3
        [InlineKeyboardButton("🔥 Full AI Package",  callback_data="pkg_tmp")],
    ])

    if poster:
        try:
            sent = await msg_obj.reply_photo(
                photo=poster, caption=caption,
                parse_mode="Markdown", reply_markup=temp_keyboard
            )
        except Exception:
            sent = await msg_obj.reply_text(
                f"⚠️ _Poster load nahi hua_\n\n{caption}",
                parse_mode="Markdown", reply_markup=temp_keyboard
            )
    else:
        sent = await msg_obj.reply_text(
            caption, parse_mode="Markdown", reply_markup=temp_keyboard
        )

    msg_id = str(sent.message_id)
    # ✅ Store genre, awards too for new AI functions
    context.user_data[msg_id] = {
        "servers":  urls,
        "names":    names,
        "trailer":  trailer,
        "title":    title,
        "year":     year,
        "rating":   rating,
        "director": director,
        "actors":   actors,
        "plot":     plot,
        "imdb_id":  imdb_id,
        "genre":    genre,
        "awards":   awards,
    }

    # Real keyboard with msg_id
    real_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Trailer",   url=trailer),
         InlineKeyboardButton("📝 Subtitles", url=subs_url)],
        [InlineKeyboardButton("❤️ Watchlist", callback_data=f"wl_save|{title.replace('|','').replace('\\','')[:40]}|{year}|{rating}"),
         InlineKeyboardButton("🔔 Alert",     callback_data=f"alert_add|{title}|{year}")],
        [InlineKeyboardButton(f"⬇️ {names[0]}", url=urls[0])],
        [InlineKeyboardButton("🌐 All 6 Servers",    callback_data=f"srv_{msg_id}"),
         InlineKeyboardButton("🎯 Similar",          callback_data=f"sim_{msg_id}")],
        [InlineKeyboardButton("🤖 AI Review",        callback_data=f"rev_{imdb_id}"),
         InlineKeyboardButton("💡 Fun Facts",        callback_data=f"fun_{imdb_id}")],
        [InlineKeyboardButton("⭐ Rate Movie",       callback_data=f"rate_{msg_id}"),
         InlineKeyboardButton("🎥 Director Top 5",  callback_data=f"dir_{quote(director, safe='')}")],
        # ✅ NEW ROWS with real msg_id
        [InlineKeyboardButton("📝 Full Review",      callback_data=f"frev_{msg_id}"),
         InlineKeyboardButton("🎭 Mood Match",       callback_data=f"mood_match_{msg_id}")],
        [InlineKeyboardButton("🌟 Cast Analysis",    callback_data=f"cast_{msg_id}"),
         InlineKeyboardButton("❓ Trivia Quiz",      callback_data=f"trivia_{msg_id}")],
        [InlineKeyboardButton("🔥 Full AI Package",  callback_data=f"pkg_{msg_id}")],
    ])
    try:
        await sent.edit_reply_markup(reply_markup=real_keyboard)
    except Exception as e:
        print(f"⚠️ edit_reply_markup failed (msg_id={msg_id}): {e}")

    asyncio.create_task(auto_delete(sent, 7200, user_data=context.user_data, key=msg_id))


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW CALLBACKS — Full Analysis (from movie_finder_groq)
# ═══════════════════════════════════════════════════════════════════

# --- 📝 Full Review ---
async def fullreview_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("📝 Writing full review...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("📝 Full review likh raha hai...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["fullreview"])
    result = await ai_full_review(
        md["title"], md["year"], md.get("genre", "N/A"),
        md["plot"], md["rating"], md["director"],
        md["actors"], md.get("awards", "N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  📝  *FULL AI REVIEW*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text(
            "❌ AI review nahi likh paya.\n_GROQ_API check karo._",
            parse_mode="Markdown"
        )

# --- 🎭 Mood Match ---
async def moodmatch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🎭 Mood match kar raha hai...")
    msg_id = query.data.split("_", 2)[2]   # mood_match_MSGID
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(
        md["title"], md.get("genre", "N/A"), md["plot"]
    )
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Mood match nahi hua. GROQ_API check karo.", parse_mode="Markdown")

# --- 🌟 Cast Analysis ---
async def castanalysis_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🌟 Cast analyze ho raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("🌟 Cast analysis chal raha hai...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["castanalysis"])
    result = await ai_cast_analysis(md["title"], md["actors"], md["director"])
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  🌟  *CAST ANALYSIS*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Cast analysis nahi hua. GROQ_API check karo.", parse_mode="Markdown")

# --- ❓ Trivia Quiz (per movie) ---
async def trivia_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("❓ Trivia question bana raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return
    loader = await query.message.reply_text("❓ Trivia bana raha hai...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["trivia"])
    result = await ai_trivia_quiz_movie(
        md["title"], md["year"], md["director"], md["actors"]
    )
    try: await loader.delete()
    except: pass
    if result:
        await query.message.reply_text(
            f"╔══════════════════════════╗\n║  ❓  *MOVIE TRIVIA*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{md['title']}* ({md['year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Trivia nahi bana. GROQ_API check karo.", parse_mode="Markdown")

# --- 🔥 Full AI Package (sab ek saath) ---
async def fullpackage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer("🔥 Full package prepare ho raha hai...")
    msg_id = query.data.split("_", 1)[1]
    md     = context.user_data.get(msg_id)
    if not md:
        await query.message.reply_text("⚠️ Session expired. Movie dobara search karo.")
        return

    loader = await query.message.reply_text("🔥 Full AI Package loading...\n" + progress_bar(0, 5))
    await animate_generic(loader, FRAMES["fullpackage"])
    try: await loader.delete()
    except: pass

    t  = md["title"];  y  = md["year"]
    g  = md.get("genre","N/A");  p  = md["plot"]
    r  = md["rating"]; d  = md["director"]
    a  = md["actors"]; aw = md.get("awards","N/A")

    sections = [
        ("📝 FULL REVIEW",    ai_full_review(t, y, g, p, r, d, a, aw)),
        ("🎯 SIMILAR MOVIES", ai_similar_deep(t, y, g)),
        ("🎭 MOOD MATCH",     ai_mood_match(t, g, p)),
        ("🌟 CAST ANALYSIS",  ai_cast_analysis(t, a, d)),
        ("❓ TRIVIA QUIZ",    ai_trivia_quiz_movie(t, y, d, a)),
    ]

    # Run all concurrently
    results = await asyncio.gather(*[coro for _, coro in sections], return_exceptions=True)

    full_text = (
        f"╔══════════════════════════╗\n"
        f"║  🔥  *FULL AI PACKAGE*  ║\n"
        f"╚══════════════════════════╝\n\n"
        f"🎬 *{t}* ({y})\n━━━━━━━━━━━━━━━━━━\n"
    )

    for i, (label, _) in enumerate(sections):
        res = results[i]
        full_text += f"\n\n*━━ {label} ━━*\n"
        if isinstance(res, Exception) or not res:
            full_text += "_AI response nahi aaya._"
        else:
            full_text += res
        # Telegram 4096 char limit — send in chunks
        if len(full_text) > 3800:
            await query.message.reply_text(full_text, parse_mode="Markdown")
            full_text = f"🎬 *{t}* — continued...\n"

    full_text += "\n\n_Powered by Groq AI (Llama 3.3)_ 🤖"
    if full_text.strip():
        await query.message.reply_text(full_text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   ✅ NEW COMMANDS — /fullreview /moodmatch /castinfo /trivia
# ═══════════════════════════════════════════════════════════════════
async def fullreview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/fullreview Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/fullreview Movie Name`\nExample: `/fullreview Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("📝 Movie info fetch ho rahi hai...\n" + progress_bar(1, 4))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["fullreview"])
    result = await ai_full_review(
        data.get("Title","N/A"), data.get("Year","N/A"),
        data.get("Genre","N/A"), data.get("Plot","N/A"),
        data.get("imdbRating","N/A"), data.get("Director","N/A"),
        data.get("Actors","N/A"), data.get("Awards","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  📝  *FULL AI REVIEW*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Review nahi likh paya. Try again.", parse_mode="Markdown")

async def moodmatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/moodmatch Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/moodmatch Movie Name`\nExample: `/moodmatch Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🎭 Mood analyze ho raha hai...\n" + progress_bar(1, 4))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["moodmatch"])
    result = await ai_mood_match(
        data.get("Title","N/A"), data.get("Genre","N/A"), data.get("Plot","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════╗\n║  🎭  *MOOD MATCH*  ║\n╚══════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Mood match nahi hua. Try again.", parse_mode="Markdown")

async def castinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/castinfo Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/castinfo Movie Name`\nExample: `/castinfo Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("🌟 Cast analyze ho raha hai...\n" + progress_bar(1, 3))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["castanalysis"])
    result = await ai_cast_analysis(
        data.get("Title","N/A"), data.get("Actors","N/A"), data.get("Director","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  🌟  *CAST ANALYSIS*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Cast info nahi aaya. Try again.", parse_mode="Markdown")

async def trivia_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/trivia Inception"""
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/trivia Movie Name`\nExample: `/trivia Inception`",
            parse_mode="Markdown"
        )
        return
    if not GROQ_API:
        await update.message.reply_text("⚠️ GROQ_API set nahi hai!", parse_mode="Markdown")
        return
    loader = await update.message.reply_text("❓ Trivia bana raha hai...\n" + progress_bar(1, 3))
    data = await asyncio.to_thread(get_omdb, title)
    if not data or data.get("Response") == "False":
        await loader.edit_text(f"❌ *'{title}'* nahi mili!", parse_mode="Markdown")
        return
    await animate_generic(loader, FRAMES["trivia"])
    result = await ai_trivia_quiz_movie(
        data.get("Title","N/A"), data.get("Year","N/A"),
        data.get("Director","N/A"), data.get("Actors","N/A")
    )
    try: await loader.delete()
    except: pass
    if result:
        await update.message.reply_text(
            f"╔══════════════════════════╗\n║  ❓  *MOVIE TRIVIA*  ║\n╚══════════════════════════╝\n\n"
            f"🎬 *{data['Title']}* ({data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{result}\n\n_Powered by Groq AI_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Trivia nahi bana. Try again.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#       MOVIE SEARCH (OMDB)
# ═══════════════════════════════════════════════════════════════════
async def movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("🚫 *You are banned.*", parse_mode="Markdown")
        return
    if is_maintenance() and not is_admin(user.id):
        maint = load_json("maintenance", {"active": False, "message": "🔧 Maintenance..."})
        await update.message.reply_text(
            f"🚧 *CineBot — Maintenance*\n\n{maint.get('message', '')}",
            parse_mode="Markdown"
        )
        return
    title = update.message.text.strip()
    if not title:
        return
    register_user(user)
    log_search(title, user.id)
    add_search_points(user.id)

    loader = await update.message.reply_text(
        f"🔍 *\"{title}\"* search ho raha hai...\n" + progress_bar(1, 6),
        parse_mode="Markdown"
    )
    await animate_search(loader)

    # AI se naam fix karo agar galat ho
    fixed_title = await ai_fix_movie_name(title) or title

    data = await asyncio.to_thread(get_omdb, fixed_title)
    try: await loader.delete()
    except: pass

    if not data or data.get("Response") == "False":
        # Try OMDB search
        results = await asyncio.to_thread(get_omdb_search, fixed_title)
        if results:
            keyboard = [[InlineKeyboardButton(
                f"🎬 {r.get('Title','?')} ({r.get('Year','?')})",
                callback_data=f"pick_{r.get('imdbID','')}"
            )] for r in results[:5]]
            await update.message.reply_text(
                f"🔍 *\"{fixed_title}\"* — multiple results:\n\n_Ek select karo:_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"😕 *\"{title}\"* — koi movie nahi mili.\n\n"
                f"_Spelling check karo ya English mein try karo._",
                parse_mode="Markdown"
            )
        return

    await _send_movie_card(update, context, data, is_search=True)

async def movieinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_maintenance() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🚧 Maintenance mode.")
        return
    if not TMDB_API:
        await update.message.reply_text(
            "⚠️ *TMDB_API not set!*", parse_mode="Markdown"
        )
        return
    title = " ".join(context.args).strip() if context.args else ""
    if not title:
        await update.message.reply_text(
            "❌ *Usage:* `/movieinfo Movie Name`", parse_mode="Markdown"
        )
        return
    await send_movie_card(update, context, title)

# Multi-result pick callback
async def pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer("🎬 Loading...")
    imdb_id = query.data.replace("pick_", "")
    loader  = await query.message.reply_text("🎬 Loading...\n" + progress_bar(2, 6))
    await animate_search(loader)
    data = await asyncio.to_thread(get_omdb, imdb_id, True)
    try: await loader.delete()
    except: pass
    if data and data.get("Response") == "True":
        await _send_movie_card(update, context, data, reply_to=query.message, is_search=True)
    else:
        await query.message.reply_text("❌ Load nahi hua. Try again.")


# ═══════════════════════════════════════════════════════════════════
#         AI REVIEW CALLBACK (original — short review)
# ═══════════════════════════════════════════════════════════════════
async def review_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🤖 Writing review...")
    imdb_id    = query.data.split("_", 1)[1]
    movie_data = await asyncio.to_thread(get_omdb, imdb_id, True)
    if not movie_data or movie_data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    loader = await query.message.reply_text("🤖 Writing AI Review...\n" + progress_bar(0, 4))
    await animate_generic(loader, FRAMES["review"])
    review = await ai_movie_review(
        movie_data.get("Title", "N/A"), movie_data.get("Year", "N/A"),
        movie_data.get("Plot", "N/A"), movie_data.get("imdbRating", "N/A")
    )
    try: await loader.delete()
    except: pass
    if review:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  🤖  *AI REVIEW* ║\n╚══════════════════════╝\n\n"
            f"🎬 *{movie_data['Title']}* ({movie_data['Year']})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{review}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Groq API ne response nahi diya. GROQ_API check karo.")


# ═══════════════════════════════════════════════════════════════════
#         FUN FACTS CALLBACK
# ═══════════════════════════════════════════════════════════════════
async def funfact_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("💡 Finding fun facts...")
    try:
        imdb_id = query.data.split("_", 1)[1]
    except IndexError:
        await query.message.reply_text("⚠️ Error: Movie ID nahi mili.")
        return
    movie_data = await asyncio.to_thread(get_omdb, imdb_id, True)
    if not movie_data or movie_data.get("Response") == "False":
        await query.message.reply_text("❌ Movie details fetch nahi ho payi!")
        return
    loader = await query.message.reply_text("💡 Finding Fun Facts...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["ai"])
    facts = await ai_fun_facts(
        movie_data.get("Title", "N/A"), movie_data.get("Year", "N/A"),
        movie_data.get("Director", "N/A"), movie_data.get("Actors", "N/A")
    )
    try: await loader.delete()
    except: pass
    if facts:
        await query.message.reply_text(
            f"╔══════════════════════╗\n║  💡  *FUN FACTS* ║\n╚══════════════════════╝\n\n"
            f"🎬 *{movie_data.get('Title')}* ({movie_data.get('Year')})\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{facts}\n\n_Powered by Groq AI (Llama 3.3)_ 🤖",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Groq API ne response nahi diya. GROQ_API check karo.")


# ═══════════════════════════════════════════════════════════════════
#         RATE MOVIE CALLBACK
# ═══════════════════════════════════════════════════════════════════
async def rate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    await query.answer()
    msg_id     = query.data.split("_", 1)[1]
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.reply_text("⚠️ Session expired. Search again.")
        return
    title = movie_data["title"]
    keyboard = [
        [InlineKeyboardButton(f"{'⭐' * i}  {i}/5", callback_data=f"dorat_{msg_id}_{i}")]
        for i in range(1, 6)
    ]
    await query.message.reply_text(
        f"⭐ *Rate:* _{title}_\n\n_Apni rating do:_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def dorat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    parts  = query.data.split("_")
    score  = int(parts[-1])
    msg_id = "_".join(parts[1:-1])
    movie_data = context.user_data.get(msg_id)
    if not movie_data:
        await query.message.edit_text("⚠️ Session expired.")
        return
    title   = movie_data["title"]
    uid     = str(query.from_user.id)
    ratings = load_json("ratings")
    if title not in ratings: ratings[title] = {}
    ratings[title][uid] = score
    save_json("ratings", ratings)
    avg = sum(ratings[title].values()) / len(ratings[title])
    await query.message.edit_text(
        f"✅ *Rating saved!*\n\n🎬 *{title}*\n⭐ Your rating: `{score}/5`\n"
        f"👥 Community avg: `{avg:.1f}/5` ({len(ratings[title])} votes)\n\n_Shukriya!_ 🙏",
        parse_mode="Markdown"
    )
    users = load_json("users")
    if uid in users:
        users[uid]["points"] = users[uid].get("points", 0) + 5
        save_json("users", users)


# ═══════════════════════════════════════════════════════════════════
async def director_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer("🎥 Loading director films...")
    from urllib.parse import unquote
    director = unquote(query.data.replace("dir_", ""))
    loader = await query.message.reply_text("🎥 Loading...\n" + progress_bar(0, 3))
    await animate_generic(loader, FRAMES["similar"])
    movies = get_director_movies(director)
    try: await loader.delete()
    except: pass
    if movies:
        text = f"🎥 *Top 5 by {director}:*\n━━━━━━━━━━━━━━━━━━\n\n"
        medals = ["🥇", "🥈", "🥉", "🏅", "🎖"]
        for i, (t, r) in enumerate(movies):
            text += f"{medals[i]} *{t}* — ⭐`{r}`\n"
        text += "\n_Type naam to search_ 🔎"
    else:
        text = f"🎥 *{director}* ki movies:\n\nTMDB API add karo for results."
    await query.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════════════
#   ✅ ADVANCED UPCOMING MOVIES SYSTEM (month/year/genre + cards)
# ═══════════════════════════════════════════════════════════════════

