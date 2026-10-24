# Shelf calibration

## 1. Prepare the scene

1. Finish PHONE_CAMERA_SETUP and HARDWARE_GUIDE section 9. Keep the mount, lamp, orientation, focus and exposure fixed. Success: camera OK and all markers readable.
2. Add inventory in Inventory: one meaningful item name and unique marker ID 0–29 per box. Print using `python tools/print_markers.py --size-cm 5 --output data/markers.pdf`, print at actual size, and measure the black square. Fixed shelf anchors use 40–49; never assign them to boxes.
3. Add shelf slots in Inventory with name, marker ID and linked item ID. The initial normalized ROI values may be approximate; Calibration replaces them. A normalized x/y is the fraction of image width/height from the top-left. For example x=.1, y=.2, w=.25, h=.5 spans 10–35% of width and 20–70% of height.

## 2. Draw and save each ROI

1. Open Calibration and choose the slot by name. Put its box in the normal position. Confirm its marker ID matches the box and inventory record.
2. Drag a rectangle around the slot's box footprint in the live frame. Include the marker and expected empty surface, but avoid adjacent boxes, moving people and distant background. The overlay shows the chosen rectangle. On touch devices drag with one finger.
3. Click **Save selected region**. Success: no error banner; the slot's ROI values update. Saving a new region invalidates its previous empty reference, so always do the next section.
4. Repeat for every slot. Keep slots separated enough that a box in one does not hide another marker. Marker center must be inside its assigned region for PRESENT.

## 3. Capture the empty reference

1. Select a slot. Remove only its box, remove hands from the image, and wait for lighting/exposure to settle. Keep the phone still. Empty means the actual shelf surface, not a covered lens or a hand.
2. Click **Capture empty reference**. Success: the empty ROI JPEG is saved and the API reports success. No modal confirmation is required; make sure the physical scene is correct before clicking.
3. Wait approximately 0.5–1 s. Empty slot should show ABSENT. In real unattended mode this can create a security incident and buzzer; perform calibration with an authorized session active, or warn people and acknowledge the test incident.
4. Replace the box. Success: PRESENT after at least four agreeing votes. Cover its marker with your hand without taking the box away: OCCLUDED should appear, and after >2 s unattended only a WARNING should be created.
5. Repeat for every slot. Finish with boxes present, gate checked out, no active alarm and health OK.

## 4. Tune conservatively

`EMPTY_DIFF_THRESH=12` is a starting mean absolute difference on blurred grayscale pixels (0–255). Lowering it makes ABSENT harder to reach and increases OCCLUDED; raising it makes ABSENT easier and may misclassify a hand/box as empty. First fix lighting and recapture references before changing thresholds.

1. Test each slot empty and verify ABSENT repeatedly under normal lighting. If empty becomes OCCLUDED, recapture with stable exposure, then try raising threshold in small steps (e.g. 2).
2. Cover a marker while leaving the box present. If it becomes ABSENT, lower threshold or improve ROI/background contrast. A textureless dark box can resemble an empty shelf; change the physical setup if threshold tuning cannot separate them.
3. Debounce defaults N=4, M=5 at 10 fps. More votes reduce flicker but increase response delay; always keep 1 <= N <= M. Do not hide persistent camera problems by making debounce extremely slow.
4. Camera COVERED thresholds use brightness and Laplacian texture. A naturally dark/blank scene can trigger a warning; add lighting and visible fixed features, then adjust .env thresholds only with measured observations. Anchors drifting more than 4% normalized distance or vanishing for 3 s cause MOVED. Restart establishes the anchor baseline, so verify placement first.
5. Record every changed value, conditions and result in TEST_PLAN. Change one parameter at a time. Settings-page values persist over .env; do not assume editing .env replaced them.

## 5. Calibration checklist

- [ ] Phone stable, charged, orientation fixed, live frames current.
- [ ] Lighting steady; exposure/focus locked if possible.
- [ ] Item IDs unique 0–29 and marker faces matte, flat, at least 4 cm.
- [ ] Anchors 40–49 fixed to structure, visible and separated.
- [ ] Slot marker/item assignments correct; ROI does not include neighbors.
- [ ] New empty reference captured after ROI/lighting/camera changes.
- [ ] Each box returns PRESENT, empty slot ABSENT, hand OCCLUDED.
- [ ] Unattended removal alarms; authorized removal is attributed without alarm.
- [ ] Occlusion and camera problems give warnings without a buzzer.
- [ ] Results recorded; all test alarms acknowledged before the demonstration.
