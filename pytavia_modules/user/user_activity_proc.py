"""User activity logging — records QR create/delete events."""
import time
import uuid
import traceback
from datetime import datetime

from pytavia_core import database, config


class user_activity_proc:

    def __init__(self, app=None):
        self.webapp = app

    # ── public helpers ──────────────────────────────────────────────────────

    def log(self, fk_user_id, action, qrcard_id="", qr_name="", qr_type="",
            source="", detail=None):
        """
        Write one activity record.

        action  : CREATE_QR | DELETE_QR | DELETE_QR_ASSETS
        source  : my_qr_codes | storage | bulk
        detail  : dict with any extra data (freed_bytes, deleted_count, …)
        """
        try:
            mgdDB = database.get_db_conn(config.mainDB)
            now = time.time()
            doc = {
                "log_id"     : uuid.uuid4().hex,
                "fk_user_id" : fk_user_id,
                "action"     : action,
                "qrcard_id"  : qrcard_id,
                "qr_name"    : qr_name,
                "qr_type"    : qr_type,
                "source"     : source,
                "detail"     : detail or {},
                "created_at" : datetime.utcfromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "timestamp"  : now,
            }
            mgdDB.db_user_activity_log.insert_one(doc)
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())

    def get_logs(self, fk_user_id, page=1, per_page=20):
        """Return paginated activity logs for a user, newest first."""
        try:
            mgdDB = database.get_db_conn(config.mainDB)
            skip  = (page - 1) * per_page
            total = mgdDB.db_user_activity_log.count_documents({"fk_user_id": fk_user_id})
            logs  = list(
                mgdDB.db_user_activity_log
                .find({"fk_user_id": fk_user_id})
                .sort("timestamp", -1)
                .skip(skip)
                .limit(per_page)
            )
            return {"logs": logs, "total": total, "page": page, "per_page": per_page}
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"logs": [], "total": 0, "page": page, "per_page": per_page}
