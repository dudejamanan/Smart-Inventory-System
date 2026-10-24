"""Interactive electrical test: no PASS without a human observation."""
import argparse
from common import connect,wait_for,encode

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port');args=parser.parse_args()
    board=connect(args.port);passed=True
    try:
        for what in ['green','red','buzzer']:
            board.write(encode({'t':'TEST','what':what}))
            answer=input(f'Did {what} turn on for about 1 second? [y/N] ').strip().lower()
            ok=answer=='y';passed &= ok;print(f'{what}: '+('PASS (observed by operator)' if ok else 'FAIL'))
        print('Tap a card within 20 seconds. It will be denied during this test.')
        event=wait_for(board,lambda e:e['t']=='SCAN',20)
        print('UID:',event['uid']);board.write(encode({'t':'AUTH','seq':event['seq'],'ok':0}))
        wait_for(board,lambda e:e['t']=='FAIL')
        print('Serial scan and denial exchange: PASS')
    except Exception as exc: passed=False;print('FAIL:',exc)
    finally: board.write(encode({'t':'ACK'}));board.close()
    raise SystemExit(0 if passed else 1)

if __name__=='__main__': main()
