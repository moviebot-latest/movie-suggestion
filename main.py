# ╔══════════════════════════════════════════════════════════════════╗
# ║  main.py — Bot startup & handler registration                  ║
# ║  Normally is file ko change karne ki zaroorat nahi             ║
# ╚══════════════════════════════════════════════════════════════════╝

import asyncio, threading, os
from flask import Flask
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                           CallbackQueryHandler, filters, ConversationHandler)
from config import TOKEN, ADMIN_ID
from config import (W_URL, W_NAME, W_MAINT_MSG, W_BROADCAST, W_BAN_USER,
                    W_AI_QUERY, W_PLOT_SEARCH, W_MOOD, W_COMPARE_1, W_COMPARE_2,
                    W_ADDADMIN)

from server_checker  import (auto_server_checker, checkservers_cmd, serverstats_cmd,
                              srvchk_refresh_cb, srvchk_stats_cb, server_status_admin_cb,
                              servers_cb, back_cb)
from movie_search    import (start, start_btn_cb, movie, movieinfo_cmd,
                              fullreview_cmd, fullreview_cb, moodmatch_cmd, moodmatch_cb,
                              castinfo_cmd, castanalysis_cb, trivia_cmd, trivia_cb,
                              fullpackage_cb, review_cb, funfact_cb, rate_cb, dorat_cb,
                              pick_cb, director_cb)
from upcoming        import (upcoming_cmd, upcom_remove_cmd, upcom_paginate_cb,
                              upcom_ai_cb, upcom_remind_cb, upcom_add_cb)
from discovery       import trending_cmd, random_cmd, daily_cmd
from cmd_watchlist   import (watchlist_cmd, wl_save_cb, wl_clear_cb,
                              alerts_cmd, alert_add_cb, alert_del_cb, alert_clear_cb)
from social          import leaderboard_cmd, history_cmd, refer_cmd, mystats_cmd
from ai_features     import (suggest_cmd, suggest_receive, plotsearch_cmd, plotsearch_receive,
                              mood_cmd, mood_receive, compare_cmd, compare_recv1, compare_recv2)
from games           import (quiz_cmd, quiz_answer_cb, quiz_diff_cb,
                              daily_challenge_cmd, dc_answer_cb, dc_leaderboard_cmd,
                              actor_connect_cmd, ac_random_cb,
                              lang_cmd, setlang_cb,
                              similar_cmd, similar_cb,
                              sim_genre_cb, sim_vibe_cb, sim_restart_cb)
from admin           import (admin_panel, clean_cmd, addadmin_cmd, adm_addadmin_cb,
                              adm_addadmin_recv, removeadmin_cmd, listadmins_cmd,
                              adm_edit, adm_recv_url, adm_recv_name, adm_maint_msg,
                              adm_recv_maint_msg, adm_broadcast_prompt, adm_do_broadcast,
                              adm_ban_prompt, adm_do_ban, adm_back, adm_reset,
                              adm_maint_toggle, adm_stats_cb, adm_logs_cb, adm_send_alerts, sendalert_cmd,
                              adm_unban_prompt, do_unban_cb, adm_export_cb,
                              adm_listadmins_cb, adm_rmadmin_cb, adm_servers_cb,
                              cancel, help_cmd)

web_app = Flask(__name__)
@web_app.route("/")
def home(): return "CineBot v10 Modular"
@web_app.route("/health")
def health(): return {"status": "ok"}
def run_web(): web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
threading.Thread(target=run_web, daemon=True).start()

async def post_init(application):
    asyncio.create_task(auto_server_checker(application.bot, ADMIN_ID))

application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

master_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(adm_edit,             pattern="^adm_edit_s"),
        CallbackQueryHandler(adm_maint_msg,        pattern="^adm_maint_msg$"),
        CallbackQueryHandler(adm_broadcast_prompt, pattern="^adm_broadcast$"),
        CallbackQueryHandler(adm_ban_prompt,       pattern="^adm_ban$"),
        CallbackQueryHandler(adm_addadmin_cb,      pattern="^adm_addadmin$"),
        CallbackQueryHandler(suggest_cmd,          pattern="^cmd_suggest$"),
        CallbackQueryHandler(plotsearch_cmd,       pattern="^cmd_plotsearch$"),
        CallbackQueryHandler(mood_cmd,             pattern="^cmd_mood$"),
        CallbackQueryHandler(compare_cmd,          pattern="^cmd_compare$"),
        CommandHandler("suggest",    suggest_cmd),
        CommandHandler("plotsearch", plotsearch_cmd),
        CommandHandler("mood",       mood_cmd),
        CommandHandler("compare",    compare_cmd),
    ],
    states={
        W_URL:         [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_url)],
        W_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_name)],
        W_MAINT_MSG:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_maint_msg)],
        W_BROADCAST:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_broadcast)],
        W_BAN_USER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_ban)],
        W_AI_QUERY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, suggest_receive)],
        W_PLOT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, plotsearch_receive)],
        W_MOOD:        [MessageHandler(filters.TEXT & ~filters.COMMAND, mood_receive)],
        W_COMPARE_1:   [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_recv1)],
        W_COMPARE_2:   [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_recv2)],
        W_ADDADMIN:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_addadmin_recv)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

application.add_handler(CommandHandler("start",        start))
application.add_handler(CommandHandler("help",         help_cmd))
application.add_handler(CommandHandler("trending",     trending_cmd))
application.add_handler(CommandHandler("random",       random_cmd))
application.add_handler(CommandHandler("daily",        daily_cmd))
application.add_handler(CommandHandler("upcoming",     upcoming_cmd))
application.add_handler(CommandHandler("upcom_remove", upcom_remove_cmd))
application.add_handler(CommandHandler("watchlist",    watchlist_cmd))
application.add_handler(CommandHandler("alerts",       alerts_cmd))
application.add_handler(CommandHandler("quiz",            quiz_cmd))
application.add_handler(CommandHandler("daily_challenge", daily_challenge_cmd))
application.add_handler(CommandHandler("dc_leaderboard",  dc_leaderboard_cmd))
application.add_handler(CommandHandler("actorconnect",    actor_connect_cmd))
application.add_handler(CommandHandler("similar",         similar_cmd))
application.add_handler(CommandHandler("refer",        refer_cmd))
application.add_handler(CommandHandler("lang",         lang_cmd))
application.add_handler(CommandHandler("mystats",      mystats_cmd))
application.add_handler(CommandHandler("admin",        admin_panel))
application.add_handler(CommandHandler("sendalert",    sendalert_cmd))
application.add_handler(CommandHandler("clean",        clean_cmd))
application.add_handler(CommandHandler("leaderboard",  leaderboard_cmd))
application.add_handler(CommandHandler("history",      history_cmd))
application.add_handler(CommandHandler("movieinfo",    movieinfo_cmd))
application.add_handler(CommandHandler("addadmin",     addadmin_cmd))
application.add_handler(CommandHandler("removeadmin",  removeadmin_cmd))
application.add_handler(CommandHandler("admins",       listadmins_cmd))
application.add_handler(CommandHandler("fullreview",   fullreview_cmd))
application.add_handler(CommandHandler("moodmatch",    moodmatch_cmd))
application.add_handler(CommandHandler("castinfo",     castinfo_cmd))
application.add_handler(CommandHandler("trivia",       trivia_cmd))
application.add_handler(CommandHandler(["checkservers","checkserver"], checkservers_cmd))
application.add_handler(CommandHandler("serverstats",  serverstats_cmd))
application.add_handler(CallbackQueryHandler(adm_servers_cb,         pattern="^adm_servers$"))
application.add_handler(CallbackQueryHandler(adm_maint_toggle,       pattern="^adm_maint_toggle$"))
application.add_handler(CallbackQueryHandler(adm_reset,              pattern="^adm_reset$"))
application.add_handler(CallbackQueryHandler(adm_stats_cb,           pattern="^adm_stats$"))
application.add_handler(CallbackQueryHandler(adm_back,               pattern="^adm_back$"))
application.add_handler(CallbackQueryHandler(adm_logs_cb,            pattern="^adm_logs$"))
application.add_handler(CallbackQueryHandler(adm_send_alerts,        pattern="^adm_send_alerts$"))
application.add_handler(CallbackQueryHandler(adm_unban_prompt,       pattern="^adm_unban$"))
application.add_handler(CallbackQueryHandler(do_unban_cb,            pattern="^dounban_"))
application.add_handler(CallbackQueryHandler(adm_export_cb,          pattern="^adm_export$"))
application.add_handler(CallbackQueryHandler(adm_listadmins_cb,      pattern="^adm_listadmins$"))
application.add_handler(CallbackQueryHandler(adm_rmadmin_cb,         pattern="^adm_rmadmin_"))
application.add_handler(CallbackQueryHandler(srvchk_refresh_cb,      pattern="^srvchk_refresh$"))
application.add_handler(CallbackQueryHandler(srvchk_stats_cb,        pattern="^srvchk_stats$"))
application.add_handler(CallbackQueryHandler(server_status_admin_cb, pattern="^adm_srv_status$"))
application.add_handler(CallbackQueryHandler(fullreview_cb,          pattern="^frev_"))
application.add_handler(CallbackQueryHandler(moodmatch_cb,           pattern="^mood_match_"))
application.add_handler(CallbackQueryHandler(castanalysis_cb,        pattern="^cast_"))
application.add_handler(CallbackQueryHandler(trivia_cb,              pattern="^trivia_"))
application.add_handler(CallbackQueryHandler(fullpackage_cb,         pattern="^pkg_"))
application.add_handler(CallbackQueryHandler(upcom_paginate_cb,      pattern="^upcom_(prev|next|noop)$"))
application.add_handler(CallbackQueryHandler(upcom_ai_cb,            pattern="^upcom_ai_"))
application.add_handler(CallbackQueryHandler(upcom_remind_cb,        pattern="^upcom_rm_"))
application.add_handler(CallbackQueryHandler(upcom_add_cb,           pattern="^upcom_add_"))
application.add_handler(master_conv)
application.add_handler(CallbackQueryHandler(start_btn_cb,   pattern="^cmd_(?!suggest|plotsearch|mood|compare)"))
application.add_handler(CallbackQueryHandler(start_btn_cb,   pattern="^open_admin$"))
application.add_handler(CallbackQueryHandler(wl_save_cb,     pattern="^wl_save\\|"))
application.add_handler(CallbackQueryHandler(wl_clear_cb,    pattern="^wl_clear$"))
application.add_handler(CallbackQueryHandler(alert_add_cb,   pattern="^alert_add\\|"))
application.add_handler(CallbackQueryHandler(alert_del_cb,   pattern="^alert_del\\|"))
application.add_handler(CallbackQueryHandler(alert_clear_cb, pattern="^alert_clear$"))
application.add_handler(CallbackQueryHandler(servers_cb,     pattern="^srv_"))
application.add_handler(CallbackQueryHandler(back_cb,        pattern="^bk_"))
application.add_handler(CallbackQueryHandler(director_cb,    pattern="^dir_"))
application.add_handler(CallbackQueryHandler(quiz_answer_cb,  pattern="^quiz_ans_"))
application.add_handler(CallbackQueryHandler(quiz_diff_cb,    pattern="^quiz_diff_"))
application.add_handler(CallbackQueryHandler(dc_answer_cb,    pattern="^dc_ans_"))
application.add_handler(CallbackQueryHandler(ac_random_cb,    pattern="^ac_random$"))
application.add_handler(CallbackQueryHandler(similar_cb,      pattern="^similar_(?!g_|v_|restart_)"))
application.add_handler(CallbackQueryHandler(sim_genre_cb,    pattern="^sim_g_"))
application.add_handler(CallbackQueryHandler(sim_vibe_cb,     pattern="^sim_v_"))
application.add_handler(CallbackQueryHandler(sim_restart_cb,  pattern="^sim_restart_"))
application.add_handler(CallbackQueryHandler(setlang_cb,      pattern="^setlang_"))
application.add_handler(CallbackQueryHandler(pick_cb,        pattern="^pick_"))
application.add_handler(CallbackQueryHandler(review_cb,      pattern="^rev_"))
application.add_handler(CallbackQueryHandler(funfact_cb,     pattern="^fun_"))
application.add_handler(CallbackQueryHandler(rate_cb,        pattern="^rate_"))
application.add_handler(CallbackQueryHandler(dorat_cb,       pattern="^dorat_"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie))

print("✅ CineBot v10 Modular started!")
application.run_polling()
