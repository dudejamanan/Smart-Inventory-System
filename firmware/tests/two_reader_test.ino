#include <SPI.h>
#include <MFRC522.h>
MFRC522 readers[2];byte nextReader=0;unsigned long lastPoll=0;
void setup(){Serial.begin(115200);SPI.begin();pinMode(10,OUTPUT);pinMode(4,OUTPUT);digitalWrite(10,HIGH);digitalWrite(4,HIGH);readers[0].PCD_Init(10,9);readers[1].PCD_Init(4,5);}
void loop(){if((unsigned long)(millis()-lastPoll)<50)return;lastPoll=millis();byte rd=nextReader;nextReader^=1;
  if(!readers[rd].PICC_IsNewCardPresent()||!readers[rd].PICC_ReadCardSerial())return;
  Serial.print(F("Reader "));Serial.print(rd);Serial.print(F(" UID "));
  for(byte i=0;i<readers[rd].uid.size;i++){if(readers[rd].uid.uidByte[i]<16)Serial.print('0');Serial.print(readers[rd].uid.uidByte[i],HEX);}
  Serial.println();readers[rd].PICC_HaltA();readers[rd].PCD_StopCrypto1();
}
