import time
import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator
from app.config import Config
from app.main import create_app
from app.db.models import Incident,Notification

@pytest.fixture
def api_client(tmp_path):
    c=Config(data_dir=tmp_path,admin_password='testing-password',twilio_auth_token='signature-test-token',
             twilio_account_sid='',public_base_url='https://warehouse.example',owner_whatsapp_to='whatsapp:+911234567890')
    app=create_app(c,simulate=True,start_services=False)
    with TestClient(app) as client:
        yield client,app.state.runtime,c

def login(client):
    client.headers['X-Warehouse-Request']='1'
    assert client.post('/api/login',json={'password':'testing-password'}).status_code==200

def test_auth_crud_settings_and_calibration(api_client):
    client,r,c=api_client
    assert client.get('/api/status').status_code==401
    assert client.post('/api/login',json={'password':'bad'}).status_code==401
    login(client)
    assert client.get('/api/settings').status_code==200
    response=client.post('/api/personnel',json={'uid':'AABBCCDD','name':'Test worker'})
    assert response.status_code==200,response.text
    ident=response.json()['id']
    assert client.put(f'/api/personnel/{ident}',json={'uid':'AABBCCDD','name':'Renamed','active':False}).status_code==200
    assert 'AABBCCDD' not in r.engine.whitelist
    assert client.post('/api/personnel',json={'uid':'../bad','name':'Invalid'}).status_code==422
    assert client.post('/api/personnel',json={'uid':'AABBCCDD','name':'Duplicate'}).status_code==409
    assert client.delete(f'/api/personnel/{ident}').status_code==200
    assert client.put('/api/settings',json={'fail_limit':4}).json()['fail_limit']==4
    assert client.put('/api/settings',json={'admin_password':'exposed'}).status_code==422
    assert client.put('/api/settings',json={'debounce_n':8,'debounce_m':2}).status_code==422
    assert client.get('/api/markers/0.png').headers['content-type']=='image/png'
    assert client.get('/api/markers/39.png').status_code==422
    assert client.post('/api/calibration/slot',json={'slot_id':1,'roi_x':.9,'roi_y':0,'roi_w':.5,'roi_h':.5}).status_code==422
    assert client.post('/api/test/red',headers={'Origin':'https://evil.example'}).status_code==403
    with client.websocket_connect('/ws') as ws:
        # Authenticated live status is delivered even when hardware services are stopped.
        assert ws.receive_json()['type']=='STATUS'

def test_twilio_signatures_and_media(api_client):
    client,r,c=api_client
    body={'From':c.owner_whatsapp_to,'Body':'hello'}
    path='/webhooks/twilio/inbound'
    assert client.post(path,data=body).status_code==403
    signature=RequestValidator(c.twilio_auth_token).compute_signature(c.public_base_url+path,body)
    assert client.post(path,data=body,headers={'X-Twilio-Signature':signature}).status_code==200
    assert r.notifications.session_remaining()>86390
    with r.store.session() as s:
        i=Incident(kind='test',severity='WARNING');s.add(i);s.flush()
        n=Notification(incident_id=i.id,to='owner',kind='text',provider_sid='SMtest');s.add(n);s.flush();nid=n.id
    path='/webhooks/twilio/status';body={'MessageSid':'SMtest','MessageStatus':'failed','ErrorCode':'63016'}
    signature=RequestValidator(c.twilio_auth_token).compute_signature(c.public_base_url+path,body)
    assert client.post(path,data=body,headers={'X-Twilio-Signature':signature}).status_code==200
    with r.store.session() as s: assert s.get(Notification,nid).status=='FAILED_SESSION_EXPIRED'
    photo=c.data_dir/'sample.jpg';photo.write_bytes(b'jpeg')
    url='/media/'+r.signer.sign(photo)+'.jpg'
    assert client.get(url).status_code==200
    assert client.get(url+'x').status_code!=200
    assert client.get('/media/invalid.jpg').status_code==403

def test_incident_ack_sends_before_db_and_stream_protection(api_client):
    client,r,c=api_client
    assert client.get('/api/shelf/stream').status_code==401
    login(client)
    ident=r.engine.incident('TEST','WARNING')
    assert client.post(f'/api/incidents/{ident}/ack').status_code==200
    assert client.get(f'/api/incidents/{ident}').json()['status']=='ACKNOWLEDGED'
    assert not r.serial.tx.empty()

def test_e2e_scenarios(tmp_path):
    from fake_scenarios import run_scenarios
    run_scenarios(tmp_path)
