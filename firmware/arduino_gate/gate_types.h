#pragma once
#include <Arduino.h>
// Token values point into the bounded serial input line, avoiding copies/heap use.
struct Field { char *key; char *value; bool quoted; };
struct Command { Field fields[10]; uint8_t count; };
enum ResultCode { R_IN, R_OUT, R_ISS, R_RET, R_DEN, R_PRM, R_NSS };
enum AlarmReason { A_GATE, A_SHELF, A_DEADMAN, A_PC };
