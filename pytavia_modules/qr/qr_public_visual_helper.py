"""
Shared helper for public QR visual procs. No base class — each type proc is standalone.
"""
import ast


def _parse_contact_item(item, value_key, label_key="label"):
    """
    Coerce a contact list item into a proper dict.
    Handles three legacy storage formats:
      1. Already a dict                → return as-is
      2. String repr of a dict        → parse with ast.literal_eval
      3. Plain string (the value)     → wrap in {label_key:"", value_key: item}
    """
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        s = item.strip()
        if s.startswith("{"):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        # plain string — treat as the raw value
        return {label_key: "", value_key: s}
    return None


def normalize_ecard_contact_lists(qrcard):
    """
    Fix legacy data where E-card_phones/emails/websites were stored as:
    - a single string instead of a list
    - a list of stringified dicts ("{'label':...}")
    Returns a new dict with normalized lists.
    """
    result = dict(qrcard)

    phone_raw = result.get("E-card_phones") or []
    if isinstance(phone_raw, str):
        phone_raw = [phone_raw] if phone_raw.strip() else []
    phones = []
    for item in phone_raw:
        coerced = _parse_contact_item(item, value_key="number")
        if coerced and (coerced.get("number") or "").strip():
            phones.append(coerced)
    result["E-card_phones"] = phones

    email_raw = result.get("E-card_emails") or []
    if isinstance(email_raw, str):
        email_raw = [email_raw] if email_raw.strip() else []
    emails = []
    for item in email_raw:
        coerced = _parse_contact_item(item, value_key="value")
        if coerced and (coerced.get("value") or "").strip():
            emails.append(coerced)
    result["E-card_emails"] = emails

    website_raw = result.get("E-card_websites") or []
    if isinstance(website_raw, str):
        website_raw = [website_raw] if website_raw.strip() else []
    websites = []
    for item in website_raw:
        coerced = _parse_contact_item(item, value_key="value")
        if coerced and (coerced.get("value") or "").strip():
            websites.append(coerced)
    result["E-card_websites"] = websites

    return result


def enforce_scan_limit_and_increment(qrcard, mgdDB, webapp):
    """
    Return qrcard if scan is allowed; otherwise return None when:
    - no qrcard
    - outside schedule window
    - scan limit reached
    Increments stats.scan_count in db_qrcard.
    """
    if not qrcard:
        return None
    try:
        now_ts = int(__import__("time").time())
        fk_user_id = qrcard.get("fk_user_id")
        if fk_user_id:
            mgdDB.db_user_subscription.update_many(
                {"fk_user_id": fk_user_id, "status": "ACTIVE", "expires_at": {"$lt": now_ts, "$gt": 0}},
                {"$set": {"status": "EXPIRED"}},
            )
            active_subs = list(mgdDB.db_user_subscription.find(
                {"fk_user_id": fk_user_id, "status": "ACTIVE", "is_deleted": {"$ne": True}, "expires_at": {"$gt": now_ts}},
                {"_id": 0, "max_qr": 1},
            ))
            total_max_qr = sum(int(s.get("max_qr", 0) or 0) for s in active_subs)
            allowed_ids = set()
            if total_max_qr > 0:
                idx_docs = list(mgdDB.db_qr_index.find(
                    {"fk_user_id": fk_user_id, "status": {"$in": ["ACTIVE", "INACTIVE"]}},
                    {"_id": 0, "qrcard_id": 1, "timestamp": 1},
                ).sort("timestamp", -1).limit(total_max_qr))
                allowed_ids = set(d.get("qrcard_id") for d in idx_docs if d.get("qrcard_id"))
            if qrcard.get("qrcard_id") not in allowed_ids:
                set_op = {"$set": {"status": "INACTIVE"}}
                mgdDB.db_qr_index.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard.get("qrcard_id")},
                    set_op,
                )
                mgdDB.db_qrcard.update_one(
                    {"fk_user_id": fk_user_id, "qrcard_id": qrcard.get("qrcard_id")},
                    set_op,
                )
                qr_type = qrcard.get("qr_type", "")
                type_col_map = {
                    "pdf": "db_qrcard_pdf",
                    "web-static": "db_qrcard_web_static",
                    "text": "db_qrcard_text",
                    "wa-static": "db_qrcard_wa_static",
                    "email-static": "db_qrcard_email_static",
                    "vcard-static": "db_qrcard_vcard_static",
                    "allinone": "db_qrcard_allinone",
                    "images": "db_qrcard_images",
                    "video": "db_qrcard_video",
                    "special": "db_qrcard_special",
                }
                col_name = type_col_map.get(qr_type)
                if col_name:
                    getattr(mgdDB, col_name).update_one(
                        {"fk_user_id": fk_user_id, "qrcard_id": qrcard.get("qrcard_id")},
                        set_op,
                    )
                return None
    except Exception:
        if webapp:
            webapp.logger.debug("public quota sync failed", exc_info=True)
    # Schedule enforcement
    if qrcard.get("schedule_enabled"):
        from datetime import date
        today = date.today()
        since = (qrcard.get("schedule_since") or "").strip()
        until = (qrcard.get("schedule_until") or "").strip()
        try:
            if since and today < date.fromisoformat(since):
                return None
        except ValueError:
            pass
        try:
            if until and today > date.fromisoformat(until):
                return None
        except ValueError:
            pass
    stats = qrcard.get("stats") or {}
    current_scans = int(stats.get("scan_count", 0) or 0)
    limit_enabled = bool(qrcard.get("scan_limit_enabled"))
    limit_value = int(qrcard.get("scan_limit_value", 0) or 0)
    if limit_enabled and limit_value > 0 and current_scans >= limit_value:
        return None
    try:
        mgdDB.db_qrcard.update_one(
            {
                "fk_user_id": qrcard.get("fk_user_id"),
                "qrcard_id": qrcard.get("qrcard_id"),
                "status": "ACTIVE",
            },
            {"$inc": {"stats.scan_count": 1}},
        )
    except Exception:
        if webapp:
            webapp.logger.debug("enforce_scan_limit_and_increment failed", exc_info=True)
    return qrcard
