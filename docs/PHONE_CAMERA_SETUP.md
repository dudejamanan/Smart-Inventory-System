# Phone camera setup

**Current operational procedure:** CURRENT_SETUP.md sections 4–6 now covers learned anchors, reveal markers, calibration pause, both cameras and WhatsApp. The phone supplies a continuous local MJPEG stream; the laptop observes it and saves incident evidence. Older M2 scope notes below are historical.

## Campus network / hotspot option

Campus guest Wi-Fi may block devices from reaching each other even when both show the same network name. For a lab demo, enable a private phone hotspot and connect the laptop to it; use a strong hotspot password. Start the camera-stream app and copy the **actual hotspot-side** video URL it displays (it may differ from your home Wi-Fi IP). Open it on the laptop and run camera_test.py before mounting/calibrating. A hotspot often has no usable internet without mobile data, so test notification connectivity separately; gate/offline alarms do not need internet. Keep the phone charged, ventilated and awake. Do not expose its stream to the public tunnel. v2 reveal/anchor learned calibration arrives at M6; current M2 vision remains the v1 pipeline below.

## 1. Select and connect a stream

1. Install a camera-streaming app from your phone's official app store. Android IP Webcam is a common option. DroidCam may require a desktop client; use its exposed MJPEG URL if supported, or the resulting virtual webcam with an appropriate source adjustment. This app expects a direct OpenCV-readable stream, not the camera app's HTML control page.
2. Connect phone and laptop to the **same trusted Wi-Fi network**. Avoid guest networks with client isolation. A phone hotspot can work if the laptop is connected to it. No port forwarding is needed for the shelf camera.
3. Grant camera/network permissions. Start the app's video server and note its address, for example `http://192.168.1.25:8080`. In IP Webcam the MJPEG endpoint is commonly `http://192.168.1.25:8080/video`; verify the exact endpoint in that app's interface/help.
4. Open the address in the laptop browser, choose its video view, and confirm motion is recent. Success: moving your hand near the shelf appears quickly. If the page loads but a saved URL returns HTML, copy the actual video-stream endpoint.
5. Keep the camera local; do not expose an unauthenticated phone server to the internet. If using app credentials, keep them in .env only. Some OpenCV builds/streams do not support every authentication scheme; test before mounting the phone.

## 2. Stable picture

1. Plug in the phone charger and mount it firmly about 40–60 cm from the shelf as a starting distance. Do not obstruct ventilation or leave it overheating.
2. Choose landscape orientation and disable automatic rotation. Start around 1280x720 at 10–15 fps; the app processes approximately 960 pixels wide at 10 fps. Lower bandwidth settings if lag grows.
3. Disable battery optimization for the streaming app and keep the screen/server active. Test with the phone screen in its intended demo state for at least ten minutes.
4. Lock focus on the marker plane and lock exposure/white balance if supported. Otherwise use steady diffuse light and avoid people casting large shadows. Ensure the smallest marker is sharp; glare, tape shine and motion blur interfere with detection.
5. After each restart check whether the phone IP changed. A router DHCP reservation can stabilize it. Update SHELF_STREAM_URL if necessary.

## 3. Test on the laptop

With the app stopped, run from the repository root:

```powershell
.\.venv\Scripts\python tools/camera_test.py http://192.168.1.25:8080/video --output data/phone-check.jpg
```

Create data first if needed. Success: the tool prints received dimensions and saves a current image; open the image and confirm all shelf markers are visible. For the gate webcam, use `tools/camera_test.py 0 --output data/gate-check.jpg`. Close other apps using the webcam.

Set `SHELF_STREAM_URL=http://.../video` in .env and restart real mode. Success: Live shows the actual shelf; System health becomes OK. If disconnected, the source reconnects with increasing waits up to five seconds. After three seconds without new frames it reports OFFLINE. Low brightness/texture for two seconds can report COVERED. Fix the stream before calibrating.

## 4. Network troubleshooting

1. Confirm both devices' Wi-Fi names, phone IP and port. Turn off a VPN temporarily only if your network policy permits it. Check that the app server is running.
2. If the browser cannot reach the phone, check guest isolation, phone sleep, Wi-Fi permissions and firewall. Permit local app traffic on a private network only; do not disable the entire firewall.
3. If the browser works but OpenCV fails, choose MJPEG instead of a proprietary player or HLS page. Use the test tool's direct stream URL.
4. If the image is delayed, close other stream viewers, lower resolution/FPS, improve Wi-Fi signal and check temperature/power saving. Success means frames are recent after several minutes, not just immediately after connection.
5. Recalibrate after changing resolution, orientation, mount or lighting. Test phone disconnect/reconnect and COVERED behavior before the presentation.
