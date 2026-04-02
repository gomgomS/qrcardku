import requests
import traceback
import sys

sys.path.append("pytavia_core")
from pytavia_core import config

class brevo_email_proc:

    def __init__(self, app=None):
        self.webapp = app
        self.api_url = "https://api.brevo.com/v3/smtp/email"
        self.api_key = getattr(config, "API_KEY_BREVO_EMAIL", "")
        self.sender_email = getattr(config, "EMAIL_ADMIN", "halo@qrkartu.com")
        self.sender_name = "QRkartu"

    def _send_email(self, to_email, to_name, subject, html_content=None, text_content=None):
        if not to_name:
            to_name = to_email.split('@')[0] if to_email else "User"

        if not self.api_key:
            if self.webapp:
                self.webapp.logger.error("BREVO API KEY is missing in config.")
            return False

        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        data = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
        }
        if text_content and not html_content:
            data["textContent"] = text_content
        else:
            data["htmlContent"] = html_content or ""

        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=10)
            if response.status_code in [200, 201, 202]:
                return True
            else:
                if self.webapp:
                    self.webapp.logger.error(f"Brevo API Error: {response.text}")
                return False
        except Exception as e:
            if self.webapp:
                self.webapp.logger.error(f"Failed to send email via Brevo: {str(e)}\n{traceback.format_exc()}")
            return False

    def send_verification_email(self, to_email, to_name, otp):
        subject = "Please Verify Your Email Address"
        html_content = f"""
        <html>
            <body>
                <h2>Welcome, {to_name}!</h2>
                <p>Thank you for registering. Please enter the following 6-digit verification code to access your account:</p>
                <div style="padding: 15px; margin: 20px 0; background-color: #f4f4f5; text-align: center; border-radius: 8px;">
                    <h1 style="letter-spacing: 5px; color: #1c2541; margin: 0;">{otp}</h1>
                </div>
                <p>This code will expire shortly. If you did not request this, you can safely ignore this email.</p>
                <br>
                <p>Best regards,<br>The QRkartu Team</p>
            </body>
        </html>
        """
        return self._send_email(to_email, to_name, subject, html_content)

    def send_forgot_password_email(self, to_email, to_name, token):
        base_url = getattr(config, "G_BASE_URL", "http://127.0.0.1:5008")
        reset_link = f"{base_url}/password-reset?token={token}"

        subject = "Reset Your QRkartu Password"
        html_content = f"""
        <html>
            <body>
                <h2>Password Reset Request</h2>
                <p>Hi {to_name},</p>
                <p>We received a request to reset your password. If you didn't make this request, you can ignore this email.</p>
                <p>Click the link below to reset your password:</p>
                <p><a href="{reset_link}" style="padding: 10px 20px; background-color: #EBA81B; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
                <p>Or copy and paste this URL into your browser:</p>
                <p>{reset_link}</p>
                <p>Thanks,<br>The QRkartu Team</p>
            </body>
        </html>
        """
        return self._send_email(to_email, to_name, subject, html_content)
