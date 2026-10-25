"""Strict bounded newline JSON framing. MAX_LINE excludes the newline."""

import json
import re

MAX_LINE = 96
UID = re.compile(r"^(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})$")
TYPES = {
    "BOOT",
    "SCAN",
    "SESSION",
    "FAIL",
    "BUSY",
    "ALARM",
    "ALARM_OFF",
    "HB",
    "AUTH",
    "REMOVAL",
    "ACK",
    "SYNC",
    "CFG",
    "TEST",
}


def parse(line: bytes) -> dict:
    raw = line.removesuffix(b"\n")
    if len(raw) > MAX_LINE:
        raise ValueError("oversized protocol line")
    try:

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        obj = json.loads(raw, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("malformed JSON") from exc
    if (
        not isinstance(obj, dict)
        or not isinstance(obj.get("t"), str)
        or obj["t"] not in TYPES
    ):
        raise ValueError("unknown message")
    for key in ["uid", "state", "why", "by", "what", "s"]:
        if key in obj and not isinstance(obj[key], str):
            raise ValueError("invalid string field")
    if "uid" in obj and not UID.fullmatch(str(obj["uid"])):
        raise ValueError("invalid UID")
    if obj["t"] in {"AUTH", "SCAN"} and (
        type(obj.get("seq")) is not int or not 0 <= obj["seq"] <= 65535
    ):
        raise ValueError("invalid sequence")
    if obj["t"] == "AUTH" and (
        type(obj.get("ok")) is not int or obj.get("ok") not in (0, 1)
    ):
        raise ValueError("invalid authorization")
    if obj["t"] in {"SESSION", "SYNC"} and obj.get("state") not in {"IN", "OUT"}:
        raise ValueError("invalid session")
    if obj["t"] in {"SCAN", "FAIL", "BUSY"} and "uid" not in obj:
        raise ValueError("missing UID")
    if (
        obj["t"] in {"SESSION", "SYNC"}
        and obj.get("state") == "IN"
        and "uid" not in obj
    ):
        raise ValueError("missing session UID")
    t = obj["t"]
    if t == "FAIL" and (
        type(obj.get("n")) is not int
        or not 1 <= obj["n"] <= 20
        or obj.get("why") not in {"DENY", "TIMEOUT"}
    ):
        raise ValueError("invalid failure")
    if (
        t == "ALARM"
        and "why" in obj
        and obj["why"] not in {"GATE_3_FAIL", "SHELF_BREACH", "PC_CMD"}
    ):
        raise ValueError("invalid alarm reason")
    if t == "ALARM_OFF" and obj.get("by") not in {"TIMEOUT", "ACK"}:
        raise ValueError("invalid alarm end")
    if t == "REMOVAL" and (type(obj.get("slot")) is not int or obj["slot"] < 0):
        raise ValueError("invalid slot")
    if t == "TEST" and obj.get("what") not in {"green", "red", "buzzer"}:
        raise ValueError("invalid test")
    if (
        t == "HB"
        and "s" in obj
        and (
            obj["s"] not in {"IN", "OUT"}
            or obj.get("pcok") not in {0, 1}
            or type(obj.get("up")) is not int
        )
    ):
        raise ValueError("invalid heartbeat")
    return obj


def encode(obj: dict) -> bytes:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    parse(raw)
    return raw + b"\n"
