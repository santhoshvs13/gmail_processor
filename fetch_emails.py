import os
import json
import sqlite3
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def authenticate_gmail():
    """Authenticate to Gmail API and return service."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request()) 
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080, access_type='offline', prompt='consent')  
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service


def fetch_emails(service):
    """Fetch emails from the user's inbox and store them in the database."""
    try:
        results = service.users().messages().list(userId='me', labelIds=['INBOX']).execute()
        messages = results.get('messages', [])

        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                from_address TEXT,
                subject TEXT,
                date TEXT,
                snippet TEXT
            )
        ''')

        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            headers = msg['payload'].get('headers', [])

            from_address = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown')
            subject = next((header['value'] for header in headers if header['name'] == 'Subject'), 'No Subject')
            date = next((header['value'] for header in headers if header['name'] == 'Date'), 'No Date')
            snippet = msg.get('snippet', 'No Snippet')

            cursor.execute('INSERT OR REPLACE INTO emails (id, from_address, subject, date, snippet) VALUES (?, ?, ?, ?, ?)',
                           (message['id'], from_address, subject, date, snippet))

        conn.commit()
    
    except Exception as e:
        print(f"Error occurred while fetching emails: {e}")
    
    finally:
        conn.close()

if __name__ == '__main__':
    service = authenticate_gmail()
    fetch_emails(service)
