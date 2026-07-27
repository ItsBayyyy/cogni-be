import logging
import json
import hashlib
import urllib.request
import asyncio
from email.message import EmailMessage
import aiosmtplib
from app.core.config import Settings

logger = logging.getLogger(__name__)

def _recipient_id(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]

class EmailService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def _dispatch_email(self, to_email: str, subject: str, html_content: str):
        recipient_id = _recipient_id(to_email)
        # Option 1: Send via Brevo HTTPS API (Sends to ANY recipient email, 300 free emails/day)
        if self.settings.BREVO_API_KEY:
            try:
                sender_email = self.settings.SMTP_USER if "@" in (self.settings.SMTP_USER or "") else "yuuxdrestapi@gmail.com"
                def _brevo_request():
                    req_data = json.dumps({
                        "sender": {"name": "CogniFlip", "email": sender_email},
                        "to": [{"email": to_email}],
                        "subject": subject,
                        "htmlContent": html_content
                    }).encode("utf-8")

                    req = urllib.request.Request(
                        "https://api.brevo.com/v3/smtp/email",
                        data=req_data,
                        headers={
                            "api-key": self.settings.BREVO_API_KEY.strip(),
                            "Content-Type": "application/json"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return resp.read()

                await asyncio.to_thread(_brevo_request)
                logger.info("Email sent via Brevo recipient_id=%s", recipient_id)
                return
            except urllib.error.HTTPError as e:
                logger.error(
                    "Brevo email request failed status=%s recipient_id=%s",
                    e.code,
                    recipient_id,
                )
            except Exception:
                logger.error("Brevo email request failed recipient_id=%s", recipient_id)

        # Option 2: Send via Resend HTTPS API
        if self.settings.RESEND_API_KEY:
            try:
                resend_from = self.settings.SMTP_FROM if "resend.dev" in (self.settings.SMTP_FROM or "") else "CogniFlip <onboarding@resend.dev>"

                def _resend_request():
                    req_data = json.dumps({
                        "from": resend_from,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content
                    }).encode("utf-8")

                    req = urllib.request.Request(
                        "https://api.resend.com/emails",
                        data=req_data,
                        headers={
                            "Authorization": f"Bearer {self.settings.RESEND_API_KEY.strip()}",
                            "Content-Type": "application/json"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return resp.read()

                await asyncio.to_thread(_resend_request)
                logger.info("Email sent via Resend recipient_id=%s", recipient_id)
                return
            except urllib.error.HTTPError as e:
                logger.error(
                    "Resend email request failed status=%s recipient_id=%s",
                    e.code,
                    recipient_id,
                )
            except Exception:
                logger.error("Resend email request failed recipient_id=%s", recipient_id)

        # Option 3: Fallback to SMTP
        if not self.settings.SMTP_USER or not self.settings.SMTP_PASS:
            logger.warning("Email provider is not configured recipient_id=%s", recipient_id)
            return

        message = EmailMessage()
        message["From"] = self.settings.SMTP_FROM
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(html_content, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=self.settings.SMTP_HOST,
                port=self.settings.SMTP_PORT,
                username=self.settings.SMTP_USER,
                password=self.settings.SMTP_PASS,
                use_tls=True if self.settings.SMTP_PORT == 465 else False,
                start_tls=True if self.settings.SMTP_PORT == 587 else False,
                timeout=15.0,
            )
            logger.info("Email sent via SMTP recipient_id=%s", recipient_id)
        except Exception:
            logger.error("SMTP email request failed recipient_id=%s", recipient_id)

    async def send_otp_email(self, to_email: str, otp_code: str):
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #333;">Welcome to CogniFlip!</h2>
                <p>Please use the following 6-digit code to verify your email address:</p>
                <div style="background-color: #f4f4f4; padding: 15px; text-align: center; border-radius: 8px; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #000;">{otp_code}</span>
                </div>
                <p>This code will expire in 15 minutes.</p>
                <p style="color: #666; font-size: 12px; margin-top: 40px;">If you didn't request this, you can safely ignore this email.</p>
            </body>
        </html>
        """
        await self._dispatch_email(to_email, "CogniFlip - Your Verification Code", html_content)

    async def send_reset_password_email(self, to_email: str, otp_code: str):
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #333;">Reset Your Password - CogniFlip</h2>
                <p>We received a request to reset your password. Use the following 6-digit verification code to proceed:</p>
                <div style="background-color: #f4f4f4; padding: 15px; text-align: center; border-radius: 8px; margin: 20px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #000;">{otp_code}</span>
                </div>
                <p>This code will expire in 15 minutes.</p>
                <p style="color: #666; font-size: 12px; margin-top: 40px;">If you didn't request a password reset, you can safely ignore this email.</p>
            </body>
        </html>
        """
        await self._dispatch_email(to_email, "CogniFlip - Password Reset Code", html_content)
