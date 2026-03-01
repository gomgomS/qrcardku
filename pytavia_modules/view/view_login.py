import sys

sys.path.append("pytavia_core"    )
sys.path.append("pytavia_modules" )
sys.path.append("pytavia_settings")
sys.path.append("pytavia_stdlib"  )
sys.path.append("pytavia_storage" )
sys.path.append("pytavia_modules/view" )

from flask          import render_template

class view_login:

    def __init__(self):
        pass

    def html(self, error_msg=None):
        return render_template(
            "auth/login.html",
            error_msg=error_msg
        )

    def admin_html(self, error_msg=None):
        return render_template(
            "auth/admin_login.html",
            error_msg=error_msg
        )

    def register_html(self, error_msg=None):
        return render_template(
            "auth/register.html",
            error_msg=error_msg
        )

