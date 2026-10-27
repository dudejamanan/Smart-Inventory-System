#pragma once
#define RFID_SS 10
#define RFID_RST 9
#define RFID_SS_1 4
#define RFID_RST_1 5
#define RFID_SCK 13
#define RFID_MOSI 11
#define RFID_MISO 12
#define BUZZER_PIN 6
#define GREEN_PIN 7
#define RED_PIN 8
#define BUTTON_PIN A0
// The supplied two-reader circuit has no button. D4 is reader 1 SS.
#ifndef BUTTON_ENABLED
#define BUTTON_ENABLED 0
#endif
// Reserved only: HC-SR04 A1/A2; I2C LCD A4/A5 (not implemented at M2).
#ifndef READER_COUNT
#define READER_COUNT 2
#endif
#if READER_COUNT < 1 || READER_COUNT > 2
#error READER_COUNT must be 1 or 2
#endif
#ifndef BUZZER_ACTIVE
#define BUZZER_ACTIVE 1
#endif
#ifndef BTN_ACK_ENABLED
#define BTN_ACK_ENABLED 1
#endif
#ifndef USE_WDT
#define USE_WDT 1
#endif
#define SERIAL_BAUD 115200UL
#define AUTH_TIMEOUT_MS 1000UL
#define CARD_DEBOUNCE_MS 1500UL
#define RF_SETTLE_MS 8UL
#define CARD_RELEASE_MS 600UL
#define HEARTBEAT_MS 2000UL
#define PC_LOST_MS 6000UL
#define DEFAULT_FAIL_LIMIT 3
#define DEFAULT_WINDOW_S 60
#define DEFAULT_ALARM_S 30
