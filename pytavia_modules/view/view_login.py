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

    def forgot_password_html(self, error_msg=None, msg=None):
        return render_template(
            "auth/forgot_password.html",
            error_msg=error_msg,
            msg=msg
        )
        
    def reset_password_html(self, token=None, error_msg=None):
        return render_template(
            "auth/reset_password.html",
            token=token,
            error_msg=error_msg
        )

    def signup_success_html(self, msg=None, error_msg=None):
        return render_template(
            "auth/signup_success.html",
            msg=msg,
            error_msg=error_msg
        )

    def verify_otp_html(self, email=None, msg=None, error_msg=None):
        return render_template(
            "auth/verify_otp.html",
            email=email,
            msg=msg,
            error_msg=error_msg
        )

    def check_email_html(self):
        return render_template(
            "auth/check_email.html"
        )

