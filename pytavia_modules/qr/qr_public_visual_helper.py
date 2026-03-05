"""
Shared helper for public QR visual procs. No base class — each type proc is standalone.
"""
from flask import abort


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
