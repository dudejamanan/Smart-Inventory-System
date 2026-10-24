"""Explicitly send one text and one photo through the configured real Twilio SDK.
Run only after joining the sandbox and sending an inbound message to the app.
"""
import argparse
import time
from pathlib import Path
from common import Config
from app.db.store import Store
from app.db.models import Incident
from app.services.notifier import MediaSigner,NotificationQueue,TwilioNotifier

def main():
    p=argparse.ArgumentParser();p.add_argument('--photo',type=Path,required=True);args=p.parse_args()
    c=Config()
    if not all([c.twilio_account_sid,c.twilio_auth_token,c.twilio_whatsapp_from,c.owner_whatsapp_to,c.public_base_url,c.media_url_secret]):
        raise SystemExit('FAIL: complete Twilio and public-media settings in .env first')
    if not args.photo.is_file(): raise SystemExit('FAIL: photo does not exist')
    store=Store(c)
    queue=NotificationQueue(store,c,MediaSigner(c.data_dir,c.media_url_secret),TwilioNotifier(c))
    if queue.session_remaining()<=0: raise SystemExit('FAIL: send WhatsApp hello to the sandbox and verify inbound webhook first')
    with store.session() as s:
        incident=Incident(kind='MANUAL_NOTIFICATION_TEST',severity='WARNING',notes='Operator requested Twilio test')
        s.add(incident);s.flush();ident=incident.id
    queue.photo=lambda source,seq:args.photo
    queue.enqueue(ident,'MANUAL_NOTIFICATION_TEST',None,'gate',None)
    queue.process(queue.q.get_nowait())
    from sqlalchemy import select
    from app.db.models import Notification
    with store.session() as s:
        rows=s.scalars(select(Notification).where(Notification.incident_id==ident)).all()
        for row in rows: print(f'{row.kind}: status={row.status}, SID={row.provider_sid}, attempts={row.attempts}, error={row.error_code}')
        failed=any(row.status.startswith('FAILED') for row in rows)
    print('Check the owner phone and dashboard delivery callbacks; queued does not mean delivered.')
    raise SystemExit(1 if failed else 0)

if __name__=='__main__': main()
