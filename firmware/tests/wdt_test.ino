// WARNING: requires a watchdog-safe bootloader. See V2_HARDWARE_CHECKPOINT.md.
#include <avr/wdt.h>
#include <avr/io.h>
uint8_t cause __attribute__((section(".noinit")));
void early(void) __attribute__((naked,section(".init3"),used));
void early(void){cause=MCUSR;MCUSR=0;wdt_disable();}
void setup(){Serial.begin(115200);Serial.print(F("BOOT reset flags="));Serial.println(cause,HEX);wdt_enable(WDTO_2S);}
void loop(){if(millis()>5000){Serial.println(F("Deliberate hang; expect reset after about 2 s"));Serial.flush();while(true){}}
  wdt_reset();
}
