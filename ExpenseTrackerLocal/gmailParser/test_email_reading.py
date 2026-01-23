#!/usr/bin/env python3
"""
Test script to verify email reading functionality.
Run with: python3 test_email_reading.py
"""

import os
import sys
from datetime import datetime, timedelta

os.environ['DRY_RUN'] = 'true'
os.environ['READ_ALL_EMAILS'] = 'true'
os.environ['MAX_EMAILS'] = '5'

one_month_ago = datetime.now() - timedelta(days=30)
os.environ['START_DATE'] = one_month_ago.strftime("%d-%b-%Y")

from expense_tracker import (
    fetch_emails_from_senders,
    connect_imap,
    WATCHED_SENDERS,
    parse_email
)

def test_email_fetching():
    email_addr = os.getenv("EMAIL_ADDRESS")
    email_password = os.getenv("EMAIL_PASSWORD")
    
    if not email_addr or not email_password:
        print("Please set EMAIL_ADDRESS and EMAIL_PASSWORD environment variables")
        sys.exit(1)
    
    print("Test Configuration:")
    print(f"  Email: {email_addr}")
    print(f"  Read all emails: True")
    print(f"  Start date: {os.getenv('START_DATE')}")
    print(f"  Max emails: 5")
    print(f"  Watched senders: {', '.join(WATCHED_SENDERS)}")
    print()
    
    try:
        print("Connecting to Gmail...")
        mail = connect_imap("imap.gmail.com", email_addr, email_password)
        
        print("Fetching emails (both read and unread)...")
        emails = fetch_emails_from_senders(
            mail, 
            max_emails=5, 
            since_date=os.getenv('START_DATE', ''),
            read_all=True
        )
        
        print(f"\nFound {len(emails)} emails from watched senders")
        
        for i, (msg_id, sender, body) in enumerate(emails, 1):
            print(f"\n--- Email {i} ---")
            print(f"  ID: {msg_id}")
            print(f"  From: {sender[:50]}...")
            print(f"  Body preview: {body[:100]}...")
            
            transaction = parse_email(sender, body)
            if transaction:
                print(f"  ✓ Parsed successfully:")
                print(f"    Amount: {transaction.amount}")
                print(f"    Merchant: {transaction.merchant}")
                print(f"    Date: {transaction.date}")
                print(f"    Type: {transaction.transaction_type}")
            else:
                print(f"  ✗ Could not parse transaction")
        
        mail.close()
        mail.logout()
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_email_fetching()