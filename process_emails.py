import sqlite3
import json
import os
import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def authenticate_gmail_modify():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("The credentials have expired, and cannot be refreshed. Re-authentication is required.")
    
    service = build('gmail', 'v1', credentials=creds)
    return service

def load_rules():
    try:
        with open('rules.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError("The rules.json file is missing. Please ensure the file exists and try again.")

def process_emails(service, rules):
    conn = None
    try:
        conn = sqlite3.connect('emails.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM emails')
        emails = cursor.fetchall()

        for email in emails:
            email_id, from_address, subject, date_str, snippet = email
            print(f"Processing email from: {from_address} with subject: {subject}")

            try:
                email_date = datetime.datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
            except ValueError as e:
                continue

            email_data = service.users().messages().get(userId='me', id=email_id).execute()
            email_labels = email_data.get('labelIds', [])

            for rule in rules['rules']:
                if evaluate_rule(rule, from_address, subject, email_date, email_labels):
                    for action in rule['actions']:
                        if action['action'] == 'mark_as_read':
                            mark_email_as_read(service, email_id)
                        elif action['action'] == 'move_to_label':
                            move_email_to_label(service, email_id, action['label'])
    
    except sqlite3.Error as e:
        print(f"Database error occurred: {e}")
    
    finally:
        if conn:
            conn.close()

def evaluate_rule(rule, from_address, subject, email_date, email_labels):
    if rule['predicate'] == 'All':
        return all(evaluate_condition(cond, from_address, subject, email_date, email_labels) for cond in rule['conditions'])
    elif rule['predicate'] == 'Any':
        return any(evaluate_condition(cond, from_address, subject, email_date, email_labels) for cond in rule['conditions'])

def evaluate_condition(cond, from_address, subject, email_date, email_labels):
    field = cond['field']
    predicate = cond['predicate']
    value = cond['value']
    
    if field == 'From':
        if predicate == 'Contains':
            return value in from_address
        elif predicate == 'Equals':
            return from_address == value
    elif field == 'Subject':
        if predicate == 'Contains':
            return value in subject
        elif predicate == 'Equals':
            return subject == value
    elif field == 'Labels':
        if predicate == 'Contains':
            return value.upper() in email_labels 
    elif field == 'Date':
        if predicate == 'Last':
            return check_date_last(email_date, value)
    
    return False

def check_date_last(email_date, value):
    try:
        time_unit = value[-1]  
        amount = int(value[:-1])

        now = datetime.datetime.now(datetime.timezone.utc)  
        if time_unit == 'd':
            time_limit = now - datetime.timedelta(days=amount)
        elif time_unit == 'h':
            time_limit = now - datetime.timedelta(hours=amount)
        else:
            raise ValueError("Unsupported time unit in 'Last' condition.")

        return email_date >= time_limit
    except Exception as e:
        print(f"Error in check_date_last: {e}")
        return False

def mark_email_as_read(service, email_id):
    try:
        service.users().messages().modify(
            userId='me',
            id=email_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        print(f"Marked email as read: {email_id}")
    except Exception as e:
        print(f"Failed to mark email as read: {e}")

def move_email_to_label(service, email_id, label_name):
    try:
        labels = service.users().labels().list(userId='me').execute().get('labels', [])
        label_id = next((label['id'] for label in labels if label['name'].lower() == label_name.lower()), None)

        if label_id:
            service.users().messages().modify(
                userId='me',
                id=email_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            print(f"Moved email to label '{label_name}': {email_id}")
        else:
            print(f"Label '{label_name}' not found.")
    
    except Exception as e:
        print(f"Failed to move email to label: {e}")

if __name__ == '__main__':
    try:
        service = authenticate_gmail_modify()
        rules = load_rules()
        process_emails(service, rules)
    except Exception as e:
        print(f"Error occurred: {e}")
