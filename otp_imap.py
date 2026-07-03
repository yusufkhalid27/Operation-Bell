import argparse
import html
import importlib
import imaplib
import os
import re
import sys
import time
from email import message_from_bytes
from email.message import Message
from email.policy import default
from email.utils import getaddresses
from typing import Any, Iterable, Optional


SCOPE = "https://mail.google.com/"
DEFAULT_USER = "liamprint4@gmail.com"  # Optional: set to your Gmail address to avoid passing --user every time.
DEFAULT_SENDER = "noreply@info.tacobell.com"
DEFAULT_SUBJECT = "Finish creating your account"


def _load_or_create_credentials(credentials_path: str, token_path: str) -> Any:
    try:
        google_requests = importlib.import_module("google.auth.transport.requests")
        google_credentials = importlib.import_module("google.oauth2.credentials")
        google_oauth_flow = importlib.import_module("google_auth_oauthlib.flow")

        Request = getattr(google_requests, "Request")
        Credentials = getattr(google_credentials, "Credentials")
        InstalledAppFlow = getattr(google_oauth_flow, "InstalledAppFlow")
    except Exception as e:
        raise ImportError("Install deps: pip install -r requirements.txt") from e

    creds: Any = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, [SCOPE])

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Missing {credentials_path}. Download OAuth client JSON (Desktop app) and save it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, [SCOPE])
            creds = flow.run_local_server(port=0)

        if creds is None:
            raise RuntimeError("OAuth flow did not return credentials")

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def _build_xoauth2_raw(user: str, access_token: str) -> bytes:
    # imaplib.authenticate() base64-encodes callback output.
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")


def connect_gmail_imap_xoauth2(user: str, access_token: str) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    xoauth2_raw = _build_xoauth2_raw(user, access_token)

    def auth_callback(_: bytes) -> bytes:
        return xoauth2_raw

    typ, _ = imap.authenticate("XOAUTH2", auth_callback)
    if typ != "OK":
        raise RuntimeError("XOAUTH2 authentication failed")
    return imap


def _addresses_from_headers(msg: Message, header_names: Iterable[str]) -> set[str]:
    values: list[str] = []
    for name in header_names:
        raw_list = msg.get_all(name, [])
        if isinstance(raw_list, str):
            values.append(raw_list)
        else:
            values.extend([str(x) for x in raw_list])

    addrs = {addr.strip().casefold() for _, addr in getaddresses(values) if addr}

    for name in header_names:
        for raw in msg.get_all(name, []):
            raw_s = str(raw).strip()
            if "@" in raw_s and " " not in raw_s and "<" not in raw_s:
                addrs.add(raw_s.casefold())

    return addrs


def _decode_text_part(part: Message) -> Optional[str]:
    payload = part.get_payload(decode=True)
    if payload is None:
        return None

    if isinstance(payload, str):
        return payload

    if isinstance(payload, memoryview):
        payload_bytes = payload.tobytes()
    elif isinstance(payload, (bytes, bytearray)):
        payload_bytes = bytes(payload)
    else:
        return str(payload)

    charset = part.get_content_charset() or "utf-8"
    try:
        return payload_bytes.decode(charset, errors="replace")
    except Exception:
        return payload_bytes.decode("utf-8", errors="replace")


def _get_message_text(msg: Message) -> str:
    text_plain: Optional[str] = None
    text_html: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and text_plain is None:
                text_plain = _decode_text_part(part)
            elif ctype == "text/html" and text_html is None:
                text_html = _decode_text_part(part)
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            text_plain = _decode_text_part(msg)
        elif ctype == "text/html":
            text_html = _decode_text_part(msg)

    if text_plain:
        return text_plain
    if text_html:
        return html.unescape(re.sub(r"<[^>]+>", " ", text_html))
    return ""


def extract_otp(message_text: str) -> Optional[str]:
    # Prefer the common phrase: "Your One-Time Code is 458107"
    m = re.search(r"(?i)\bYour\s+One-Time\s+Code\s+is\s+([0-9]{6})\b", message_text)
    if m:
        return m.group(1)

    # Then a 6-digit code near common keywords.
    m = re.search(r"(?is)(verification|verify|one[- ]time|otp|code)[^0-9]{0,40}([0-9]{6})", message_text)
    if m:
        return m.group(2)

    # Then any standalone 6-digit code.
    m = re.search(r"\b([0-9]{6})\b", message_text)
    if m:
        return m.group(1)

    return None


def _imap_quote(value: str) -> str:
    # Quote a string for IMAP commands (e.g., SEARCH SUBJECT "... with spaces ...").
    # Escape backslashes and double quotes.
    safe = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{safe}"'


def _uid_search(imap: imaplib.IMAP4_SSL, unseen_only: bool, sender: str, subject: str) -> list[bytes]:
    criteria: list[str] = []
    if unseen_only:
        criteria.append("UNSEEN")
    criteria.extend(["FROM", _imap_quote(sender)])
    criteria.extend(["SUBJECT", _imap_quote(subject)])

    typ, data = imap.uid("SEARCH", "CHARSET", "UTF-8", *criteria)
    if typ != "OK" or not data:
        return []
    return data[0].split()


def _fetch_header(imap: imaplib.IMAP4_SSL, uid: bytes) -> Message:
    uid_str = uid.decode("ascii", errors="ignore")
    typ, data = imap.uid(
        "FETCH",
        uid_str,
        "(BODY.PEEK[HEADER.FIELDS (FROM TO CC DELIVERED-TO X-ORIGINAL-TO X-ENVELOPE-TO SUBJECT DATE)])",
    )
    if typ != "OK" or not data or data[0] is None:
        raise RuntimeError("Failed to fetch headers")
    raw = data[0][1]
    if not isinstance(raw, (bytes, bytearray)):
        raise RuntimeError("Unexpected header payload type")
    return message_from_bytes(bytes(raw), policy=default)


def _fetch_full_message(imap: imaplib.IMAP4_SSL, uid: bytes) -> Message:
    uid_str = uid.decode("ascii", errors="ignore")
    typ, data = imap.uid("FETCH", uid_str, "(RFC822)")
    if typ != "OK" or not data or data[0] is None:
        raise RuntimeError("Failed to fetch message")
    raw = data[0][1]
    if not isinstance(raw, (bytes, bytearray)):
        raise RuntimeError("Unexpected RFC822 payload type")
    return message_from_bytes(bytes(raw), policy=default)


def _mark_seen_uid(imap: imaplib.IMAP4_SSL, uid: bytes) -> None:
    uid_str = uid.decode("ascii", errors="ignore")
    imap.uid("STORE", uid_str, "+FLAGS", "\\Seen")


def find_otp(
    *,
    user: Optional[str] = None,
    recipient: str,
    sender: str = DEFAULT_SENDER,
    subject: str = DEFAULT_SUBJECT,
    credentials: str = "credentials.json",
    token: str = "token.json",
    mailbox: str = "INBOX",
    include_seen: bool = False,
    mark_seen: bool = False,
    max_candidates: int = 50,
) -> Optional[str]:
    """Return the OTP string if found, else None.

    This is the programmatic API; it does not print.
    """

    if user is None:
        user = DEFAULT_USER
    if not user:
        raise ValueError("Missing Gmail user. Pass user=... or set DEFAULT_USER in otp_imap.py")

    creds = _load_or_create_credentials(credentials, token)
    access_token = getattr(creds, "token", None)
    if not access_token:
        raise RuntimeError("no access token available")

    unseen_only = not include_seen

    imap: Optional[imaplib.IMAP4_SSL] = None
    try:
        imap = connect_gmail_imap_xoauth2(user, access_token)
        typ, _ = imap.select(mailbox)
        if typ != "OK":
            raise RuntimeError(f"failed to select mailbox {mailbox}")

        uids = _uid_search(imap, unseen_only=unseen_only, sender=sender, subject=subject)
        if not uids:
            return None

        recipient_cf = recipient.casefold().strip()
        sender_cf = sender.casefold().strip()
        subject_cf = subject.casefold().strip()

        checked = 0
        for uid in reversed(uids):
            header_msg = _fetch_header(imap, uid)

            from_addrs = _addresses_from_headers(header_msg, ["From"])
            if sender_cf not in from_addrs:
                continue

            header_subject = str(header_msg.get("Subject", "")).casefold().strip()
            if header_subject != subject_cf:
                continue

            rcpt_addrs = _addresses_from_headers(
                header_msg,
                ["To", "Cc", "Delivered-To", "X-Original-To", "X-Envelope-To"],
            )
            if recipient_cf not in rcpt_addrs:
                continue

            full_msg = _fetch_full_message(imap, uid)
            text = _get_message_text(full_msg)
            otp = extract_otp(text)
            if otp:
                if mark_seen:
                    _mark_seen_uid(imap, uid)
                return otp

            checked += 1
            if checked >= max_candidates:
                break

        return None

    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass


def wait_for_otp(
    *,
    user: Optional[str] = None,
    recipient: str,
    sender: str = DEFAULT_SENDER,
    subject: str = DEFAULT_SUBJECT,
    credentials: str = "credentials.json",
    token: str = "token.json",
    mailbox: str = "INBOX",
    include_seen: bool = False,
    mark_seen: bool = False,
    max_candidates: int = 50,
    timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 3.0,
) -> Optional[str]:
    """Poll until an OTP is found or timeout elapses.

    Returns the OTP string, or None on timeout.
    """

    if timeout_seconds <= 0:
        return find_otp(
            user=user,
            recipient=recipient,
            sender=sender,
            subject=subject,
            credentials=credentials,
            token=token,
            mailbox=mailbox,
            include_seen=include_seen,
            mark_seen=mark_seen,
            max_candidates=max_candidates,
        )

    interval = max(0.25, float(poll_interval_seconds))
    deadline = time.monotonic() + float(timeout_seconds)

    while True:
        otp = find_otp(
            user=user,
            recipient=recipient,
            sender=sender,
            subject=subject,
            credentials=credentials,
            token=token,
            mailbox=mailbox,
            include_seen=include_seen,
            mark_seen=mark_seen,
            max_candidates=max_candidates,
        )
        if otp:
            return otp

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None

        time.sleep(min(interval, remaining))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find an OTP email and print the OTP (Gmail IMAP + OAuth2).")
    default_user = DEFAULT_USER if DEFAULT_USER else None
    parser.add_argument(
        "--user",
        default=default_user,
        required=default_user is None,
        help="Your Gmail address (mailbox you sign into). Defaults to DEFAULT_USER in otp_imap.py",
    )
    parser.add_argument("--recipient", required=True, help="Exact recipient address/alias to match")
    parser.add_argument("--sender", default=DEFAULT_SENDER, help="Sender address to match")
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="Exact subject to match")
    parser.add_argument("--credentials", default="credentials.json", help="OAuth client JSON (Desktop app)")
    parser.add_argument("--token", default="token.json", help="Saved user token cache")
    parser.add_argument("--mailbox", default="INBOX", help="Mailbox to search")
    parser.add_argument("--include-seen", action="store_true", help="Search read emails too")
    parser.add_argument("--mark-seen", action="store_true", help="Mark the matched email read")
    parser.add_argument("--max-candidates", type=int, default=50, help="Max newest candidates to inspect")

    args = parser.parse_args(argv)

    try:
        otp = find_otp(
            user=args.user,
            recipient=args.recipient,
            sender=args.sender,
            subject=args.subject,
            credentials=args.credentials,
            token=args.token,
            mailbox=args.mailbox,
            include_seen=args.include_seen,
            mark_seen=args.mark_seen,
            max_candidates=args.max_candidates,
        )
    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if not otp:
        return 1

    print(otp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())