#include <EEPROM.h>
// Scratch address 900 is outside the gate whitelist and boot-counter regions.
void setup(){Serial.begin(115200);byte saved[4];bool ok=true;
  for(byte i=0;i<4;i++){saved[i]=EEPROM.read(900+i);EEPROM.update(900+i,0x51+i);}
  for(byte i=0;i<4;i++)if(EEPROM.read(900+i)!=0x51+i)ok=false;
  for(byte i=0;i<4;i++)EEPROM.update(900+i,saved[i]);
  Serial.println(ok?F("EEPROM scratch round trip PASS; original bytes restored"):F("EEPROM FAIL"));
}
void loop(){}
