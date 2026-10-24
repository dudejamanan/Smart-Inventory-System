// One-second green, red, buzzer, then silent. Repeat. No delay().
// Copy into a folder named led_buzzer_test before opening in Arduino IDE.
#ifndef BUZZER_ACTIVE
#define BUZZER_ACTIVE 1
#endif
void setup(){pinMode(7,OUTPUT);pinMode(8,OUTPUT);pinMode(6,OUTPUT);Serial.begin(115200);}
void loop(){
  byte phase=(millis()/1000)%4;digitalWrite(7,phase==0);digitalWrite(8,phase==1);
#if BUZZER_ACTIVE
  digitalWrite(6,phase==2);
#else
  if(phase==2)tone(6,2200);else noTone(6);
#endif
}
