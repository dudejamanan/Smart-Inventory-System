import cv2
import numpy as np
from app.config import Config
from app.services.frames import SyntheticShelfSource
from app.services.vision import detect,classify,crop,Debounce,CameraHealth

def test_real_marker_detection_and_empty_logic():
    source=SyntheticShelfSource(); roi=(.06,.25,.26,.55)
    empty=crop(source.empty(),roi)
    frame=source.grab()
    assert set(detect(frame))=={0,1,2,40,41}
    assert classify(frame,roi,0,detect(frame),empty,12)=='PRESENT'
    source.states[0]='absent'; frame=source.grab()
    assert classify(frame,roi,0,detect(frame),empty,12)=='ABSENT'
    source.states[0]='occluded'; frame=source.grab()
    assert classify(frame,roi,0,detect(frame),empty,12)=='OCCLUDED'
    assert classify(frame,roi,0,{},None,12)=='UNKNOWN'

def test_debounce():
    d=Debounce()
    for _ in range(3): assert d.vote('PRESENT')=='UNKNOWN'
    assert d.vote('PRESENT')=='PRESENT'
    assert d.vote('ABSENT')=='PRESENT'
    for _ in range(3): d.vote('ABSENT')
    assert d.state=='ABSENT'

def test_camera_health():
    c=Config(); health=CameraHealth(c); src=SyntheticShelfSource(); frame=src.grab()
    assert health.update(frame,0,0,detect(frame))=='OK'
    assert health.update(None,0,4,{})=='OFFLINE'
    black=np.zeros_like(frame)
    assert health.update(black,5,5,{})=='OK'
    assert health.update(black,7.1,7.1,{})=='COVERED'
    assert health.update(frame,8,8,detect(frame))=='OK'
    src.moved=True; moved=src.grab()
    health.update(moved,9,9,detect(moved))
    assert health.update(moved,12.1,12.1,detect(moved))=='MOVED'
