#pragma once
#include <avr/pgmspace.h>
struct HashVector { char uid[21]; uint32_t hash; };
// Matches hash_vectors.json; pytest checks both sources against the Python port.
const HashVector hashVectors[] PROGMEM={
  {"A1B2C3D4",0xC20D677DUL},{"11223344",0xE568577DUL},
  {"00000000",0x0FF37DE5UL},{"FFFFFFFF",0x29613CE5UL},
  {"04AABBCCDDEEFF",0x1ED863CBUL}};
