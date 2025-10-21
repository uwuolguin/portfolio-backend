# app/templates/email_verification.py
"""HTML templates for email verification responses"""

def verification_success_page(email: str) -> str:
    """HTML page for successful email verification"""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Email Verified - Proveo</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                background: white;
                border-radius: 16px;
                padding: 48px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }}
            .success-icon {{
                width: 80px;
                height: 80px;
                background: #4CAF50;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
                animation: scaleIn 0.5s ease-out;
            }}
            .success-icon svg {{
                width: 48px;
                height: 48px;
                stroke: white;
                stroke-width: 3;
                stroke-linecap: round;
                stroke-linejoin: round;
                fill: none;
            }}
            h1 {{
                color: #333;
                font-size: 28px;
                margin-bottom: 16px;
                font-weight: 600;
            }}
            p {{
                color: #666;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 32px;
            }}
            .email {{
                color: #667eea;
                font-weight: 600;
            }}
            .info-box {{
                background: #f8f9fa;
                border-left: 4px solid #4CAF50;
                padding: 16px;
                border-radius: 8px;
                text-align: left;
                margin-top: 24px;
            }}
            .info-box p {{
                margin: 0;
                font-size: 14px;
                color: #555;
            }}
            @keyframes scaleIn {{
                from {{
                    transform: scale(0);
                    opacity: 0;
                }}
                to {{
                    transform: scale(1);
                    opacity: 1;
                }}
            }}
            @media (max-width: 600px) {{
                .container {{
                    padding: 32px 24px;
                }}
                h1 {{
                    font-size: 24px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">
                <svg viewBox="0 0 24 24">
                    <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
            </div>
            
            <h1>✅ Email Verified!</h1>
            
            <p>
                Your email <span class="email">{email}</span> has been successfully verified.
            </p>
            
            <div class="info-box">
                <p><strong>What's next?</strong></p>
                <p>You can now close this window and log in to your Proveo account using your credentials.</p>
            </div>
        </div>
    </body>
    </html>
    """


def verification_error_page(error_message: str) -> str:
    """HTML page for email verification errors"""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verification Failed - Proveo</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                background: white;
                border-radius: 16px;
                padding: 48px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }}
            .error-icon {{
                width: 80px;
                height: 80px;
                background: #f44336;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
            }}
            .error-icon svg {{
                width: 48px;
                height: 48px;
                stroke: white;
                stroke-width: 3;
                stroke-linecap: round;
                stroke-linejoin: round;
                fill: none;
            }}
            h1 {{
                color: #333;
                font-size: 28px;
                margin-bottom: 16px;
                font-weight: 600;
            }}
            p {{
                color: #666;
                font-size: 16px;
                line-height: 1.6;
                margin-bottom: 32px;
            }}
            .error-message {{
                background: #ffebee;
                border-left: 4px solid #f44336;
                padding: 16px;
                border-radius: 8px;
                text-align: left;
                margin-top: 24px;
            }}
            .error-message p {{
                margin: 0;
                font-size: 14px;
                color: #c62828;
            }}
            @media (max-width: 600px) {{
                .container {{
                    padding: 32px 24px;
                }}
                h1 {{
                    font-size: 24px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error-icon">
                <svg viewBox="0 0 24 24">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </div>
            
            <h1>❌ Verification Failed</h1>
            
            <p>We couldn't verify your email address.</p>
            
            <div class="error-message">
                <p><strong>Error:</strong> {error_message}</p>
            </div>
        </div>
    </body>
    </html>
    """


def verification_server_error_page() -> str:
    """HTML page for unexpected server errors"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error - Proveo</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 16px;
                padding: 48px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }
            h1 {
                color: #333;
                font-size: 28px;
                margin-bottom: 16px;
                font-weight: 600;
            }
            p {
                color: #666;
                font-size: 16px;
                line-height: 1.6;
            }
            @media (max-width: 600px) {
                .container {
                    padding: 32px 24px;
                }
                h1 {
                    font-size: 24px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>⚠️ Something Went Wrong</h1>
            <p>An unexpected error occurred. Please try again later.</p>
        </div>
    </body>
    </html>
    """