import logging
from email.message import EmailMessage
import aiosmtplib
from app.core.config import Settings

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def send_otp_email(self, to_email: str, otp_code: str):
        if not self.settings.SMTP_USER or not self.settings.SMTP_PASS:
            logger.warning(f"SMTP Credentials missing! Cannot send OTP {otp_code} to {to_email}")
            return
            
        message = EmailMessage()
        message["From"] = self.settings.SMTP_FROM
        message["To"] = to_email
        message["Subject"] = "CogniFlip - Your Verification Code"
        
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
            )
            logger.info(f"OTP email sent to {to_email}")
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
