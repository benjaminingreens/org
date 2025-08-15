import os, hashlib, base64, json, uuid, time
from pathlib import Path

NS_BITS  = 64  # per-install namespace
CTR_BITS = 32  # per-install counter
assert NS_BITS + CTR_BITS == 96
ROOT: Path = Path.cwd()
CONFIG_PATH: Path = ROOT / ".config.json"

def new_user_id_str() -> str:
    """Generate a UUIDv7 namespace once per install, returned as string."""
    ts_ms = int(time.time() * 1000)
    if ts_ms >= (1 << 48):
        raise ValueError("Timestamp too large for UUIDv7")

    time_bytes = ts_ms.to_bytes(6, "big")
    rand_bytes = os.urandom(10)
    b = bytearray(time_bytes + rand_bytes)
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # RFC 4122 variant

    return str(uuid.UUID(bytes=bytes(b)))

def make_id() -> str:
    """
    160-bit ID from UUIDv7 namespace (string in config) + 32-bit counter.
    Keyed Feistel over 160 bits for full diffusion; outputs 32-char base32 (lowercase).
    """
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")

    ns_uuid_str = cfg.get("user_id")
    counter = cfg.get("counter")

    if not isinstance(ns_uuid_str, str):
        raise TypeError("user_id in config must be a string")
    if not (0 <= counter < (1 << 32)):
        raise ValueError("counter must be a 32-bit unsigned integer")

    ns_uuid = uuid.UUID(ns_uuid_str)
    ns128 = int.from_bytes(ns_uuid.bytes, "big")
    x = (ns128 << 32) | counter  # 160 bits

    mask80 = (1 << 80) - 1
    L, R = (x >> 80) & mask80, x & mask80

    # namespace-derived key
    K = hashlib.sha256(ns_uuid.bytes + b"org-feistel-160-key").digest()

    def F(r_half: int, rnd: int) -> int:
        # depend on RIGHT half + key + round (+ counter for extra tweak)
        data = (
            r_half.to_bytes(10, "big")
            + counter.to_bytes(4, "big")
            + K
            + bytes([rnd])
        )
        return int.from_bytes(hashlib.sha256(data).digest()[:10], "big")  # 80 bits

    # more rounds for diffusion; use right-half in F
    for r in range(1, 11):  # was 6
        L, R = R, (L ^ F(R, r)) & mask80

    # final swap to improve avalanche
    y = (R << 80) | L

    # increment and persist counter
    cfg["counter"] = counter + 1
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str), encoding="utf-8")

    return base64.b32encode(y.to_bytes(20, "big")).decode().rstrip("=").lower()
