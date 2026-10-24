"""Same command cases can target simulation or a real UNO (requires card taps)."""
import argparse
import time
from common import connect,wait_for,encode
from app.sim.arduino import SimulatedArduino

CASES=[({'t':'SYNC','state':'OUT'},None),
       ({'t':'REMOVAL','slot':2},('ALARM','why','SHELF_BREACH')),
       ({'t':'ACK'},('ALARM_OFF','by','ACK')),
       ({'t':'ALARM','on':1},('ALARM','why','PC_CMD')),
       ({'t':'ACK'},('ALARM_OFF','by','ACK'))]

def main():
    p=argparse.ArgumentParser();p.add_argument('--port');p.add_argument('--simulate',action='store_true');args=p.parse_args()
    b=SimulatedArduino() if args.simulate else connect(args.port)
    try:
        for message,expected in CASES:
            if args.simulate:
                b.drain();b.receive(message);events=b.drain()
                if expected: assert any(e['t']==expected[0] and e.get(expected[1])==expected[2] for e in events),events
            else:
                b.write(encode(message))
                if expected: wait_for(b,lambda e:e['t']==expected[0] and e.get(expected[1])==expected[2])
            print('PASS',message['t'],expected or '')
        if not args.simulate:
            uid=None
            for state in ['IN','OUT']:
                print(f'Tap the same card for SESSION {state} (20 second limit)')
                scan=wait_for(b,lambda e:e['t']=='SCAN',20)
                if uid: assert uid==scan['uid'],'Use the same card'
                uid=scan['uid'];b.write(encode({'t':'AUTH','seq':scan['seq'],'ok':1}))
                wait_for(b,lambda e:e['t']=='SESSION' and e['state']==state)
                print('PASS SESSION',state)
            for n in [1,2,3]:
                print(f'Tap/remove a card for failed attempt {n} (wait 1.5 seconds between taps)')
                scan=wait_for(b,lambda e:e['t']=='SCAN',20)
                b.write(encode({'t':'AUTH','seq':scan['seq'],'ok':0}))
                wait_for(b,lambda e:e['t']=='FAIL' and e['n']==n)
            wait_for(b,lambda e:e['t']=='ALARM' and e['why']=='GATE_3_FAIL')
            print('PASS three failures -> alarm')
    finally:
        if not args.simulate: b.write(encode({'t':'ACK'}));b.close()

if __name__=='__main__': main()
