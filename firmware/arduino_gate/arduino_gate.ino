// Gate v2: the PC owns online decisions; the board owns outputs and safety timers.
#include <SPI.h>
#include <MFRC522.h>
#include <avr/wdt.h>
#include <avr/pgmspace.h>
#include "config.h"
#include "gate_types.h"

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
const char resultNames[7][4] PROGMEM={"IN","OUT","ISS","RET","DEN","PRM","NSS"};
// Each row: green pulse count/on/off, beep count/on/off, red duration. Units 10 ms.
const uint8_t patterns[7][7] PROGMEM={
  {0,0,0,1,8,12,0},{2,15,15,2,8,12,0},{3,7,7,1,8,12,0},
  {2,25,25,1,8,12,0},{0,0,0,0,0,0,200},{0,0,0,2,8,12,200},{0,0,0,0,0,0,200}};

bool elapsed(uint32_t now,uint32_t start,uint32_t duration){return (uint32_t)(now-start)>=duration;}
bool pcOk(uint32_t now){return !elapsed(now,lastPc,PC_LOST_MS);}
uint32_t uidHash(const char *uid){uint32_t h=2166136261UL;while(*uid)h=(h^(uint8_t)*uid++)*16777619UL;return h;}
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
  while(*p&&*p!='"'){if((uint8_t)*p<32||*p=='\\')return NULL;p++;}
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
// M2 extends these two hooks with EEPROM and replay; no online local toggles.
bool offlineScan(uint32_t hash){return false;}
bool offlineCommand(Command &c,const char *type){return false;}
void offlineTick(uint32_t now){}
uint8_t offlineCount(){return 0;}
void command(){
  Command c;if(!parseCommand(c))return;char *t=stringField(c,F("t"));if(!t)return;
  uint32_t n=0,seq=0,value=0;
  if(equals(t,F("HB"))&&numberField(c,F("n"),n)&&n<=8){lastPc=millis();sessions=n;}
  else if(equals(t,F("SYNC"))&&numberField(c,F("n"),n)&&n<=8)sessions=n;
  else if(equals(t,F("AUTH"))&&numberField(c,F("seq"),seq)&&seq==pendingSeq&&numberField(c,F("n"),n)&&n<=8&&pending&&pcOk(millis())&&!elapsed(millis(),scanAt,AUTH_TIMEOUT_MS)){
    uint8_t r=resultIndex(stringField(c,F("r")));if(r<7){sessions=n;applyResult(r);}
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
  lastPc=millis();Serial.print(F("{\"t\":\"BOOT\",\"fw\":\"2.0\",\"rst\":\""));
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
