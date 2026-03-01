import sys

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )
sys.path.append("pytavia_modules/view" )
sys.path.append("pytavia_modules/admin" )

from flask          import render_template
from admin          import admin_proc
from karyawan       import karyawan_proc
from ecard          import ecard_proc

class view_admin:

    def __init__(self, app):
        self.webapp = app

    def requests_html(self, msg=None, error_msg=None):
        requests = admin_proc.admin_proc(self.webapp).get_all_requests()
        return render_template(
            "admin/dashboard.html",
            requests=requests,
            msg=msg,
            error_msg=error_msg
        )

    def users_html(self, msg=None, error_msg=None):
        users = admin_proc.admin_proc(self.webapp).get_all_users()
        return render_template(
            "admin/users.html",
            users=users,
            msg=msg,
            error_msg=error_msg
        )

    def karyawan_html(self, msg=None, error_msg=None):
        karyawans = karyawan_proc.karyawan_proc(self.webapp).get_all_karyawan()
        return render_template(
            "admin/karyawan.html",
            karyawans=karyawans,
            msg=msg,
            error_msg=error_msg
        )

    def karyawan_add_html(self, msg=None, error_msg=None):
        return render_template(
            "admin/karyawan_add.html",
            msg=msg,
            error_msg=error_msg
        )

    def karyawan_edit_html(self, karyawan_id, msg=None, error_msg=None):
        karyawan = karyawan_proc.karyawan_proc(self.webapp).get_karyawan_by_id(karyawan_id)
        if not karyawan:
            return self.karyawan_html(error_msg="Employee not found.")
            
        return render_template(
            "admin/karyawan_edit.html",
            karyawan=karyawan,
            msg=msg,
            error_msg=error_msg
        )

    def ecard_html(self, msg=None, error_msg=None):
        ecards = ecard_proc.ecard_proc(self.webapp).get_all_ecards()
        return render_template(
            "admin/ecard.html",
            ecards=ecards,
            msg=msg,
            error_msg=error_msg
        )

    def ecard_add_html(self, msg=None, error_msg=None):
        karyawans = karyawan_proc.karyawan_proc(self.webapp).get_all_karyawan()
        return render_template(
            "admin/ecard_add.html",
            karyawans=karyawans,
            msg=msg,
            error_msg=error_msg
        )

    def ecard_edit_html(self, ecard_id, msg=None, error_msg=None):
        ecard = ecard_proc.ecard_proc(self.webapp).get_ecard_by_id(ecard_id)
        if not ecard:
            return self.ecard_html(error_msg="E-card not found.")
            
        karyawans = karyawan_proc.karyawan_proc(self.webapp).get_all_karyawan()
        return render_template(
            "admin/ecard_edit.html",
            ecard=ecard,
            karyawans=karyawans,
            msg=msg,
            error_msg=error_msg
        )
