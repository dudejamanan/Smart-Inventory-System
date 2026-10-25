"""v2 bounded framing, FNV-1a UID hashes and CRC16 whitelist checksums."""

import json
import re

MAX_LINE = 96
UID = re.compile(r"^(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})$")
HASH = re.compile(r"^[0-9A-F]{8}$")
RESULTS = {"IN", "OUT", "ISS", "RET", "DEN", "PRM", "NSS"}
REASONS = {"GATE_3_FAIL", "SHELF_BREACH", "DEADMAN", "PC_CMD"}
TYPES = {
    "BOOT",
    "SCAN",
    "FAIL",
    "FB",
    "ALARM",
    "ALARM_OFF",
    "PW",
    "HB",
    "BTN",
    "OFF",
    "WLOK",
    "WLERR",
    "AUTH",
    "ACK",
    "CFG",
    "TEST",
    "SYNC",
    "WL",
    "OFFOK",
}


def fnv1a(uid: str) -> int:
    if not UID.fullmatch(uid):
        raise ValueError("UID must be uppercase hex (4, 7 or 10 bytes)")
    value = 2166136261
    for byte in uid.encode("ascii"):
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def crc16(data: bytes) -> int:
    value = 0xFFFF
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ 0x1021 if value & 0x8000 else value << 1) & 0xFFFF
    return value


def whitelist_bytes(entries: list[tuple[int, int, bool]]) -> bytes:
    if len(entries) > 100:
        raise ValueError("Maximum 100 offline tags")
    seen = set()
    raw = bytearray([2, len(entries)])
    for h, level, item in entries:
        if h in seen or not 0 <= h <= 0xFFFFFFFF or not 1 <= level <= 3:
            raise ValueError("Duplicate hash or invalid level")
        seen.add(h)
        raw.extend(h.to_bytes(4, "little"))
        raw.append(level | (0x80 if item else 0))
    return bytes(raw)


def whitelist_messages(entries: list[tuple[int, int, bool]]) -> list[dict]:
    raw = whitelist_bytes(entries)
    return (
        [{"t": "WL", "op": "CLR", "n": len(entries)}]
        + [
            {"t": "WL", "op": "ADD", "h": f"{h:08X}", "lv": lv, "it": int(it)}
            for h, lv, it in entries
        ]
        + [{"t": "WL", "op": "END", "n": len(entries), "ck": crc16(raw)}]
    )


def parse(line: bytes) -> dict:
    raw = line.removesuffix(b"\n")
    if len(raw) > MAX_LINE:
        raise ValueError("Oversized protocol line")

    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("Duplicate JSON key")
            result[k] = v
        return result

    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed JSON") from exc
    if (
        not isinstance(obj, dict)
        or not isinstance(obj.get("t"), str)
        or obj["t"] not in TYPES
    ):
        raise ValueError("Unknown v2 message")

    def integer(key, lo=0, hi=0xFFFFFFFF, required=True):
        if not required and key not in obj:
            return
        if type(obj.get(key)) is not int or not lo <= obj[key] <= hi:
            raise ValueError("Invalid " + key)

    def choice(key, values):
        if not isinstance(obj.get(key), str) or obj[key] not in values:
            raise ValueError("Invalid " + key)

    if "uid" in obj and (
        not isinstance(obj["uid"], str) or not UID.fullmatch(obj["uid"])
    ):
        raise ValueError("Invalid UID")
    if "h" in obj and (not isinstance(obj["h"], str) or not HASH.fullmatch(obj["h"])):
        raise ValueError("Invalid hash")
    t = obj["t"]
    if t == "BOOT":
        if not isinstance(obj.get("fw"), str) or not re.fullmatch(
            r"\d+\.\d+", obj["fw"]
        ):
            raise ValueError("Invalid firmware version")
        if tuple(map(int, obj["fw"].split("."))) >= (2, 0):
            choice("rst", {"PWR", "EXT", "BOR", "WDT"})
            integer("rd", 1, 2)
            integer("bid", 1)
    elif t in {"SCAN", "AUTH", "FB"}:
        integer("seq", 0, 65535)
        if t == "SCAN":
            if "uid" not in obj:
                raise ValueError("Missing UID")
            integer("rd", 0, 1)
        else:
            choice("r", RESULTS)
            integer("n", 0, 8) if t == "AUTH" else integer("ms")
            if "ok" in obj:
                raise ValueError("v1 AUTH is not supported")
    elif t == "FAIL":
        if "uid" not in obj:
            raise ValueError("Missing UID")
        integer("n", 1, 20)
        choice("why", {"DENY", "TIMEOUT", "NSS"})
    elif t == "ALARM":
        choice("why", REASONS)
        integer("on", 1, 1, False)
    elif t == "ALARM_OFF":
        choice("by", {"TIMEOUT", "ACK", "BTN"})
    elif t == "PW":
        if "st" in obj:
            choice("st", {"ON", "OFF", "ESC"})
        else:
            integer("on", 0, 1)
            if obj["on"]:
                integer("s", 1, 3600)
    elif t in {"HB", "SYNC"}:
        integer("n", 0, 8)
        if "up" in obj:
            integer("up")
            integer("pcok", 0, 1)
            integer("ram", 0, 2048)
            integer("lp")
            integer("off", 0, 16)
    elif t == "BTN":
        choice("k", {"S", "L"})
    elif t == "OFF":
        integer("id", 1)
        integer("bid", 1)
        integer("ago")
        choice("e", {"IN", "OUT", "ISS", "DEN"})
        if "h" not in obj:
            raise ValueError("Missing hash")
    elif t == "OFFOK":
        integer("id", 1)
    elif t == "WL":
        choice("op", {"CLR", "ADD", "END"})
        if obj["op"] in {"CLR", "END"}:
            integer("n", 0, 100)
        if obj["op"] == "ADD":
            if "h" not in obj:
                raise ValueError("Missing hash")
            integer("lv", 1, 3)
            integer("it", 0, 1)
        if obj["op"] == "END":
            integer("ck", 0, 65535)
    elif t == "WLOK":
        integer("n", 0, 100)
    elif t == "WLERR":
        choice("why", {"BUSY", "COUNT", "CRC", "DUP", "STATE", "FULL"})
    elif t == "CFG":
        integer("fail_limit", 1, 20)
        integer("window_s", 1, 3600)
        integer("alarm_s", 1, 3600)
    elif t == "TEST":
        choice("what", {"green", "red", "buzzer"})
    return obj


def encode(obj: dict) -> bytes:
    raw = json.dumps(obj, separators=(",", ":")).encode("ascii")
    parse(raw)
    return raw + b"\n"
