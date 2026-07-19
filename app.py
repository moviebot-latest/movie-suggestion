from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler,
    CommandHandler, ConversationHandler, InlineQueryHandler,
    MessageHandler, filters,
)

from config import BOT_TOKEN
from database import init_pool, close_pool
from cache import init_cache, close_cache
from background import start_background_tasks

from start import start, help_cmd, start_btn_cb
from search import movie, pick_cb, movieinfo_cmd, random_cmd
from ai_convo import (
    suggest_cmd, suggest_receive, plotsearch_cmd, plotsearch_receive,
    mood_cmd, mood_receive, compare_cmd, compare_recv1, compare_recv2,
    cancel, W_AI_QUERY, W_PLOT_SEARCH, W_MOOD, W_COMPARE_1, W_COMPARE_2,
)
from user_data import (
    watchlist_cmd, wl_save_cb, wl_clear_cb, rate_cb, dorat_cb,
    alerts_cmd, alert_add_cb, alert_del_cb, alert_clear_cb,
    history_cmd, mystats_cmd, leaderboard_cmd, refer_cmd,
)
from admin import (
    admin_panel, adm_stats_cb, adm_listadmins_cb, listadmins_cmd,
    adm_broadcast_prompt, adm_do_broadcast,
    adm_ban_prompt, adm_do_ban, adm_unban_prompt, do_unban_cb,
    adm_maint_toggle, adm_maint_msg, adm_recv_maint_msg,
    addadmin_cmd, removeadmin_cmd,
    groqstatus_cmd, adm_groqstatus_cb, setgroqkey_cmd,
    shutdown_cmd, recover_cmd, adm_shutdown_confirm_cb, adm_shutdown_do_cb, adm_recover_cb,
    W_BROADCAST, W_BAN_USER, W_MAINT_MSG, W_ADDADMIN,
)
from upcoming import (
    upcoming_cmd, upcom_paginate_cb, upcom_ai_cb, upcom_remind_cb,
    upcom_add_cb, upcom_remove_cmd, upcom_pick_cb,
)
from ai_analysis import (
    review_cb, fullreview_cmd, fullreview_cb, moodmatch_cmd, moodmatch_cb,
    castinfo_cmd, castanalysis_cb, trivia_cmd, trivia_cb, funfact_cb,
    fullpackage_cb, similar_cb,
)
from misc import (
    quiz_cmd, quiz_answer_cb, trending_cmd, daily_cmd, clean_cmd,
    back_cb,
)
from lang import (
    lang_cmd, setlang_cb, lang_stats, lang_bulk_reset,
    adminlang_cb, adminpanel_lang_start, lang_cancel_cb,
)
from servers import (
    checkservers_cmd, srvchk_refresh_cb, serverstats_cmd, srvchk_stats_cb,
    server_status_admin_cb, sendalert_cmd, failoverlog_cmd,
    adm_servers_cb, adm_logs_cb, adm_send_alerts, adm_export_cb, adm_back,
    adm_addadmin_cb, adm_addadmin_recv, adm_reset, adm_edit, adm_rmadmin_cb,
    failover_undo_cb, failover_keep_cb, ai_approve_cb, ai_reject_cb, ai_edit_cb,
)
from inline import inline_query_handler

log = logging.getLogger("cinebot.app")


async def post_init(application: Application):
    await init_pool()
    await init_cache()
    await start_background_tasks(application)
    log.info("✅ post_init complete — DB pool, cache, and background tasks ready")


async def post_shutdown(application: Application):
    await close_pool()
    await close_cache()
    log.info("Shutdown complete")


def build_application() -> Application:
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ── Master conversation handler (AI features + admin flows) ────
    master_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(adm_edit,             pattern="^adm_edit_s"),
            CallbackQueryHandler(adm_maint_msg,        pattern="^adm_maint_msg$"),
            CallbackQueryHandler(adm_broadcast_prompt, pattern="^adm_broadcast$"),
            CallbackQueryHandler(adm_ban_prompt,       pattern="^adm_ban$"),
            CallbackQueryHandler(adm_addadmin_cb,      pattern="^adm_addadmin$"),
            CallbackQueryHandler(suggest_cmd,          pattern="^cmd_suggest$"),
            CallbackQueryHandler(plotsearch_cmd,       pattern="^cmd_plotsearch$"),
            CallbackQueryHandler(mood_cmd,              pattern="^cmd_mood$"),
            CallbackQueryHandler(compare_cmd,           pattern="^cmd_compare$"),
            CommandHandler("suggest",    suggest_cmd),
            CommandHandler("plotsearch", plotsearch_cmd),
            CommandHandler("mood",       mood_cmd),
            CommandHandler("compare",    compare_cmd),
        ],
        states={
            W_AI_QUERY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, suggest_receive)],
            W_PLOT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, plotsearch_receive)],
            W_MOOD:        [MessageHandler(filters.TEXT & ~filters.COMMAND, mood_receive)],
            W_COMPARE_1:   [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_recv1)],
            W_COMPARE_2:   [MessageHandler(filters.TEXT & ~filters.COMMAND, compare_recv2)],
            W_BROADCAST:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_broadcast)],
            W_BAN_USER:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_do_ban)],
            W_MAINT_MSG:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_maint_msg)],
            W_ADDADMIN:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_addadmin_recv)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="master_conv",
        persistent=False,
    )

    # ── Commands ─────────────────────────────────────────────────
    application.add_handler(CommandHandler("start",        start))
    application.add_handler(CommandHandler("help",         help_cmd))
    application.add_handler(CommandHandler("trending",     trending_cmd))
    application.add_handler(CommandHandler("random",       random_cmd))
    application.add_handler(CommandHandler("daily",        daily_cmd))
    application.add_handler(CommandHandler("upcoming",     upcoming_cmd))
    application.add_handler(CommandHandler("upcom_remove", upcom_remove_cmd))
    application.add_handler(CommandHandler("watchlist",    watchlist_cmd))
    application.add_handler(CommandHandler("alerts",       alerts_cmd))
    application.add_handler(CommandHandler("quiz",         quiz_cmd))
    application.add_handler(CommandHandler("refer",        refer_cmd))
    application.add_handler(CommandHandler("lang",         lang_cmd))
    application.add_handler(CommandHandler("langstats",    lang_stats))
    application.add_handler(CommandHandler("langreset",    lang_bulk_reset))
    application.add_handler(CommandHandler("mystats",      mystats_cmd))
    application.add_handler(CommandHandler("admin",        admin_panel))
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
    application.add_handler(CommandHandler(["checkservers", "checkserver"], checkservers_cmd))
    application.add_handler(CommandHandler("serverstats",  serverstats_cmd))
    application.add_handler(CommandHandler("sendalert",    sendalert_cmd))
    application.add_handler(CommandHandler("failoverlog",  failoverlog_cmd))
    application.add_handler(CommandHandler("groqstatus",   groqstatus_cmd))
    application.add_handler(CommandHandler("setgroqkey",   setgroqkey_cmd))
    application.add_handler(CommandHandler("shutdown",     shutdown_cmd))
    application.add_handler(CommandHandler("recover",      recover_cmd))

    # ── Admin callbacks ──────────────────────────────────────────
    application.add_handler(CallbackQueryHandler(adm_servers_cb,    pattern="^adm_servers$"))
    application.add_handler(CallbackQueryHandler(adm_maint_toggle,  pattern="^adm_maint_toggle$"))
    application.add_handler(CallbackQueryHandler(adm_reset,         pattern="^adm_reset$"))
    application.add_handler(CallbackQueryHandler(adm_stats_cb,      pattern="^adm_stats$"))
    application.add_handler(CallbackQueryHandler(adm_back,          pattern="^adm_back$"))
    application.add_handler(CallbackQueryHandler(adm_logs_cb,       pattern="^adm_logs$"))
    application.add_handler(CallbackQueryHandler(adm_send_alerts,   pattern="^adm_send_alerts$"))
    application.add_handler(CallbackQueryHandler(adm_unban_prompt,  pattern="^adm_unban$"))
    application.add_handler(CallbackQueryHandler(do_unban_cb,       pattern="^dounban_"))
    application.add_handler(CallbackQueryHandler(adm_export_cb,     pattern="^adm_export$"))
    application.add_handler(CallbackQueryHandler(adm_listadmins_cb, pattern="^adm_listadmins$"))
    application.add_handler(CallbackQueryHandler(adm_rmadmin_cb,    pattern="^adm_rmadmin_"))
    application.add_handler(CallbackQueryHandler(adm_groqstatus_cb,      pattern="^adm_groqstatus$"))
    application.add_handler(CallbackQueryHandler(adm_shutdown_confirm_cb, pattern="^adm_shutdown_confirm$"))
    application.add_handler(CallbackQueryHandler(adm_shutdown_do_cb,      pattern="^adm_shutdown_do$"))
    application.add_handler(CallbackQueryHandler(adm_recover_cb,          pattern="^adm_recover$"))

    # ── Server checker callbacks ─────────────────────────────────
    application.add_handler(CallbackQueryHandler(srvchk_refresh_cb,      pattern="^srvchk_refresh$"))
    application.add_handler(CallbackQueryHandler(srvchk_stats_cb,        pattern="^srvchk_stats$"))
    application.add_handler(CallbackQueryHandler(server_status_admin_cb, pattern="^adm_srv_status$"))

    # ── Failover / AI approval callbacks ─────────────────────────
    application.add_handler(CallbackQueryHandler(failover_undo_cb, pattern="^failover_undo_"))
    application.add_handler(CallbackQueryHandler(failover_keep_cb, pattern="^failover_keep_"))
    application.add_handler(CallbackQueryHandler(ai_approve_cb, pattern="^ai_approve:"))
    application.add_handler(CallbackQueryHandler(ai_reject_cb,  pattern="^ai_reject:"))
    application.add_handler(CallbackQueryHandler(ai_edit_cb,    pattern="^ai_edit:"))

    # ── Full AI analysis callbacks ────────────────────────────────
    application.add_handler(CallbackQueryHandler(fullreview_cb,   pattern="^frev_"))
    application.add_handler(CallbackQueryHandler(moodmatch_cb,    pattern="^mood_match_"))
    application.add_handler(CallbackQueryHandler(castanalysis_cb, pattern="^cast_"))
    application.add_handler(CallbackQueryHandler(trivia_cb,       pattern="^trivia_"))
    application.add_handler(CallbackQueryHandler(fullpackage_cb,  pattern="^pkg_"))

    # ── Upcoming callbacks ────────────────────────────────────────
    application.add_handler(CallbackQueryHandler(upcom_paginate_cb, pattern="^upcom_(prev|next|noop)$"))
    application.add_handler(CallbackQueryHandler(upcom_ai_cb,       pattern="^upcom_ai_"))
    application.add_handler(CallbackQueryHandler(upcom_remind_cb,   pattern="^upcom_rm_"))
    application.add_handler(CallbackQueryHandler(upcom_add_cb,      pattern="^upcom_add_"))
    application.add_handler(CallbackQueryHandler(upcom_pick_cb,     pattern="^upcom_pick_"))

    # ── Lang callbacks ────────────────────────────────────────────
    application.add_handler(CallbackQueryHandler(setlang_cb,            pattern="^setlang_"))
    application.add_handler(CallbackQueryHandler(adminlang_cb,          pattern="^adminlang_"))
    application.add_handler(CallbackQueryHandler(adminpanel_lang_start, pattern="^adminpanel_lang$"))
    application.add_handler(CallbackQueryHandler(lang_cancel_cb,        pattern="^lang_cancel$"))

    # ── Master conversation (must come before the generic cmd_* catch-all) ──
    application.add_handler(master_conv)

    # ── Generic main-menu buttons ─────────────────────────────────
    application.add_handler(CallbackQueryHandler(start_btn_cb, pattern="^cmd_(?!suggest|plotsearch|mood|compare)"))
    application.add_handler(CallbackQueryHandler(start_btn_cb, pattern="^open_admin$"))

    # ── User callbacks ────────────────────────────────────────────
    application.add_handler(CallbackQueryHandler(wl_save_cb,     pattern=r"^wl_save\|"))
    application.add_handler(CallbackQueryHandler(wl_clear_cb,    pattern="^wl_clear$"))
    application.add_handler(CallbackQueryHandler(alert_add_cb,   pattern=r"^alert_add\|"))
    application.add_handler(CallbackQueryHandler(alert_del_cb,   pattern=r"^alert_del\|"))
    application.add_handler(CallbackQueryHandler(alert_clear_cb, pattern="^alert_clear$"))
    application.add_handler(CallbackQueryHandler(similar_cb,     pattern="^sim_"))
    application.add_handler(CallbackQueryHandler(back_cb,        pattern="^bk_"))
    application.add_handler(CallbackQueryHandler(quiz_answer_cb, pattern="^quiz_ans_"))
    application.add_handler(CallbackQueryHandler(pick_cb,        pattern="^pick_"))
    application.add_handler(CallbackQueryHandler(review_cb,      pattern="^rev_"))
    application.add_handler(CallbackQueryHandler(funfact_cb,     pattern="^fun_"))
    application.add_handler(CallbackQueryHandler(rate_cb,        pattern="^rate_"))
    application.add_handler(CallbackQueryHandler(dorat_cb,       pattern="^dorat_"))

    # ── Inline mode ────────────────────────────────────────────────
    application.add_handler(InlineQueryHandler(inline_query_handler))

    # ── Movie search — LAST ──────────────────────────────────────
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, movie))

    return application
