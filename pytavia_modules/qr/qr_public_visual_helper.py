"""
Shared helper for public QR visual procs. No base class — each type proc is standalone.
"""
import ast
from flask import abort


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
    Return qrcard if scan is allowed; abort(404) if no qrcard or scan limit reached.
    Increments stats.scan_count in db_qrcard.
    """
    if not qrcard:
        abort(404)
    stats = qrcard.get("stats") or {}
    current_scans = int(stats.get("scan_count", 0) or 0)
    limit_enabled = bool(qrcard.get("scan_limit_enabled"))
    limit_value = int(qrcard.get("scan_limit_value", 0) or 0)
    if limit_enabled and limit_value > 0 and current_scans >= limit_value:
        abort(404)
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
