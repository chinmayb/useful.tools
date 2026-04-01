#!/usr/bin/env python3
"""Test IMAP search commands to debug the parsing error."""

import imaplib
import os
import sys
from datetime import datetime, timedelta

def test_search_formats():
    email_addr = os.getenv("EMAIL_ADDRESS")
    email_password = os.getenv("EMAIL_PASSWORD")
    
    if not email_addr or not email_password:
        print("EMAIL_ADDRESS and EMAIL_PASSWORD required")
        sys.exit(1)
    
    print(f"Connecting to Gmail as {email_addr}...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email_addr, email_password)
    print("Connected successfully")
    
    mail.select("INBOX")
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    since_date = thirty_days_ago.strftime("%d-%b-%Y")
    
    test_sender = "alerts@hdfcbank.net"
    
    print(f"\nTesting different search formats for sender: {test_sender}")
    print(f"Since date: {since_date}")
    print("-" * 60)
    
    print("\nTest 1: Simple FROM search")
    try:
        status, messages = mail.search(None, 'FROM', f'"{test_sender}"')
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nTest 2: FROM + SINCE (separate args)")
    try:
        status, messages = mail.search(None, 'FROM', f'"{test_sender}"', 'SINCE', since_date)
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nTest 3: Single string (space-separated)")
    try:
        search_str = f'FROM "{test_sender}" SINCE {since_date}'
        print(f"  Search string: {search_str}")
        status, messages = mail.search(None, search_str)
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nTest 4: Parenthesized string")
    try:
        search_str = f'(FROM "{test_sender}" SINCE {since_date})'
        print(f"  Search string: {search_str}")
        status, messages = mail.search(None, search_str)
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nTest 5: UNSEEN + FROM (separate args)")
    try:
        status, messages = mail.search(None, 'UNSEEN', 'FROM', f'"{test_sender}"')
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nTest 6: UNSEEN FROM SINCE (single string)")
    try:
        search_str = f'UNSEEN FROM "{test_sender}" SINCE {since_date}'
        print(f"  Search string: {search_str}")
        status, messages = mail.search(None, search_str)
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\nTest 7: ALL with criteria")
    try:
        status, messages = mail.search(None, 'ALL', 'FROM', f'"{test_sender}"')
        print(f"  Result: {status}, Found {len(messages[0].split()) if messages[0] else 0} emails")
    except Exception as e:
        print(f"  ERROR: {e}")
    
    mail.close()
    mail.logout()
    print("\nTests completed")

if __name__ == "__main__":
    test_search_formats()