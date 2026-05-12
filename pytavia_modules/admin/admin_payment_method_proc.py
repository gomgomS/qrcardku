"""Processor for admin-managed payment methods (categories + methods)."""

import os
import sys
import json
import time
import uuid
import traceback
import datetime

sys.path.append("pytavia_core")
sys.path.append("pytavia_modules")
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib")
sys.path.append("pytavia_modules/storage")

from pytavia_core import database, config
from storage import r2_storage_proc as r2_mod

ALLOWED_ICON_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_ICON_SIZE = 2 * 1024 * 1024  # 2 MB


class admin_payment_method_proc:

    mgdDB = database.get_db_conn(config.mainDB)

    def __init__(self, app):
        self.webapp = app

    # ── Seed from JSON ──────────────────────────────────────────────────────

    def seed_from_json(self, root_path):
        """One-time migration: read payment-methods.json into DB collections.
        Returns dict with counts."""
        try:
            if self.mgdDB.db_payment_category.count_documents({}) > 0:
                return {"ok": True, "message": "Already seeded, skipping."}

            json_path = os.path.join(root_path, "static", "json_file", "payment-methods.json")
            if not os.path.exists(json_path):
                return {"ok": False, "error": "payment-methods.json not found"}

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            now_ts = int(time.time() * 1000)
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cat_count = 0
            method_count = 0

            for cat_idx, cat in enumerate(data):
                cat_id = uuid.uuid4().hex
                self.mgdDB.db_payment_category.insert_one({
                    "category_id": cat_id,
                    "name": cat.get("name", ""),
                    "order": cat_idx,
                    "status": "ACTIVE",
                    "created_at": now_str,
                    "timestamp": now_ts,
                })
                cat_count += 1

                for m_idx, pay in enumerate(cat.get("payments", [])):
                    merchants = pay.get("merchants") or []
                    primary = merchants[0] if merchants else {}
                    method_id = uuid.uuid4().hex
                    self.mgdDB.db_payment_method.insert_one({
                        "method_id": method_id,
                        "fk_category_id": cat_id,
                        "merchant_id": primary.get("id", ""),
                        "merchant_name": primary.get("name", ""),
                        "icon_url": primary.get("icon", ""),
                        "fee": pay.get("fee", ""),
                        "order": m_idx,
                        "status": "ACTIVE",
                        "created_at": now_str,
                        "timestamp": now_ts,
                    })
                    method_count += 1

            return {"ok": True, "categories": cat_count, "methods": method_count}

        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Seed failed."}

    # ── Read ────────────────────────────────────────────────────────────────

    def get_all_categories_with_methods(self):
        """Return all non-deleted categories with their methods, sorted by order."""
        try:
            cats = list(
                self.mgdDB.db_payment_category
                    .find({"status": {"$ne": "DELETED"}})
                    .sort("order", 1)
            )
            for cat in cats:
                cat["methods"] = list(
                    self.mgdDB.db_payment_method
                        .find({
                            "fk_category_id": cat["category_id"],
                            "status": {"$ne": "DELETED"},
                        })
                        .sort("order", 1)
                )
            return cats
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return []

    def get_active_categories_for_checkout(self):
        """Return ACTIVE categories+methods in the same shape as payment-methods.json."""
        try:
            cats = list(
                self.mgdDB.db_payment_category
                    .find({"status": "ACTIVE"})
                    .sort("order", 1)
            )
            out = []
            for cat in cats:
                methods = list(
                    self.mgdDB.db_payment_method
                        .find({
                            "fk_category_id": cat["category_id"],
                            "status": "ACTIVE",
                        })
                        .sort("order", 1)
                )
                payments = []
                for m in methods:
                    payments.append({
                        "merchants": [{
                            "id": m["merchant_id"],
                            "name": m["merchant_name"],
                            "icon": m["icon_url"],
                        }],
                        "fee": m["fee"],
                        "free_admin_fee": bool(m.get("free_admin_fee")),
                    })
                out.append({"name": cat["name"], "payments": payments})
            return out
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return []

    # ── Category CRUD ───────────────────────────────────────────────────────

    def save_category(self, data):
        """Create or update a payment category. data: {category_id?, name, status?}"""
        try:
            cat_id = str(data.get("category_id", "")).strip()
            name = str(data.get("name", "")).strip()
            status = str(data.get("status", "")).strip()
            now_ts = int(time.time() * 1000)

            # Status-only toggle (when just flipping ACTIVE/INACTIVE)
            if cat_id and not name:
                if status in ("ACTIVE", "INACTIVE"):
                    self.mgdDB.db_payment_category.update_one(
                        {"category_id": cat_id},
                        {"$set": {"status": status, "timestamp": now_ts}}
                    )
                    return {"ok": True}
                return {"ok": False, "error": "Invalid status"}

            if not name:
                return {"ok": False, "error": "Name is required"}

            if cat_id:
                update = {"name": name, "timestamp": now_ts}
                if status in ("ACTIVE", "INACTIVE"):
                    update["status"] = status
                self.mgdDB.db_payment_category.update_one(
                    {"category_id": cat_id}, {"$set": update}
                )
            else:
                cat_id = uuid.uuid4().hex
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                count = self.mgdDB.db_payment_category.count_documents(
                    {"status": {"$ne": "DELETED"}}
                )
                self.mgdDB.db_payment_category.insert_one({
                    "category_id": cat_id,
                    "name": name,
                    "order": count,
                    "status": "ACTIVE",
                    "created_at": now_str,
                    "timestamp": now_ts,
                })
            return {"ok": True}
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Save category failed."}

    def delete_category(self, cat_id):
        """Soft-delete a category and all its methods."""
        try:
            now_ts = int(time.time() * 1000)
            self.mgdDB.db_payment_category.update_one(
                {"category_id": cat_id},
                {"$set": {"status": "DELETED", "timestamp": now_ts}},
            )
            self.mgdDB.db_payment_method.update_many(
                {"fk_category_id": cat_id, "status": {"$ne": "DELETED"}},
                {"$set": {"status": "DELETED", "timestamp": now_ts}},
            )
            return {"ok": True}
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Delete category failed."}

    # ── Method CRUD ─────────────────────────────────────────────────────────

    def save_method(self, data):
        """Create or update a payment method. data: {method_id?, fk_category_id, merchant_id, merchant_name, fee, icon_url, free_admin_fee?, status?}"""
        try:
            method_id = str(data.get("method_id", "")).strip()
            cat_id = str(data.get("fk_category_id", "")).strip()
            merchant_id = str(data.get("merchant_id", "")).strip().upper()
            merchant_name = str(data.get("merchant_name", "")).strip()
            fee = str(data.get("fee", "")).strip()
            icon_url = str(data.get("icon_url", "")).strip()
            free_admin_fee = bool(data.get("free_admin_fee"))
            status = str(data.get("status", "")).strip()
            now_ts = int(time.time() * 1000)

            # Status-only toggle (when just flipping ACTIVE/INACTIVE)
            if method_id and not merchant_id and not merchant_name and status in ("ACTIVE", "INACTIVE"):
                self.mgdDB.db_payment_method.update_one(
                    {"method_id": method_id},
                    {"$set": {"status": status, "timestamp": now_ts}}
                )
                return {"ok": True}

            # Free-fee-only toggle (when just flipping free_admin_fee)
            if method_id and not merchant_id and not merchant_name and "free_admin_fee" in data and not status:
                self.mgdDB.db_payment_method.update_one(
                    {"method_id": method_id},
                    {"$set": {"free_admin_fee": free_admin_fee, "timestamp": now_ts}}
                )
                return {"ok": True}

            if not merchant_id or not merchant_name:
                return {"ok": False, "error": "Code and Name are required"}
            if not cat_id and not method_id:
                return {"ok": False, "error": "Category is required for new methods"}

            if method_id:
                update = {
                    "merchant_id": merchant_id,
                    "merchant_name": merchant_name,
                    "fee": fee,
                    "icon_url": icon_url,
                    "free_admin_fee": free_admin_fee,
                    "timestamp": now_ts,
                }
                if status in ("ACTIVE", "INACTIVE"):
                    update["status"] = status
                self.mgdDB.db_payment_method.update_one(
                    {"method_id": method_id}, {"$set": update}
                )
            else:
                method_id = uuid.uuid4().hex
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                count = self.mgdDB.db_payment_method.count_documents({
                    "fk_category_id": cat_id,
                    "status": {"$ne": "DELETED"},
                })
                self.mgdDB.db_payment_method.insert_one({
                    "method_id": method_id,
                    "fk_category_id": cat_id,
                    "merchant_id": merchant_id,
                    "merchant_name": merchant_name,
                    "icon_url": icon_url,
                    "fee": fee,
                    "free_admin_fee": free_admin_fee,
                    "order": count,
                    "status": "ACTIVE",
                    "created_at": now_str,
                    "timestamp": now_ts,
                })
            return {"ok": True}
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Save method failed."}

    def delete_method(self, method_id):
        """Soft-delete a payment method."""
        try:
            now_ts = int(time.time() * 1000)
            self.mgdDB.db_payment_method.update_one(
                {"method_id": method_id},
                {"$set": {"status": "DELETED", "timestamp": now_ts}},
            )
            return {"ok": True}
        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Delete method failed."}

    # ── Icon Upload ─────────────────────────────────────────────────────────

    def upload_icon(self, icon_file):
        """Upload a merchant logo to R2. Returns {ok, url} or {ok, error}."""
        try:
            if not icon_file or not icon_file.filename:
                return {"ok": False, "error": "No file uploaded"}

            ext = os.path.splitext(icon_file.filename)[1].lower()
            if ext not in ALLOWED_ICON_EXT:
                return {"ok": False, "error": "Only PNG, JPG, WebP, SVG allowed"}

            icon_file.seek(0, 2)
            size = icon_file.tell()
            icon_file.seek(0)
            if size > MAX_ICON_SIZE:
                return {"ok": False, "error": "Icon must be under 2 MB"}

            file_id = uuid.uuid4().hex
            key = f"payment_methods/{file_id}/logo{ext}"
            url = r2_mod.r2_storage_proc().upload_file(icon_file, key)
            return {"ok": True, "url": url}

        except Exception:
            if self.webapp:
                self.webapp.logger.debug(traceback.format_exc())
            return {"ok": False, "error": "Icon upload failed."}
