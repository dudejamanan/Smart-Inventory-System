// Smart Warehouse gate v1.0. No heap strings, JSON library, or blocking delays.
#include <SPI.h>
#include <MFRC522.h>
#include "config.h"
#include <stdlib.h>
#include <string.h>

MFRC522 rfid(RFID_SS, RFID_RST);
char line[97], sessionUid[21]="", pendingUid[21]="", lastUid[21]="";
uint8_t lineLen=0, failures=0, failLimit=DEFAULT_FAIL_LIMIT;
bool dropLine=false, pending=false, alarmOn=false, haveFail=false, haveCard=false;
uint16_t sequence=0, pendingSeq=0, windowS=DEFAULT_WINDOW_S, alarmS=DEFAULT_ALARM_S;
unsigned long lastPc=0, lastHb=0, pendingAt=0, lastCard=0, firstFail=0, alarmAt=0, redAt=0, outAt=0, testAt=0;
bool redFlash=false, outBlink=false;
uint8_t testKind=0;

bool elapsed(unsigned long now,unsigned long then,unsigned long duration){return (unsigned long)(now-then)>=duration;}
bool pcOk(unsigned long now){return !elapsed(now,lastPc,PC_LOST_MS);}
void buzzer(bool on){
#if BUZZER_ACTIVE
  digitalWrite(BUZZER_PIN,on?HIGH:LOW);
#else
  if(on) tone(BUZZER_PIN,2200); else noTone(BUZZER_PIN);
#endif
}
void emitUid(const __FlashStringHelper* type,const char* uid){
  Serial.print(F("{\"t\":\""));Serial.print(type);Serial.print(F("\",\"uid\":\""));Serial.print(uid);Serial.println(F("\"}"));
}
void startAlarm(const __FlashStringHelper* why){
  alarmOn=true;alarmAt=millis();
  Serial.print(F("{\"t\":\"ALARM\",\"why\":\""));Serial.print(why);Serial.println(F("\"}"));
}
void stopAlarm(const __FlashStringHelper* by){
  alarmOn=false;buzzer(false);
  Serial.print(F("{\"t\":\"ALARM_OFF\",\"by\":\""));Serial.print(by);Serial.println(F("\"}"));
}
void failed(const __FlashStringHelper* why){
  unsigned long now=millis();
  if(!haveFail||elapsed(now,firstFail,(unsigned long)windowS*1000)){failures=0;firstFail=now;haveFail=true;}
  failures++;redFlash=true;redAt=now;
  Serial.print(F("{\"t\":\"FAIL\",\"uid\":\""));Serial.print(pendingUid);Serial.print(F("\",\"n\":"));Serial.print(failures);Serial.print(F(",\"why\":\""));Serial.print(why);Serial.println(F("\"}"));
  if(failures>=failLimit){startAlarm(F("GATE_3_FAIL"));failures=0;haveFail=false;}
}
void authorized(bool ok){
  pending=false;
  if(!ok){failed(F("DENY"));return;}
  failures=0;haveFail=false;
  if(sessionUid[0]&&strcmp(sessionUid,pendingUid)!=0){emitUid(F("BUSY"),pendingUid);return;}
  bool entering=!sessionUid[0];
  if(entering) strcpy(sessionUid,pendingUid);
  else {sessionUid[0]=0;outBlink=true;outAt=millis();}
  Serial.print(F("{\"t\":\"SESSION\",\"state\":\""));Serial.print(entering?F("IN"):F("OUT"));Serial.print(F("\",\"uid\":\""));Serial.print(pendingUid);Serial.println(F("\"}"));
}

// Small strict parser for this flat JSON protocol. Only strings and unsigned
// integers are accepted. Unknown keys/duplicate keys/escapes are rejected.
struct Command {char t[12],uid[21],state[4],what[8]; unsigned long seq,ok,on,limit,window,alarm;uint16_t fields;};
void spaces(const char*& p){while(*p==' '||*p=='\t'||*p=='\r')p++;}
bool text(const char*& p,char* dest,uint8_t capacity){
  if(*p++!='"')return false;uint8_t n=0;
  while(*p&&*p!='"'){if((uint8_t)*p<32||*p=='\\'||n>=capacity-1)return false;dest[n++]=*p++;}
  if(*p++!='"')return false;dest[n]=0;return true;
}
bool uidValid(const char* uid){
  uint8_t n=strlen(uid);if(n!=8&&n!=14&&n!=20)return false;
  for(uint8_t i=0;i<n;i++)if(!((uid[i]>='0'&&uid[i]<='9')||(uid[i]>='A'&&uid[i]<='F')))return false;
  return true;
}
bool parseCommand(const char* p,Command& c){
  memset(&c,0,sizeof(c));spaces(p);if(*p++!='{')return false;
  while(true){
    spaces(p);char key[12],value[24];if(!text(p,key,sizeof(key)))return false;
    spaces(p);if(*p++!=':')return false;spaces(p);
    bool quoted=*p=='"';unsigned long number=0;
    if(quoted){if(!text(p,value,sizeof(value)))return false;}
    else {if(*p<'0'||*p>'9')return false;uint8_t digits=0;while(*p>='0'&&*p<='9'){if(++digits>9)return false;number=number*10+(*p++-'0');}}
    uint16_t bit=0;
    if(!strcmp(key,"t")&&quoted&&strlen(value)<sizeof(c.t)){bit=1;strcpy(c.t,value);}
    else if(!strcmp(key,"uid")&&quoted&&uidValid(value)){bit=2;strcpy(c.uid,value);}
    else if(!strcmp(key,"state")&&quoted&&(!strcmp(value,"IN")||!strcmp(value,"OUT"))){bit=4;strcpy(c.state,value);}
    else if(!strcmp(key,"what")&&quoted&&strlen(value)<sizeof(c.what)){bit=8;strcpy(c.what,value);}
    else if(!quoted){
      if(!strcmp(key,"seq")&&number<=65535){bit=16;c.seq=number;}
      else if(!strcmp(key,"ok")&&number<=1){bit=32;c.ok=number;}
      else if(!strcmp(key,"on")&&number<=1){bit=64;c.on=number;}
      else if(!strcmp(key,"fail_limit")&&number>=1&&number<=20){bit=128;c.limit=number;}
      else if(!strcmp(key,"window_s")&&number>=1&&number<=3600){bit=256;c.window=number;}
      else if(!strcmp(key,"alarm_s")&&number>=1&&number<=3600){bit=512;c.alarm=number;}
      else if(!strcmp(key,"slot")){bit=1024;}
    }
    if(!bit||(c.fields&bit))return false;c.fields|=bit;
    spaces(p);if(*p=='}'){p++;spaces(p);return !*p&&(c.fields&1);}
    if(*p++!=',')return false;
  }
}
void command(){
  Command c;if(!parseCommand(line,c))return;
  if(!strcmp(c.t,"HB")){lastPc=millis();}
  else if(!strcmp(c.t,"AUTH")&&(c.fields&48)==48&&pending&&c.seq==pendingSeq&&pcOk(millis())&&!elapsed(millis(),pendingAt,AUTH_TIMEOUT_MS)){authorized(c.ok==1);}
  else if(!strcmp(c.t,"REMOVAL")&&(c.fields&1024)&&!sessionUid[0])startAlarm(F("SHELF_BREACH"));
  else if(!strcmp(c.t,"ACK"))stopAlarm(F("ACK"));
  else if(!strcmp(c.t,"ALARM")&&(c.fields&64)&&c.on)startAlarm(F("PC_CMD"));
  else if(!strcmp(c.t,"SYNC")&&(c.fields&4)){
    if(!strcmp(c.state,"OUT"))sessionUid[0]=0;
    else if(c.fields&2)strcpy(sessionUid,c.uid);
  }
  else if(!strcmp(c.t,"CFG")){
    if(c.fields&128)failLimit=c.limit;if(c.fields&256)windowS=c.window;if(c.fields&512)alarmS=c.alarm;
  }
  else if(!strcmp(c.t,"TEST")&&(c.fields&8)){
    testKind=!strcmp(c.what,"green")?1:!strcmp(c.what,"red")?2:!strcmp(c.what,"buzzer")?3:0;testAt=millis();
  }
}
void serialInput(){
  // Bounded work per loop keeps RFID/timers responsive under serial floods.
  uint8_t budget=96;
  while(Serial.available()&&budget--){
    char ch=Serial.read();
    if(ch=='\n'){
      if(!dropLine&&lineLen){line[lineLen]=0;command();}
      lineLen=0;dropLine=false;
    }else if(!dropLine){if(lineLen>=96){dropLine=true;lineLen=0;}else line[lineLen++]=ch;}
  }
}
void readCard(){
  if(pending||!rfid.PICC_IsNewCardPresent()||!rfid.PICC_ReadCardSerial())return;
  char uid[21];const char hex[]="0123456789ABCDEF";
  if(rfid.uid.size>10)return;
  for(uint8_t i=0;i<rfid.uid.size;i++){uid[i*2]=hex[rfid.uid.uidByte[i]>>4];uid[i*2+1]=hex[rfid.uid.uidByte[i]&15];}uid[rfid.uid.size*2]=0;
  rfid.PICC_HaltA();rfid.PCD_StopCrypto1();
  unsigned long now=millis();
  if(haveCard&&!strcmp(uid,lastUid)&&!elapsed(now,lastCard,CARD_DEBOUNCE_MS))return;
  strcpy(lastUid,uid);lastCard=now;haveCard=true;
  strcpy(pendingUid,uid);pendingSeq=++sequence;pendingAt=now;pending=true;
  Serial.print(F("{\"t\":\"SCAN\",\"uid\":\""));Serial.print(uid);Serial.print(F("\",\"seq\":"));Serial.print(pendingSeq);Serial.println(F("}"));
}
void outputs(unsigned long now){
  if(redFlash&&elapsed(now,redAt,2000))redFlash=false;
  if(outBlink&&elapsed(now,outAt,600))outBlink=false;
  if(testKind&&elapsed(now,testAt,1000))testKind=0;
  bool green=sessionUid[0],red=redFlash,sound=false;
  if(outBlink)green=((now-outAt)/150)%2==0;
  if(!pcOk(now)){green=(now/600)%2==0;red=!green;}
  if(testKind==1)green=true;if(testKind==2)red=true;if(testKind==3)sound=true;
  // Alarm always has output priority, even if cameras/PC/WhatsApp fail.
  if(alarmOn){red=(now/100)%2==0;sound=(now/200)%2==0;}
  digitalWrite(GREEN_PIN,green?HIGH:LOW);digitalWrite(RED_PIN,red?HIGH:LOW);buzzer(sound);
}
void setup(){
  pinMode(GREEN_PIN,OUTPUT);pinMode(RED_PIN,OUTPUT);pinMode(BUZZER_PIN,OUTPUT);
  buzzer(false);Serial.begin(SERIAL_BAUD);SPI.begin();rfid.PCD_Init();
  lastPc=millis();Serial.println(F("{\"t\":\"BOOT\",\"fw\":\"1.0\"}"));
}
void loop(){
  serialInput();unsigned long now=millis();
  if(pending&&elapsed(now,pendingAt,AUTH_TIMEOUT_MS)){
    pending=false;
#if COUNT_TIMEOUT_AS_FAIL
    failed(F("TIMEOUT"));
#else
    redFlash=true;redAt=now;
#endif
  }
  if(haveFail&&elapsed(now,firstFail,(unsigned long)windowS*1000)){failures=0;haveFail=false;}
  if(alarmOn&&elapsed(now,alarmAt,(unsigned long)alarmS*1000))stopAlarm(F("TIMEOUT"));
  readCard();outputs(now);
  if(elapsed(now,lastHb,HEARTBEAT_MS)){
    lastHb=now;Serial.print(F("{\"t\":\"HB\",\"up\":"));Serial.print(now);Serial.print(F(",\"s\":\""));Serial.print(sessionUid[0]?F("IN"):F("OUT"));Serial.print(F("\",\"pcok\":"));Serial.print(pcOk(now)?1:0);Serial.println(F("}"));
  }
}
