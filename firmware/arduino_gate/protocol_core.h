#pragma once
#include <stdint.h>
// Shared by main firmware and the standalone EEPROM/hash validation sketch.
static inline uint32_t uidHash(const char *uid){uint32_t h=2166136261UL;while(*uid)h=(h^(uint8_t)*uid++)*16777619UL;return h;}
static inline uint16_t crcByte(uint16_t crc,uint8_t value){crc^=(uint16_t)value<<8;for(uint8_t i=0;i<8;i++)crc=crc&0x8000?(crc<<1)^0x1021:crc<<1;return crc;}
