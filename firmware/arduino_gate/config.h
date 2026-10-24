#pragma once
// UNO pin assignment. RC522 power MUST be 3.3 V; level shift UNO outputs.
#define RFID_SS 10
#define RFID_RST 9
#define RFID_SCK 13
#define RFID_MOSI 11
#define RFID_MISO 12
#define BUZZER_PIN 6
#define GREEN_PIN 7
#define RED_PIN 8
#ifndef BUZZER_ACTIVE
#define BUZZER_ACTIVE 1
#endif
#ifndef COUNT_TIMEOUT_AS_FAIL
#define COUNT_TIMEOUT_AS_FAIL 1
#endif
#define SERIAL_BAUD 115200UL
#define AUTH_TIMEOUT_MS 1000UL
#define CARD_DEBOUNCE_MS 1500UL
#define HEARTBEAT_MS 2000UL
#define PC_LOST_MS 6000UL
#define DEFAULT_FAIL_LIMIT 3
#define DEFAULT_WINDOW_S 60
#define DEFAULT_ALARM_S 30
