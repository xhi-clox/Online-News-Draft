import os
import base64
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(base_dir, 'token.json')
    creds_path = os.path.join(base_dir, 'credentials.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Token refresh failed ({e}), will re-authenticate")
                creds = None
                try:
                    os.remove(token_path)
                except OSError:
                    pass
        else:
            creds = None

        if not creds:
            if not os.path.exists(creds_path):
                logger.error(
                    "credentials.json not found. Please set up Gmail API: "
                    "https://developers.google.com/gmail/api/quickstart/python"
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error creating Gmail service: {e}")
        return None

def fetch_emails(service, query=None):
    try:
        logger.info("Fetching unread emails from Primary inbox only")
        results = service.users().messages().list(
            userId='me',
            labelIds=['INBOX', 'UNREAD'],
            includeSpamTrash=False,
        ).execute()
        all_messages = results.get('messages', [])
        estimate = results.get('resultSizeEstimate', 0)
        logger.info(f"Found {len(all_messages)} unread messages (estimate: {estimate})")

        if not all_messages:
            logger.info("No unread messages found")
            return []

        primary_messages = []
        for msg in all_messages:
            msg_data = service.users().messages().get(
                userId='me', id=msg['id'], fields='id,labelIds'
            ).execute()
            labels = msg_data.get('labelIds', [])
            category_labels = [l for l in labels if l.startswith('CATEGORY_')]
            has_non_primary = any(l != 'CATEGORY_PRIMARY' for l in category_labels)
            if not category_labels or not has_non_primary:
                primary_messages.append(msg)

        logger.info(f"Found {len(primary_messages)} unread Primary messages")
        return primary_messages
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        return []

def decode_gmail_data(data):
    """Safely decode base64url data from Gmail API."""
    try:
        # Gmail uses urlsafe base64 and sometimes removes padding
        padding = len(data) % 4
        if padding:
            data += '=' * (4 - padding)
        return base64.urlsafe_b64decode(data.encode('UTF-8'))
    except Exception as e:
        logger.error(f"Base64 decode error: {e}")
        return b""

def get_message_details(service, msg_id):
    try:
        message = service.users().messages().get(userId='me', id=msg_id).execute()
        payload = message['payload']
        headers = payload.get('headers', [])
        
        subject = "(No Subject)"
        for header in headers:
            if header['name'].lower() == 'subject':
                subject = header['value']
                break
        
        body = ""
        attachments = []
        
        def process_parts(parts):
            nonlocal body
            for part in parts:
                mime_type = part.get('mimeType')
                body_data = part.get('body', {}).get('data')
                
                if mime_type == 'text/plain' and body_data:
                    decoded = decode_gmail_data(body_data)
                    if decoded:
                        body += decoded.decode('utf-8', errors='ignore')
                elif mime_type == 'text/html' and body_data and not body:
                    decoded = decode_gmail_data(body_data)
                    if decoded:
                        body += decoded.decode('utf-8', errors='ignore')
                
                if part.get('filename') and part.get('body', {}).get('attachmentId'):
                    attachments.append({
                        'filename': part['filename'],
                        'attachmentId': part['body']['attachmentId'],
                        'mimeType': mime_type
                    })
                
                if 'parts' in part:
                    process_parts(part['parts'])

        if 'parts' in payload:
            process_parts(payload['parts'])
        else:
            body_data = payload.get('body', {}).get('data')
            if body_data:
                decoded = decode_gmail_data(body_data)
                if decoded:
                    body = decoded.decode('utf-8', errors='ignore')

        return {
            'id': msg_id,
            'subject': subject,
            'body': body,
            'attachments': attachments
        }
    except Exception as e:
        logger.error(f"Error getting message details for {msg_id}: {e}")
        return None

def download_attachment(service, msg_id, attachment_id, save_path):
    try:
        attachment = service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=attachment_id).execute()
        data = attachment['data']
        file_data = decode_gmail_data(data)
        
        if not file_data:
            return None
            
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(file_data)
        return save_path
    except Exception as e:
        logger.error(f"Error downloading attachment {attachment_id}: {e}")
        return None
