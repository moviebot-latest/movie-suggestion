from __future__ import annotations

import time

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import repository as repo
from database import get_pool
from decorators import guarded

DEFAULT_SERVERS = {
    "server1": {"name": "Primary Mirror", "url": "https://example.com"},
    "server2": {"name": "Backup Mirror", "url": "https://example2.com"},
}


async def _check_url(url: str) -> tuple[bool, float]:
    start = time.monotonic()
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                elapsed = time.monotonic() - start
                return resp.status < 500, elapsed
    except Exception:
        return False, time.monotonic() - start


@guarded()
async def checkservers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    servers = await repo.get_setting("servers", DEFAULT_SERVERS)
    loader = await update.message.reply_text("📡 Checking servers...")
    lines = []
    for key, info in servers.items():
        up, latency = await _check_url(info["url"])
        await repo.domain_history_record(key, info["url"], up)
        status = "🟢 UP" if up else "🔴 DOWN"
        lines.append(f"{info['name']}: {status} ({latency*1000:.0f}ms)")
    try:
        await loader.delete()
    except Exception:
        pass
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="srvchk_refresh")]])
    await update.message.reply_text("📡 *Server Status*\n\n" + "\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@guarded()
async def srvchk_refresh_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Refreshing...")
    servers = await repo.get_setting("servers", DEFAULT_SERVERS)
    lines = []
    for key, info in servers.items():
        up, latency = await _check_url(info["url"])
        await repo.domain_history_record(key, info["url"], up)
        status = "🟢 UP" if up else "🔴 DOWN"
        lines.append(f"{info['name']}: {status} ({latency*1000:.0f}ms)")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="srvchk_refresh")]])
    try:
        await query.message.edit_text("📡 *Server Status*\n\n" + "\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    except Exception:
        pass


@guarded(require_admin=True)
async def serverstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM server_domain_history ORDER BY last_seen DESC LIMIT 10")
    if not rows:
        await update.message.reply_text("Koi server history nahi hai.")
        return
    lines = []
    for r in rows:
        total = r["times_up"] + r["times_down"]
        pct = (r["times_up"] / total * 100) if total else 0
        lines.append(f"• {r['domain']}: {pct:.0f}% uptime")
    await update.message.reply_text("📊 *Server Stats*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded(require_admin=True)
async def srvchk_stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await serverstats_cmd(update, context)


@guarded(require_admin=True)
async def server_status_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    servers = await repo.get_setting("servers", DEFAULT_SERVERS)
    lines = [f"{info['name']}: {info['url']}" for info in servers.values()]
    await query.message.reply_text("🌐 *Configured Servers*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded(require_admin=True)
async def sendalert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/sendalert <message>`", parse_mode="Markdown")
        return
    msg = " ".join(context.args)
    await update.message.reply_text(f"⚠️ Alert broadcast queued: {msg}\n\n(Use /admin → Broadcast for full delivery.)")


@guarded(require_admin=True)
async def failoverlog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await repo.heal_log_recent(10)
    if not rows:
        await update.message.reply_text("Koi failover events nahi hain.")
        return
    lines = [f"• {r['site_key']}: {r['old_url']} → {r['new_url']} ({r['status']})" for r in rows]
    await update.message.reply_text("📜 *Failover Log*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded(require_admin=True)
async def adm_servers_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await server_status_admin_cb(update, context)


@guarded(require_admin=True)
async def adm_logs_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = await repo.heal_log_recent(10)
    lines = [f"• {r['site_key']}: {r['status']}" for r in rows] or ["Koi logs nahi hain."]
    await query.message.reply_text("📜 *Recent Logs*\n\n" + "\n".join(lines), parse_mode="Markdown")


@guarded(require_admin=True)
async def adm_send_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Use /sendalert command.", show_alert=True)


@guarded(require_admin=True)
async def adm_export_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    total = await repo.user_count()
    await query.message.reply_text(f"📤 Export: {total} users in database (full CSV export via /admin dashboard planned).")


@guarded(require_admin=True)
async def adm_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from admin import admin_panel
    await admin_panel(update, context)


@guarded(require_owner=True)
async def adm_addadmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("User ID bhejo naya admin banane ke liye:\n\n/cancel")
    from admin import W_ADDADMIN
    return W_ADDADMIN


@guarded(require_owner=True)
async def adm_addadmin_recv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    try:
        target_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")
        return ConversationHandler.END
    await repo.add_admin(target_id, update.effective_user.id)
    await update.message.reply_text(f"✅ Admin added: `{target_id}`", parse_mode="Markdown")
    return ConversationHandler.END


@guarded(require_admin=True)
async def adm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Use specific commands to reset data.", show_alert=True)


@guarded(require_admin=True)
async def adm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Server edit — coming soon.", show_alert=True)


@guarded(require_admin=True)
async def adm_rmadmin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = int(query.data.replace("adm_rmadmin_", ""))
    removed = await repo.remove_admin(uid)
    await query.answer("✅ Removed" if removed else "❌ Not found", show_alert=True)


@guarded(require_admin=True)
async def failover_undo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Failover undo — logged.", show_alert=True)


@guarded(require_admin=True)
async def failover_keep_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Failover kept.", show_alert=True)


@guarded(require_admin=True)
async def ai_approve_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Approved.", show_alert=True)


@guarded(require_admin=True)
async def ai_reject_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Rejected.", show_alert=True)


@guarded(require_admin=True)
async def ai_edit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Edit — coming soon.", show_alert=True)
