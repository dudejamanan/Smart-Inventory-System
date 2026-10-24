"""Generate local secrets once. Existing .env is never overwritten."""
import getpass
import secrets
from pathlib import Path

root=Path(__file__).resolve().parents[1]
target=root/'.env'
if target.exists(): raise SystemExit('.env already exists; edit it locally. Nothing changed.')
password=getpass.getpass('Choose admin password (12+ characters): ')
if len(password)<12 or any(c in password for c in ['\n','\r','"']): raise SystemExit('Use 12+ characters without quotes/newlines')
text=(root/'.env.example').read_text()
for key,value in [('ADMIN_PASSWORD',password),('COOKIE_SECRET',secrets.token_hex(32)),('MEDIA_URL_SECRET',secrets.token_hex(32))]:
    text=text.replace(key+'=\n',key+'="'+value+'"\n')
target.write_text(text)
print('Created .env with generated secrets. Secrets are not printed.')
