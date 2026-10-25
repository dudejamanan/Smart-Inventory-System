#include <EEPROM.h>
#include "protocol_core.h"
#include "hash_vectors.h"
// Scratch address 900 is outside the gate whitelist and boot-counter regions.
void setup(){Serial.begin(115200);byte saved[4];bool ok=true;
  char uid[21];bool hashes=true;for(byte i=0;i<sizeof(hashVectors)/sizeof(hashVectors[0]);i++){strcpy_P(uid,hashVectors[i].uid);if(uidHash(uid)!=pgm_read_dword(&hashVectors[i].hash))hashes=false;}
  Serial.println(hashes?F("FNV shared vectors PASS"):F("FNV FAIL"));
  uint16_t crc=0xffff;const char *digits="123456789";while(*digits)crc=crcByte(crc,*digits++);Serial.println(crc==0x29b1?F("CRC shared vector PASS"):F("CRC FAIL"));
  for(byte i=0;i<4;i++){saved[i]=EEPROM.read(900+i);EEPROM.update(900+i,0x51+i);}
  for(byte i=0;i<4;i++)if(EEPROM.read(900+i)!=0x51+i)ok=false;
  for(byte i=0;i<4;i++)EEPROM.update(900+i,saved[i]);
  Serial.println(ok?F("EEPROM scratch round trip PASS; original bytes restored"):F("EEPROM FAIL"));
}
void loop(){}
