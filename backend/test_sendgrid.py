import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv('.env')

message = Mail(
    from_email='YOUR_VERIFIED_EMAIL@domain.com',  # Change this!
    to_emails=os.getenv('NOTIFICATION_EMAIL'),
    subject='SendGrid Test',
    html_content='<p>This is a test</p>'
)

try:
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    response = sg.send(message)
    print(f"Success! Status code: {response.status_code}")
    print(f"Response body: {response.body}")
    print(f"Response headers: {response.headers}")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'body'):
        print(f"Error body: {e.body}")