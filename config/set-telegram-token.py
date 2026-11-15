#!/usr/bin/env python3
"""Save a Telegram token interactively without echoing it or changing other settings."""
from getpass import getpass
from pathlib import Path
import os
import re
import tempfile

path = Path('/opt/containers/vinted-minipc-watcher/.env')
text = path.read_text()
if len(re.findall(r'^TELEGRAM_BOT_TOKEN=', text, re.M)) != 1:
    raise SystemExit('Expected exactly one TELEGRAM_BOT_TOKEN setting; no changes made.')
token = getpass('Paste bot token (hidden), then press Enter: ').strip()
if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token):
    raise SystemExit('Token format invalid; no changes made.')
text = re.sub(r'^TELEGRAM_BOT_TOKEN=.*$', lambda _: 'TELEGRAM_BOT_TOKEN=' + token, text, flags=re.M)
fd, name = tempfile.mkstemp(prefix='.env-setup-', dir=path.parent)
try:
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, path)
finally:
    Path(name).unlink(missing_ok=True)
print('Token saved securely. Open your Telegram bot and tap Start, then tell me you are ready.')
