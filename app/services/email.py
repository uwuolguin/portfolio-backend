import resend
from app.config import settings
import structlog

logger = structlog.get_logger(__name__)


class EmailService:
    def __init__(self):
        resend.api_key = settings.resend_api_key
    
    async def send_verification_email(self, to_email: str, token: str, user_name: str) -> bool:
        """Send email verification link"""
        verification_url = f"{settings.frontend_url}/verify-email?token={token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; padding: 40px;">
                            <tr>
                                <td>
                                    <h1 style="color: #333333; margin: 0 0 20px 0;">Welcome to Proveo, {user_name}! 🎉</h1>
                                    <p style="color: #666666; font-size: 16px; line-height: 1.5; margin: 0 0 20px 0;">
                                        Thanks for signing up! Please verify your email address to get started.
                                    </p>
                                    <table width="100%" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td align="center" style="padding: 20px 0;">
                                                <a href="{verification_url}" 
                                                   style="display: inline-block; padding: 14px 32px; 
                                                          background-color: #4CAF50; color: #ffffff; 
                                                          text-decoration: none; border-radius: 4px;
                                                          font-weight: bold; font-size: 16px;">
                                                    Verify Email Address
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                    <p style="color: #999999; font-size: 14px; line-height: 1.5; margin: 20px 0 0 0;">
                                        Or copy and paste this link into your browser:<br>
                                        <a href="{verification_url}" style="color: #4CAF50; word-break: break-all;">
                                            {verification_url}
                                        </a>
                                    </p>
                                    <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                                    <p style="color: #999999; font-size: 12px; line-height: 1.5; margin: 0;">
                                        This link expires in 24 hours. If you didn't create this account, please ignore this email.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        try:
            response = resend.Emails.send({
                "from": f"Proveo <{settings.email_from}>",
                "to": to_email,
                "subject": "✅ Verify Your Proveo Account",
                "html": html_content
            })
            
            logger.info("verification_email_sent", 
                       to=to_email, 
                       email_id=response.get('id'))
            return True
            
        except Exception as e:
            logger.error("verification_email_failed", 
                        to=to_email, 
                        error=str(e),
                        exc_info=True)
            return False


email_service = EmailService()