// Optional A0 button to GND; D4 is reader #2 SS in the supplied circuit.
const byte BUTTON=A0;bool raw=false,stable=false;unsigned long changed=0,pressedAt=0;
void setup(){pinMode(BUTTON,INPUT_PULLUP);Serial.begin(115200);}
void loop(){unsigned long now=millis();bool pressed=digitalRead(BUTTON)==LOW;
  if(pressed!=raw){raw=pressed;changed=now;}
  if(raw!=stable&&(unsigned long)(now-changed)>=30){stable=raw;if(stable)pressedAt=now;else Serial.println((unsigned long)(now-pressedAt)>=1500?F("LONG"):F("SHORT"));}
}
