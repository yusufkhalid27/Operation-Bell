# Gmail IMAP OTP extractor (Python, OAuth2)

Huge news for those with large backs! Want free Taco Bell? Use this minimal script that connects to Gmail over IMAP (XOAUTH2) and prints an OTP from a matching email.

## Gmail notes (Jan 2025 change)

For personal Google Accounts, starting **January 2025** Gmail no longer shows the “Enable IMAP / Disable IMAP” toggle.
IMAP access is **always on**.

Gmail does **not** allow third-party apps to use your normal Google password (“basic auth”). Use **OAuth2/XOAUTH2**.

## Setup

1. Create a Google Cloud project
2. Configure **OAuth consent screen**
3. Create an **OAuth Client ID** of type **Desktop app**
4. Download the JSON and save it as `credentials.json` in this folder

Install deps:

```powershell
pip install -r .\requirements.txt
```

## Run

This prints only the OTP to stdout.

```powershell
python .\otp_imap.py \
  --user "you@gmail.com" \
  --recipient "you+alias@gmail.com" \
  # (optional) defaults:
  # --sender "noreply@info.tacobell.com"
  # --subject "Finish creating your account"
```

Tip: if you don't want to pass `--user` every time, set `DEFAULT_USER` near the top of `otp_imap.py`.

Options:

- Add `--include-seen` to also search read emails
- Add `--mark-seen` to mark the matched email read

## Polling (Python)

If you want to *wait* for the email to arrive (instead of running the script repeatedly), use `wait_for_otp()`:

```python
from otp_imap import wait_for_otp

otp = wait_for_otp(
  recipient="you+alias@gmail.com",
  include_seen=True,
  mark_seen=True,
  timeout_seconds=120,
  poll_interval_seconds=3,
)

if otp is None:
  raise RuntimeError("Timed out waiting for OTP")

print("OTP:", otp)
```

## Troubleshooting

### `Error 403: access_denied`

- In Google Cloud Console → **APIs & Services** → **OAuth consent screen**:
  - Fill required fields (app name, support email, developer contact)
  - If **Publishing status** is **Testing**, add your Gmail under **Test users**
- Sign in with the same account you pass as `--user`

Note: IMAP over OAuth uses the restricted scope `https://mail.google.com/`.
