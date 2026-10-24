import argparse
from common import Config
import cv2
def main():
    p=argparse.ArgumentParser();p.add_argument('source',help='Webcam index or MJPEG URL');p.add_argument('--output',default='camera-check.jpg');args=p.parse_args()
    source=int(args.source) if args.source.isdigit() else args.source
    cap=cv2.VideoCapture(source)
    try:
        ok,frame=cap.read()
        if not ok: raise SystemExit('FAIL: no frame; check URL, app, firewall and Wi-Fi')
        if not cv2.imwrite(args.output,frame): raise OSError('Cannot save frame')
        print(f'PASS: received {frame.shape[1]}x{frame.shape[0]}; saved {args.output}')
    finally: cap.release()
if __name__=='__main__': main()
