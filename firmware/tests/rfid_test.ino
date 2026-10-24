// Copy into a folder named rfid_test before opening in Arduino IDE.
#include <SPI.h>
#include <MFRC522.h>
MFRC522 reader(10,9);
void setup(){Serial.begin(115200);SPI.begin();reader.PCD_Init();Serial.println(F("Tap a card; UID follows"));}
void loop(){
  if(!reader.PICC_IsNewCardPresent()||!reader.PICC_ReadCardSerial())return;
  for(byte i=0;i<reader.uid.size;i++){if(reader.uid.uidByte[i]<16)Serial.print('0');Serial.print(reader.uid.uidByte[i],HEX);}
  Serial.println();reader.PICC_HaltA();reader.PCD_StopCrypto1();
}
