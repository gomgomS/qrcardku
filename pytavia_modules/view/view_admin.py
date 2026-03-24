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
from admin          import admin_frame_proc


class view_admin:

    def __init__(self, app):
        self.webapp = app

    def admins_html(self, msg=None, error_msg=None):
        admins = admin_proc.admin_proc(self.webapp).get_all_admins()
        return render_template(
            "admin/admins.html",
            admins=admins,
            valid_roles=admin_proc.admin_proc.VALID_ROLES,
            msg=msg,
            error_msg=error_msg,
        )

    def users_html(self, msg=None, error_msg=None):
        users = admin_proc.admin_proc(self.webapp).get_all_users()
        return render_template(
            "admin/users.html",
            users=users,
            msg=msg,
            error_msg=error_msg,
        )

    def frames_html(self, msg=None, error_msg=None):
        frames = admin_frame_proc.admin_frame_proc(self.webapp).get_all_frames()
        return render_template(
            "admin/frames.html",
            frames=frames,
            msg=msg,
            error_msg=error_msg,
        )
