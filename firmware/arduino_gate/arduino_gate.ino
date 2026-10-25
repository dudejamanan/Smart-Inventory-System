// Gate v2: the PC owns online decisions; the board owns outputs and safety timers.
#include <SPI.h>
#include <MFRC522.h>
#include <avr/wdt.h>
#include <avr/pgmspace.h>
#include <EEPROM.h>
#include "config.h"
#include "gate_types.h"
#include "protocol_core.h"

// avr-libc early-reset pattern: preserve MCUSR before C initialization clears RAM.
uint8_t resetCause __attribute__((section(".noinit")));
void earlyReset(void) __attribute__((naked, section(".init3"), used));
void earlyReset(void) { resetCause=MCUSR; MCUSR=0; wdt_disable(); }
MFRC522 readers[READER_COUNT];
char line[97], pendingUid[21];
uint8_t lineLen=0, nextReader=0, sessions=0, failures=0, failLimit=DEFAULT_FAIL_LIMIT;
uint16_t sequence=0, pendingSeq=0, windowS=DEFAULT_WINDOW_S, alarmS=DEFAULT_ALARM_S;
bool dropping=false, pending=false, haveFail=false, alarmOn=false, pwOn=false, muted=false;
uint8_t feedback=255, alarmReason=A_PC, testKind=0;
uint32_t lastPc=0,lastHb=0,scanAt=0,firstFail=0,alarmAt=0,pwAt=0,pwMs=0,feedbackAt=0,muteAt=0,testAt=0,maxLoop=0;
uint32_t lastHash[READER_COUNT]={0}, lastCard[READER_COUNT]={0};
bool haveCard[READER_COUNT]={false};
bool btnRaw=false,btnStable=false;
uint32_t btnChanged=0,btnSince=0;
uint32_t bootId=1;
// Mutually exclusive buffers: 500-byte upload staging OR 16 offline records.
// Upload is refused until replay drains, so unacknowledged records are never lost.
union WorkBuffer { uint8_t stage[500]; OfflineEvent logs[16]; } work;
uint32_t offlineUsers[8],recentHash=0,recentAt=0,replayAt=0,nextEventId=1;
uint8_t offlineLevels[8],offlineUserCount=0,logHead=0,logCount=0,cacheCount=0,stageCount=0,stageExpected=0;
bool staging=false,haveRecent=false;
const char resultNames[7][4] PROGMEM={"IN","OUT","ISS","RET","DEN","PRM","NSS"};
// Each row: green pulse count/on/off, beep count/on/off, red duration. Units 10 ms.
const uint8_t patterns[7][7] PROGMEM={
  {0,0,0,1,8,12,0},{2,15,15,2,8,12,0},{3,7,7,1,8,12,0},
  {2,25,25,1,8,12,0},{0,0,0,0,0,0,200},{0,0,0,2,8,12,200},{0,0,0,0,0,0,200}};

bool elapsed(uint32_t now,uint32_t start,uint32_t duration){return (uint32_t)(now-start)>=duration;}
bool pcOk(uint32_t now){return !elapsed(now,lastPc,PC_LOST_MS);}
void printHash(uint32_t h){for(int8_t i=7;i>=0;i--){uint8_t d=(h>>(4*i))&15;Serial.write(d<10?'0'+d:'A'+d-10);}}
void buzzer(bool on){
#if BUZZER_ACTIVE
  digitalWrite(BUZZER_PIN,on?HIGH:LOW);
#else
  if(on)tone(BUZZER_PIN,2200);else noTone(BUZZER_PIN);
#endif
}
void resultText(uint8_t r){Serial.print((const __FlashStringHelper*)resultNames[r]);}
void reasonText(uint8_t why){
  switch(why){case A_GATE:Serial.print(F("GATE_3_FAIL"));break;case A_SHELF:Serial.print(F("SHELF_BREACH"));break;case A_DEADMAN:Serial.print(F("DEADMAN"));break;default:Serial.print(F("PC_CMD"));}
}
void startAlarm(uint8_t why){
  alarmOn=true;pwOn=false;alarmAt=millis();alarmReason=why;
  Serial.print(F("{\"t\":\"ALARM\",\"why\":\""));reasonText(why);Serial.println(F("\"}"));
}
void stopAlarm(const __FlashStringHelper *by){
  alarmOn=false;buzzer(false);Serial.print(F("{\"t\":\"ALARM_OFF\",\"by\":\""));Serial.print(by);Serial.println(F("\"}"));
}
void failed(const __FlashStringHelper *why){
  uint32_t now=millis();
  if(!haveFail||elapsed(now,firstFail,(uint32_t)windowS*1000)){failures=0;firstFail=now;haveFail=true;}
  failures++;Serial.print(F("{\"t\":\"FAIL\",\"uid\":\""));Serial.print(pendingUid);Serial.print(F("\",\"n\":"));Serial.print(failures);Serial.print(F(",\"why\":\""));Serial.print(why);Serial.println(F("\"}"));
  if(failures>=failLimit){failures=0;haveFail=false;startAlarm(A_GATE);}
}
void outputs(uint32_t now){
  bool green=sessions>0,red=false,sound=false;
  if(!pcOk(now)){green=(now/600)%2==0;red=!green;}
  if(feedback<7){
    uint32_t dt=now-feedbackAt;const uint8_t *p=patterns[feedback];
    uint8_t g=pgm_read_byte(p),b=pgm_read_byte(p+3);
    uint16_t gon=10U*pgm_read_byte(p+1),goff=10U*pgm_read_byte(p+2),bon=10U*pgm_read_byte(p+4),boff=10U*pgm_read_byte(p+5);
    if(g&&dt<(uint32_t)g*(gon+goff))green=dt%(gon+goff)<gon;
    if(dt<10UL*pgm_read_byte(p+6))red=true;
    if(b)sound=dt<(uint32_t)b*(bon+boff)&&dt%(bon+boff)<bon;
  }
  if(pwOn){uint16_t phase=(now-pwAt)%1000;red=phase<500;sound|=phase<80;}
  if(testKind&&!elapsed(now,testAt,1000)){green|=testKind==1;red|=testKind==2;sound|=testKind==3;}
  if(alarmOn){uint32_t dt=now-alarmAt;red=dt%200<100;bool shelf=alarmReason==A_SHELF||alarmReason==A_DEADMAN;sound=dt%(shelf?900:400)<(uint16_t)(shelf?600:200);}
  if(muted&&elapsed(now,muteAt,30000))muted=false;
  digitalWrite(GREEN_PIN,green);digitalWrite(RED_PIN,red);buzzer(sound&&!muted);
}
void applyResult(uint8_t r){
  pending=false;feedback=r;feedbackAt=millis();
  if(r==R_DEN||r==R_NSS)failed(r==R_NSS?F("NSS"):F("DENY"));
  else if(r!=R_PRM){failures=0;haveFail=false;}
  // Output is applied BEFORE FB, so FB timestamps describe real drive-start code.
  outputs(millis());Serial.print(F("{\"t\":\"FB\",\"seq\":"));Serial.print(pendingSeq);Serial.print(F(",\"r\":\""));resultText(r);Serial.print(F("\",\"ms\":"));Serial.print((uint32_t)(millis()-scanAt));Serial.println(F("}"));
}

// Strict in-place flat JSON tokenizer: no escapes, duplicates or nested values.
void spaces(char *&p){while(*p==' '||*p=='\t'||*p=='\r')p++;}
char *quoted(char *&p){
  if(*p++!='"')return NULL;char *start=p;
  while(*p&&*p!='"'){if((uint8_t)*p<32||(uint8_t)*p>126||*p=='\\')return NULL;p++;}
  if(!*p)return NULL;*p++=0;return start;
}
bool parseCommand(Command &c){
  c.count=0;char *p=line;spaces(p);if(*p++!='{')return false;
  while(c.count<10){
    spaces(p);char *key=quoted(p);if(!key)return false;
    for(uint8_t i=0;i<c.count;i++)if(!strcmp(key,c.fields[i].key))return false;
    spaces(p);if(*p++!=':')return false;spaces(p);
    Field &f=c.fields[c.count++];f.key=key;f.quoted=*p=='"';
    if(f.quoted){f.value=quoted(p);if(!f.value)return false;}
    else {
      f.value=p;if(*p<'0'||*p>'9'||(*p=='0'&&p[1]>='0'&&p[1]<='9'))return false;
      uint32_t n=0;while(*p>='0'&&*p<='9'){uint8_t d=*p++-'0';if(n>(0xffffffffUL-d)/10)return false;n=n*10+d;}
    }
    spaces(p);if(*p=='}'){p++;spaces(p);return !*p;}if(*p++!=',')return false;
  }return false;
}
Field *findField(Command &c,const __FlashStringHelper *key){for(uint8_t i=0;i<c.count;i++)if(!strcmp_P(c.fields[i].key,(PGM_P)key))return &c.fields[i];return NULL;}
char *stringField(Command &c,const __FlashStringHelper *key){Field *f=findField(c,key);return f&&f->quoted?f->value:NULL;}
bool numberField(Command &c,const __FlashStringHelper *key,uint32_t &out){Field *f=findField(c,key);if(!f||f->quoted)return false;out=strtoul(f->value,NULL,10);return true;}
bool equals(const char *value,const __FlashStringHelper *expected){return value&&!strcmp_P(value,(PGM_P)expected);}
uint8_t resultIndex(const char *r){if(r)for(uint8_t i=0;i<7;i++)if(!strcmp_P(r,resultNames[i]))return i;return 255;}
uint32_t readHashBytes(const uint8_t *bytes){uint32_t h=0;for(uint8_t i=0;i<4;i++)h|=(uint32_t)bytes[i]<<(8*i);return h;}
uint32_t eepromHash(uint8_t index){uint32_t h=0;for(uint8_t i=0;i<4;i++)h|=(uint32_t)EEPROM.read(4+5*index+i)<<(8*i);return h;}
uint8_t cacheFlags(uint32_t hash){for(uint8_t i=0;i<cacheCount;i++)if(eepromHash(i)==hash)return EEPROM.read(8+5*i);return 0;}
void loadOffline(){
  cacheCount=0;uint8_t count=EEPROM.read(3);
  if(EEPROM.read(0)=='W'&&EEPROM.read(1)=='2'&&EEPROM.read(2)==2&&count<=100){
    uint16_t crc=crcByte(crcByte(0xffff,2),count);bool valid=true;
    for(uint16_t i=0;i<(uint16_t)count*5;i++)crc=crcByte(crc,EEPROM.read(4+i));
    uint16_t stored=EEPROM.read(4+count*5)|((uint16_t)EEPROM.read(5+count*5)<<8);
    for(uint8_t i=0;i<count;i++){uint8_t flags=EEPROM.read(8+5*i);if((flags&0x7c)||!(flags&3))valid=false;for(uint8_t j=0;j<i;j++)if(eepromHash(i)==eepromHash(j))valid=false;}
    if(valid&&crc==stored)cacheCount=count;
  }
  // The independent boot counter is not part of the whitelist image.
  // Two journal slots retain the last valid identifier across a torn counter write.
  uint32_t a,ai,b,bi;EEPROM.get(1008,a);EEPROM.get(1012,ai);EEPROM.get(1016,b);EEPROM.get(1020,bi);
  bool av=a&&(a^ai)==0xffffffffUL,bv=b&&(b^bi)==0xffffffffUL;
  bool useB=bv&&(!av||(int32_t)(b-a)>0);uint32_t previous=useB?b:av?a:0;
  bootId=previous+1;if(!bootId)bootId=1;uint32_t inverse=~bootId;uint16_t target=useB?1008:1016;
  for(uint8_t i=0;i<4;i++){EEPROM.update(target+i,(bootId>>(8*i))&255);EEPROM.update(target+4+i,(inverse>>(8*i))&255);}
}
void wlError(const __FlashStringHelper *why){Serial.print(F("{\"t\":\"WLERR\",\"why\":\""));Serial.print(why);Serial.println(F("\"}"));}
void trackBadge(uint32_t hash,uint8_t result){
  uint8_t index=0;while(index<offlineUserCount&&offlineUsers[index]!=hash)index++;
  if(result==R_OUT&&index<offlineUserCount){for(uint8_t i=index;i+1<offlineUserCount;i++){offlineUsers[i]=offlineUsers[i+1];offlineLevels[i]=offlineLevels[i+1];}offlineUserCount--;if(haveRecent&&recentHash==hash)haveRecent=false;}
  else if(result==R_IN){if(index==offlineUserCount&&offlineUserCount<8){offlineUsers[offlineUserCount]=hash;offlineLevels[offlineUserCount++]=cacheFlags(hash)&3;}haveRecent=true;recentHash=hash;recentAt=millis();}
}
bool offlineScan(uint32_t hash){
  staging=false;sessions=offlineUserCount;
  if(logCount>=16||!nextEventId){wlError(F("FULL"));applyResult(R_PRM);return true;}
  uint8_t flags=cacheFlags(hash),result=R_DEN,event=3;
  if(flags){
    if(!(flags&0x80)){
      bool inside=false;for(uint8_t i=0;i<offlineUserCount;i++)if(offlineUsers[i]==hash)inside=true;
      result=inside?R_OUT:offlineUserCount<8?R_IN:R_PRM;
      if(result==R_IN||result==R_OUT){trackBadge(hash,result);event=result==R_IN?0:1;}
    }else{
      uint8_t owner=255;if(haveRecent&&!elapsed(millis(),recentAt,30000))for(uint8_t i=0;i<offlineUserCount;i++)if(offlineUsers[i]==recentHash)owner=i;
      if(owner==255&&offlineUserCount==1)owner=0;
      result=owner==255?R_NSS:offlineLevels[owner]<(flags&3)?R_PRM:R_ISS;if(result==R_ISS)event=2;
    }
  }
  sessions=offlineUserCount;uint8_t slot=(logHead+logCount)%16;
  work.logs[slot].hash=hash;work.logs[slot].at=millis();work.logs[slot].id=nextEventId++;work.logs[slot].event=event;logCount++;
  applyResult(result);return true;
}
bool offlineCommand(Command &c,const char *type){
  uint32_t value=0;
  if(equals(type,F("OFFOK"))){if(numberField(c,F("id"),value)&&logCount&&work.logs[logHead].id==value){logHead=(logHead+1)%16;logCount--;replayAt=millis()-1000;}return true;}
  if(!equals(type,F("WL")))return false;
  char *op=stringField(c,F("op"));
  if(equals(op,F("CLR"))){
    if(logCount||alarmOn||pwOn||pending||!pcOk(millis())){wlError(F("BUSY"));return true;}
    if(!numberField(c,F("n"),value)||value>100){wlError(F("COUNT"));return true;}
    staging=true;stageExpected=value;stageCount=0;logHead=0;
  }else if(!staging)wlError(F("STATE"));
  else if(equals(op,F("ADD"))){
    uint32_t lv,it;char *h=stringField(c,F("h"));
    if(!h||strlen(h)!=8||!numberField(c,F("lv"),lv)||lv<1||lv>3||!numberField(c,F("it"),it)||it>1){wlError(F("STATE"));staging=false;return true;}
    uint32_t hash=0;for(uint8_t i=0;i<8;i++){char ch=h[i];if(!((ch>='0'&&ch<='9')||(ch>='A'&&ch<='F'))){wlError(F("STATE"));staging=false;return true;}hash=(hash<<4)|(ch<='9'?ch-'0':ch-'A'+10);}
    if(stageCount>=stageExpected){wlError(F("COUNT"));staging=false;return true;}
    for(uint8_t i=0;i<stageCount;i++)if(readHashBytes(work.stage+5*i)==hash){wlError(F("DUP"));staging=false;return true;}
    for(uint8_t i=0;i<4;i++)work.stage[5*stageCount+i]=(hash>>(8*i))&255;work.stage[5*stageCount+4]=lv|(it?0x80:0);stageCount++;
  }else if(equals(op,F("END"))){
    staging=false;uint32_t checksum;
    if(logCount||alarmOn||pwOn||pending){wlError(F("BUSY"));return true;}
    if(!numberField(c,F("n"),value)||value!=stageExpected||stageCount!=stageExpected){wlError(F("COUNT"));return true;}
    uint16_t crc=crcByte(crcByte(0xffff,2),stageCount);for(uint16_t i=0;i<(uint16_t)stageCount*5;i++)crc=crcByte(crc,work.stage[i]);
    if(!numberField(c,F("ck"),checksum)||checksum!=crc){wlError(F("CRC"));return true;}
    // Magic is published last; an interrupted commit cannot authorize a partial list.
    bool same=EEPROM.read(0)=='W'&&EEPROM.read(1)=='2'&&EEPROM.read(2)==2&&EEPROM.read(3)==stageCount;
    for(uint16_t i=0;i<(uint16_t)stageCount*5&&same;i++)if(EEPROM.read(4+i)!=work.stage[i])same=false;
    if(same&&(EEPROM.read(4+stageCount*5)!=(crc&255)||EEPROM.read(5+stageCount*5)!=(crc>>8)))same=false;
    if(!same){EEPROM.update(0,0);EEPROM.update(1,0);EEPROM.update(2,2);EEPROM.update(3,stageCount);
    for(uint16_t i=0;i<(uint16_t)stageCount*5;i++){EEPROM.update(4+i,work.stage[i]);
#if USE_WDT
      wdt_reset();
#endif
    }
    EEPROM.update(4+stageCount*5,crc&255);EEPROM.update(5+stageCount*5,crc>>8);EEPROM.update(0,'W');EEPROM.update(1,'2');}cacheCount=stageCount;
    // Revocation/downgrade must also affect already remembered offline identities.
    for(uint8_t i=0;i<offlineUserCount;){uint8_t flags=cacheFlags(offlineUsers[i]);if(!flags||(flags&0x80))trackBadge(offlineUsers[i],R_OUT);else{offlineLevels[i]=flags&3;i++;}}
    Serial.print(F("{\"t\":\"WLOK\",\"n\":"));Serial.print(cacheCount);Serial.println(F("}"));
  }else{staging=false;wlError(F("STATE"));}
  return true;
}
void offlineTick(uint32_t now){
  if(!pcOk(now)){staging=false;return;}
  if(logCount&&elapsed(now,replayAt,1000)){
    replayAt=now;OfflineEvent &e=work.logs[logHead];Serial.print(F("{\"t\":\"OFF\",\"id\":"));Serial.print(e.id);Serial.print(F(",\"bid\":"));Serial.print(bootId);Serial.print(F(",\"h\":\""));printHash(e.hash);Serial.print(F("\",\"e\":\""));Serial.print(e.event==0?F("IN"):e.event==1?F("OUT"):e.event==2?F("ISS"):F("DEN"));Serial.print(F("\",\"ago\":"));Serial.print((uint32_t)(now-e.at)/1000);Serial.println(F("}"));
  }
}
uint8_t offlineCount(){return logCount;}
void command(){
  Command c;if(!parseCommand(c))return;char *t=stringField(c,F("t"));if(!t)return;
  uint32_t n=0,seq=0,value=0;
  if(equals(t,F("HB"))&&numberField(c,F("n"),n)&&n<=8){lastPc=millis();sessions=n;}
  else if(equals(t,F("SYNC"))&&numberField(c,F("n"),n)&&n<=8)sessions=n;
  else if(equals(t,F("AUTH"))&&numberField(c,F("seq"),seq)&&seq==pendingSeq&&numberField(c,F("n"),n)&&n<=8&&pending&&pcOk(millis())&&!elapsed(millis(),scanAt,AUTH_TIMEOUT_MS)){
    uint8_t r=resultIndex(stringField(c,F("r")));if(r<7){sessions=n;if(r==R_IN||r==R_OUT)trackBadge(uidHash(pendingUid),r);applyResult(r);}
  }else if(equals(t,F("PW"))&&numberField(c,F("on"),value)&&value<=1){
    if(value){uint32_t seconds;if(!numberField(c,F("s"),seconds)||seconds<1||seconds>3600)return;
      uint32_t now=millis(),duration=seconds*1000;if(!pwOn||duration<pwMs-(uint32_t)(now-pwAt)){pwAt=now;pwMs=duration;}pwOn=true;Serial.println(F("{\"t\":\"PW\",\"st\":\"ON\"}"));
    }else{pwOn=false;Serial.println(F("{\"t\":\"PW\",\"st\":\"OFF\"}"));}
  }else if(equals(t,F("ACK"))){pwOn=false;stopAlarm(F("ACK"));}
  else if(equals(t,F("ALARM"))&&numberField(c,F("on"),value)&&value==1){
    char *why=stringField(c,F("why"));if(equals(why,F("SHELF_BREACH")))startAlarm(A_SHELF);else if(equals(why,F("DEADMAN")))startAlarm(A_DEADMAN);else if(equals(why,F("GATE_3_FAIL")))startAlarm(A_GATE);else if(equals(why,F("PC_CMD")))startAlarm(A_PC);
  }else if(equals(t,F("CFG"))){
    uint32_t limit,window,alarm;if(numberField(c,F("fail_limit"),limit)&&limit>=1&&limit<=20&&numberField(c,F("window_s"),window)&&window>=1&&window<=3600&&numberField(c,F("alarm_s"),alarm)&&alarm>=1&&alarm<=3600){failLimit=limit;windowS=window;alarmS=alarm;}
  }else if(equals(t,F("TEST"))){char *what=stringField(c,F("what"));testKind=equals(what,F("green"))?1:equals(what,F("red"))?2:equals(what,F("buzzer"))?3:0;testAt=millis();}
  else offlineCommand(c,t);
}
void serialInput(){
  uint8_t budget=96;while(Serial.available()&&budget--){char ch=Serial.read();if(ch=='\n'){if(!dropping&&lineLen){line[lineLen]=0;command();}lineLen=0;dropping=false;}else if(!dropping){if(lineLen>=96){lineLen=0;dropping=true;}else line[lineLen++]=ch;}}
}
void readCard(){
  if(pending)return;uint8_t rd=nextReader;nextReader=(nextReader+1)%READER_COUNT;
  MFRC522 &reader=readers[rd];if(!reader.PICC_IsNewCardPresent()||!reader.PICC_ReadCardSerial())return;
  if(reader.uid.size!=4&&reader.uid.size!=7&&reader.uid.size!=10)return;
  const char hex[]="0123456789ABCDEF";for(uint8_t i=0;i<reader.uid.size;i++){pendingUid[2*i]=hex[reader.uid.uidByte[i]>>4];pendingUid[2*i+1]=hex[reader.uid.uidByte[i]&15];}pendingUid[reader.uid.size*2]=0;
  reader.PICC_HaltA();reader.PCD_StopCrypto1();uint32_t now=millis(),hash=uidHash(pendingUid);
  if(haveCard[rd]&&lastHash[rd]==hash&&!elapsed(now,lastCard[rd],CARD_DEBOUNCE_MS))return;
  haveCard[rd]=true;lastHash[rd]=hash;lastCard[rd]=now;pendingSeq=++sequence;scanAt=now;
  Serial.print(F("{\"t\":\"SCAN\",\"uid\":\""));Serial.print(pendingUid);Serial.print(F("\",\"seq\":"));Serial.print(pendingSeq);Serial.print(F(",\"rd\":"));Serial.print(rd);Serial.println(F("}"));
  if(!pcOk(now)&&offlineScan(hash))return;pending=true;
}
void buttonTick(uint32_t now){
  bool pressed=digitalRead(BUTTON_PIN)==LOW;if(pressed!=btnRaw){btnRaw=pressed;btnChanged=now;}
  if(btnRaw!=btnStable&&elapsed(now,btnChanged,30)){
    btnStable=btnRaw;if(btnStable)btnSince=now;else{bool longPress=elapsed(now,btnSince,1500);Serial.println(longPress?F("{\"t\":\"BTN\",\"k\":\"L\"}"):F("{\"t\":\"BTN\",\"k\":\"S\"}"));
      if(!longPress){muted=true;muteAt=now;}
#if BTN_ACK_ENABLED
      else{pwOn=false;stopAlarm(F("BTN"));}
#endif
    }
  }
}
int freeRam(){extern int __heap_start,*__brkval;int top;return (int)&top-(__brkval?(int)__brkval:(int)&__heap_start);}
void setup(){
  pinMode(GREEN_PIN,OUTPUT);pinMode(RED_PIN,OUTPUT);pinMode(BUZZER_PIN,OUTPUT);pinMode(BUTTON_PIN,INPUT_PULLUP);buzzer(false);
  Serial.begin(SERIAL_BAUD);SPI.begin();
  for(uint8_t i=0;i<READER_COUNT;i++){uint8_t ss=i?RFID_SS_1:RFID_SS;pinMode(ss,OUTPUT);digitalWrite(ss,HIGH);}
  for(uint8_t i=0;i<READER_COUNT;i++)readers[i].PCD_Init(i?RFID_SS_1:RFID_SS,i?RFID_RST_1:RFID_RST);
  loadOffline();lastPc=millis();Serial.print(F("{\"t\":\"BOOT\",\"fw\":\"2.0\",\"rst\":\""));
  Serial.print(resetCause&_BV(WDRF)?F("WDT"):resetCause&_BV(BORF)?F("BOR"):resetCause&_BV(EXTRF)?F("EXT"):F("PWR"));Serial.print(F("\",\"rd\":"));Serial.print(READER_COUNT);Serial.print(F(",\"bid\":"));Serial.print(bootId);Serial.println(F("}"));
#if USE_WDT
  wdt_enable(WDTO_2S);
#endif
}
void loop(){
  uint32_t started=micros();
#if USE_WDT
  wdt_reset();
#endif
  serialInput();uint32_t now=millis();buttonTick(now);offlineTick(now);
  if(pending&&elapsed(now,scanAt,AUTH_TIMEOUT_MS)){pending=false;feedback=R_DEN;feedbackAt=now;failed(F("TIMEOUT"));outputs(now);Serial.print(F("{\"t\":\"FB\",\"seq\":"));Serial.print(pendingSeq);Serial.print(F(",\"r\":\"DEN\",\"ms\":"));Serial.print((uint32_t)(now-scanAt));Serial.println(F("}"));}
  if(haveFail&&elapsed(now,firstFail,(uint32_t)windowS*1000)){failures=0;haveFail=false;}
  if(pwOn&&elapsed(now,pwAt,pwMs)){pwOn=false;Serial.println(F("{\"t\":\"PW\",\"st\":\"ESC\"}"));startAlarm(A_DEADMAN);}
  if(alarmOn&&elapsed(now,alarmAt,(uint32_t)alarmS*1000))stopAlarm(F("TIMEOUT"));
  readCard();outputs(millis());
  uint32_t duration=micros()-started;if(duration>maxLoop)maxLoop=duration;
  if(elapsed(now,lastHb,HEARTBEAT_MS)){lastHb=now;Serial.print(F("{\"t\":\"HB\",\"up\":"));Serial.print(now);Serial.print(F(",\"n\":"));Serial.print(sessions);Serial.print(F(",\"pcok\":"));Serial.print(pcOk(now)?1:0);Serial.print(F(",\"ram\":"));Serial.print(freeRam());Serial.print(F(",\"lp\":"));Serial.print(maxLoop);Serial.print(F(",\"off\":"));Serial.print(offlineCount());Serial.println(F("}"));maxLoop=0;}
}
