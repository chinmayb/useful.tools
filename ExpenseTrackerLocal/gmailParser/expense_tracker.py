#!/usr/bin/env python3
"""
Expense Tracker - Reads bank/CC transaction emails and logs to Sure Finance API.

Supports: HDFC Bank (Savings + Credit Cards), Axis Bank, ICICI CC, HDFC NACH
"""

import imaplib
from email import message_from_bytes
from email.message import Message
import re
import os
import sys
import logging
from datetime import datetime
from dataclasses import dataclass
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    amount: float
    merchant: str
    date: datetime
    account_id: str
    transaction_type: str
    raw_text: str


ACCOUNT_IDS: dict[str, str] = {
    "hdfc_savings": os.getenv("HDFC_SAVINGS_ID", ""),
    "axis_savings": os.getenv("AXIS_SAVINGS_ID", ""),
    "hdfc_cc_3114": os.getenv("HDFC_INFINIA_CC_ID", ""),
    "hdfc_cc_2398": os.getenv("HDFC_RUPAY_CC_ID", ""),
    "axis_cc_0022": os.getenv("AXIS_REWARDS_CC_ID", ""),
    "icici_cc_0018": os.getenv("ICICI_AMAZON_CC_ID", ""),
    "zerodha_coin": os.getenv("ZERODHA_COIN_ID", ""),
    "zerodha_kite": os.getenv("ZERODHA_KITE_ID", ""),
    "vested": os.getenv("VESTED_ID", ""),
}

WATCHED_SENDERS = [
    "alerts@hdfcbank.net",
    "nachautoemailer@hdfcbank.net",
    "alerts@axisbank.com",
    "alerts@axis.bank.in",
    "alerts@icicibank.com",
    "no-reply@alerts.vestedfinance.com",
]


def get_email_body(msg: Message) -> str:
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                        break
                except Exception as e:
                    logger.warning(f"Failed to decode part: {e}")
            elif content_type == "text/html" and not body:
                try:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        html_body = payload.decode(charset, errors="replace")
                        body = re.sub(r"<[^>]+>", " ", html_body)
                        body = re.sub(r"\s+", " ", body).strip()
                except Exception as e:
                    logger.warning(f"Failed to decode HTML part: {e}")
    else:
        try:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")
        except Exception as e:
            logger.warning(f"Failed to decode message: {e}")

    return body


def parse_amount(amount_str: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", amount_str)
    return float(cleaned) if cleaned else 0.0


def try_parse_date(date_str: str, formats: list[str]) -> datetime:
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime.now()


def detect_transaction_type(body: str) -> str:
    """Detect transaction type from email body keywords."""
    body_lower = body.lower()
    
    income_keywords = [
        "credited",
        "received",
        "refund",
        "cashback",
        "reversal",
        "credit alert",
        "amount credited",
        "has been credited",
        "salary",
        "dividend",
    ]
    
    expense_keywords = [
        "debited",
        "spent",
        "debit alert",
        "payment of",
        "purchase",
        "withdrawn",
        "paid to",
        "transaction of inr",
        "has been used for",
    ]
    
    for keyword in income_keywords:
        if keyword in body_lower:
            if f"not {keyword}" not in body_lower and f"failed to {keyword}" not in body_lower:
                return "income"
    
    for keyword in expense_keywords:
        if keyword in body_lower:
            return "expense"
    
    return "expense"


def parse_hdfc_bank_debit(body: str) -> Transaction | None:
    """Pattern: Rs.X has been debited from HDFC Bank Account"""
    pattern = r"Rs\.?([\d,]+\.?\d*)\s+has been debited from (?:your )?HDFC Bank Account"
    match = re.search(pattern, body, re.IGNORECASE)
    if not match:
        return None

    amount = parse_amount(match.group(1))

    merchant = "HDFC Bank Debit"
    towards_match = re.search(r"towards\s+([^.]+)", body, re.IGNORECASE)
    if towards_match:
        merchant = towards_match.group(1).strip()

    date = datetime.now()
    date_match = re.search(r"on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", body)
    if date_match:
        date = try_parse_date(
            date_match.group(1), ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"]
        )

    account_id = ACCOUNT_IDS["hdfc_savings"]
    if not account_id:
        logger.warning("HDFC_SAVINGS_ID not configured, skipping.")
        return None

    return Transaction(
        amount=amount,
        merchant=merchant,
        date=date,
        account_id=account_id,
        transaction_type=detect_transaction_type(body),
        raw_text=body[:500],
    )


def parse_hdfc_cc_debit(body: str) -> Transaction | None:
    """
    Pattern 1: Rs.X is debited from your HDFC Bank Credit Card ending XXXX towards MERCHANT on DATE
    Pattern 2: Thank you for using HDFC Bank Card XXXXXX for Rs. X at MERCHANT on DD-MM-YYYY
    Pattern 3: Rs.X has been debited from your HDFC Bank RuPay Credit Card XXXXXX to MERCHANT on DD-MM-YY
    """
    pattern1 = r"Rs\.?([\d,]+\.?\d*)\s+is debited from your HDFC Bank Credit Card ending\s+(\d{4})\s+towards\s+([^.]+?)\s+on\s+(\d{1,2}\s+\w+,?\s+\d{4})"
    match = re.search(pattern1, body, re.IGNORECASE)

    if match:
        amount = parse_amount(match.group(1))
        last_four = match.group(2)
        merchant = match.group(3).strip()
        date_str = match.group(4).strip().replace(",", "")
        date = try_parse_date(date_str, ["%d %b %Y", "%d %B %Y"])
    else:
        pattern2 = r"HDFC Bank Card\s+\w*(\d{4})\s+for\s+Rs\.?\s*([\d,]+\.?\d*)\s+at\s+(.+?)\s+on\s+(\d{2}-\d{2}-\d{4})"
        match = re.search(pattern2, body, re.IGNORECASE)
        if match:
            last_four = match.group(1)
            amount = parse_amount(match.group(2))
            merchant = match.group(3).strip()
            date_str = match.group(4).strip()
            date = try_parse_date(date_str, ["%d-%m-%Y"])
        else:
            pattern3 = r"Rs\.?([\d,]+\.?\d*)\s+has been debited from your HDFC Bank RuPay Credit Card\s+\w*(\d{4})\s+to\s+(.+?)\s+on\s+(\d{2}-\d{2}-\d{2})"
            match = re.search(pattern3, body, re.IGNORECASE)
            if not match:
                return None

            amount = parse_amount(match.group(1))
            last_four = match.group(2)
            merchant = match.group(3).strip()
            date_str = match.group(4).strip()
            date = try_parse_date(date_str, ["%d-%m-%y"])

    account_key = f"hdfc_cc_{last_four}"
    account_id = ACCOUNT_IDS.get(account_key)
    
    if not account_id:
        logger.warning(f"Unknown HDFC card ending {last_four}, skipping. Add HDFC_CC_{last_four}_ID to config.")
        return None

    return Transaction(
        amount=amount,
        merchant=merchant,
        date=date,
        account_id=account_id,
        transaction_type=detect_transaction_type(body),
        raw_text=body[:500],
    )


def parse_axis_bank_debit(body: str) -> Transaction | None:
    """
    Pattern 1: INR X spent/debited
    Pattern 2: INR X was debited from your A/c no. XX1817
    """
    pattern = r"INR\s+([\d,]+\.?\d*)\s+(?:was\s+debited|spent|debited)"
    match = re.search(pattern, body, re.IGNORECASE)
    if not match:
        return None

    amount = parse_amount(match.group(1))

    merchant = "Axis Bank Debit"
    txn_info_match = re.search(
        r"Transaction\s+Info:\s*(?:UPI/[^/]+/[^/]+/)?(.+?)(?:\n|$)", body, re.IGNORECASE
    )
    if txn_info_match:
        merchant = txn_info_match.group(1).strip()[:100]
    else:
        at_match = re.search(r"(?:at|to|for)\s+([^.]+)", body, re.IGNORECASE)
        if at_match:
            merchant = at_match.group(1).strip()[:100]

    date = datetime.now()
    date_match = re.search(r"(\d{2}-\d{2}-\d{2}),?\s+\d{2}:\d{2}:\d{2}", body)
    if date_match:
        date = try_parse_date(date_match.group(1), ["%d-%m-%y"])
    else:
        date_match = re.search(r"on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", body)
        if date_match:
            date = try_parse_date(
                date_match.group(1), ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"]
            )

    account_id = ACCOUNT_IDS["axis_savings"]
    if not account_id:
        logger.warning("AXIS_SAVINGS_ID not configured, skipping.")
        return None

    return Transaction(
        amount=amount,
        merchant=merchant,
        date=date,
        account_id=account_id,
        transaction_type=detect_transaction_type(body),
        raw_text=body[:500],
    )


def parse_icici_cc_debit(body: str) -> Transaction | None:
    """Pattern: Credit Card XX0018 has been used for a transaction of INR X on DATE. Info: MERCHANT"""
    pattern = r"Credit Card\s+\w*(\d{4})\s+has been used for a transaction of INR\s+([\d,]+\.?\d*)\s+on\s+(\w+\s+\d{1,2},?\s+\d{4}).*?Info:\s*([^.]+)"
    match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    last_four = match.group(1)
    amount = parse_amount(match.group(2))
    date_str = match.group(3).strip().replace(",", "")
    merchant = match.group(4).strip()

    account_key = f"icici_cc_{last_four}"
    account_id = ACCOUNT_IDS.get(account_key)
    
    if not account_id:
        logger.warning(f"Unknown ICICI card ending {last_four}, skipping. Add ICICI_CC_{last_four}_ID to config.")
        return None

    date = try_parse_date(date_str, ["%b %d %Y", "%B %d %Y"])

    return Transaction(
        amount=amount,
        merchant=merchant,
        date=date,
        account_id=account_id,
        transaction_type=detect_transaction_type(body),
        raw_text=body[:500],
    )


def parse_hdfc_nach_debit(body: str) -> Transaction | None:
    """Pattern: Rs.X has been debited from HDFC Bank Account...towards ZERODHA"""
    pattern = r"Rs\.?([\d,]+\.?\d*)\s+has been debited from HDFC Bank Account.*?towards\s+([^/\n]+)"
    match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    amount = parse_amount(match.group(1))
    merchant = match.group(2).strip()

    if "ZERODHA" not in merchant.upper():
        return parse_hdfc_bank_debit(body)

    date = datetime.now()
    date_match = re.search(r"on\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", body)
    if date_match:
        date = try_parse_date(
            date_match.group(1), ["%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"]
        )

    account_id = ACCOUNT_IDS["zerodha_kite"]
    if not account_id:
        logger.warning("ZERODHA_KITE_ID not configured, skipping.")
        return None

    return Transaction(
        amount=amount,
        merchant=merchant,
        date=date,
        account_id=account_id,
        transaction_type=detect_transaction_type(body),
        raw_text=body[:500],
    )


def parse_vested(body: str) -> Transaction | None:
    """
    Pattern 1: Dividend - You have received a $X dividend payout...for your investment in STOCK
    Pattern 2: Buy order - Your buy order for STOCK for $X has been successfully completed
    """
    dividend_pattern = r"received a \$([\d,]+\.?\d*)\s+dividend payout.*?investment in\s+([^.]+?)\."
    match = re.search(dividend_pattern, body, re.IGNORECASE | re.DOTALL)
    
    if match:
        amount = parse_amount(match.group(1))
        stock_name = match.group(2).strip()
        merchant = f"Dividend: {stock_name}"
        
        date = datetime.now()
        date_match = re.search(r"Payout Date:\s*(\d{1,2}/\d{1,2}/\d{4})", body)
        if date_match:
            date = try_parse_date(date_match.group(1), ["%d/%m/%Y", "%m/%d/%Y"])
    else:
        buy_pattern = r"buy order for\s+(.+?)\s+for\s+\$([\d,]+\.?\d*)\s+has been successfully"
        match = re.search(buy_pattern, body, re.IGNORECASE)
        if not match:
            return None
        
        stock_name = match.group(1).strip()
        amount = parse_amount(match.group(2))
        merchant = f"Buy: {stock_name}"
        
        date = datetime.now()
        date_match = re.search(r"Transaction Date:\s*[\d:]+\s*[ap]m\s*(\d{1,2}/\d{1,2}/\d{4})", body, re.IGNORECASE)
        if date_match:
            date = try_parse_date(date_match.group(1), ["%d/%m/%Y", "%m/%d/%Y"])

    account_id = ACCOUNT_IDS["vested"]
    if not account_id:
        logger.warning("VESTED_ID not configured, skipping.")
        return None

    return Transaction(
        amount=amount,
        merchant=merchant,
        date=date,
        account_id=account_id,
        transaction_type=detect_transaction_type(body),
        raw_text=body[:500],
    )


def parse_email(sender: str, body: str) -> Transaction | None:
    sender_lower = sender.lower()

    if "hdfcbank" in sender_lower:
        if "Credit Card" in body:
            return parse_hdfc_cc_debit(body)
        elif "NACH" in body or "nachautoemailer" in sender_lower:
            return parse_hdfc_nach_debit(body)
        else:
            return parse_hdfc_bank_debit(body)
    elif "axisbank" in sender_lower or "axis.bank" in sender_lower:
        return parse_axis_bank_debit(body)
    elif "icicibank" in sender_lower:
        return parse_icici_cc_debit(body)
    elif "vestedfinance" in sender_lower:
        return parse_vested(body)

    return None


def post_to_sure(transaction: Transaction, api_url: str, api_key: str) -> bool:
    endpoint = f"{api_url}/api/transactions"

    payload = {
        "amount": transaction.amount,
        "description": transaction.merchant,
        "date": transaction.date.isoformat(),
        "accountId": transaction.account_id,
        "type": transaction.transaction_type,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Posted transaction: {transaction.amount} - {transaction.merchant}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to post transaction: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"Response: {e.response.text}")
        return False


def connect_imap(host: str, email_addr: str, password: str) -> imaplib.IMAP4_SSL:
    logger.info(f"Connecting to {host}...")
    mail = imaplib.IMAP4_SSL(host)
    mail.login(email_addr, password)
    logger.info("Connected successfully")
    return mail


def fetch_unread_emails(
    mail: imaplib.IMAP4_SSL, folder: str = "INBOX"
) -> list[tuple[str, str, str]]:
    mail.select(folder)
    emails: list[tuple[str, str, str]] = []

    for sender in WATCHED_SENDERS:
        search_criteria = f'(UNSEEN FROM "{sender}")'
        status, messages = mail.search(None, search_criteria)

        if status != "OK" or not messages[0]:
            continue

        message_ids = messages[0].split()
        logger.info(f"Found {len(message_ids)} unread emails from {sender}")

        for msg_id in message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK" or msg_data is None or msg_data[0] is None:
                    continue

                first_item = msg_data[0]
                if not isinstance(first_item, tuple) or len(first_item) < 2:
                    continue

                raw_email = first_item[1]
                if not isinstance(raw_email, bytes):
                    continue

                msg = message_from_bytes(raw_email)
                from_header = msg.get("From", "")
                body = get_email_body(msg)

                if body:
                    emails.append((msg_id.decode(), from_header, body))

            except Exception as e:
                logger.error(f"Error fetching email {msg_id}: {e}")

    return emails


def mark_as_read(mail: imaplib.IMAP4_SSL, msg_id: str) -> bool:
    try:
        mail.store(msg_id, "+FLAGS", "\\Seen")
        return True
    except Exception as e:
        logger.error(f"Failed to mark email {msg_id} as read: {e}")
        return False


def main() -> None:
    imap_host = os.getenv("IMAP_HOST", "imap.gmail.com")
    email_addr = os.getenv("EMAIL_ADDRESS")
    email_password = os.getenv("EMAIL_PASSWORD")
    sure_api_url = os.getenv("SURE_API_URL", "http://localhost:3001")
    sure_api_key = os.getenv("SURE_API_KEY")
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    if not email_addr or not email_password:
        logger.error("EMAIL_ADDRESS and EMAIL_PASSWORD are required")
        sys.exit(1)

    if not sure_api_key and not dry_run:
        logger.error("SURE_API_KEY is required (or set DRY_RUN=true)")
        sys.exit(1)

    logger.info("Starting expense tracker...")
    logger.info(f"Dry run mode: {dry_run}")

    try:
        mail = connect_imap(imap_host, email_addr, email_password)
        emails = fetch_unread_emails(mail)
        logger.info(f"Processing {len(emails)} emails...")

        processed = 0
        failed = 0

        for msg_id, sender, body in emails:
            transaction = parse_email(sender, body)

            if transaction:
                logger.info(
                    f"Parsed: {transaction.amount} - {transaction.merchant} ({transaction.date})"
                )

                if dry_run:
                    logger.info("[DRY RUN] Would post transaction")
                    success = True
                elif sure_api_key:
                    success = post_to_sure(transaction, sure_api_url, sure_api_key)
                else:
                    success = False

                if success:
                    mark_as_read(mail, msg_id)
                    processed += 1
                else:
                    failed += 1
            else:
                mark_as_read(mail, msg_id)
                logger.debug(f"Could not parse email from {sender}")

        mail.close()
        mail.logout()

        logger.info(f"Done! Processed: {processed}, Failed: {failed}")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
