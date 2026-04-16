"""
mci.parser

Core ISO8583 parsing logic for MasterCard IPM files.
Modern Python 3 rewrite - no legacy Python 2 compatibility needed.
"""

import binascii
import codecs
import datetime
import decimal
import logging
import re
import struct
from array import array

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bitmap
# ---------------------------------------------------------------------------

class BitArray:
    """Pure-Python bitmap interpreter (replaces the C bitarray module)."""

    def __init__(self):
        self._bytes = b""

    def frombytes(self, data: bytes):
        self._bytes = data

    def tolist(self) -> list[bool]:
        swap = array("B", self._bytes)
        width = len(self._bytes) * 8
        try:
            raw = swap.tobytes()
        except AttributeError:
            raw = swap.tostring()
        bits = "{:0{}b}".format(int(binascii.hexlify(raw), 16), width)
        return [b == "1" for b in bits]


def _get_bitmap_list(binary_bitmap: bytes) -> list:
    """Return list where index 0 = raw bitmap bytes, indices 1-128 = bool."""
    ba = BitArray()
    ba.frombytes(binary_bitmap)
    return [binary_bitmap] + ba.tolist()


# ---------------------------------------------------------------------------
# 1014-block / VBS helpers
# ---------------------------------------------------------------------------

def unblock(data: bytes) -> list[bytes]:
    """Unpack 1014-byte blocked data into a list of VBS records."""
    raw_blocks = []
    ptr = 0
    warned = False

    while ptr + 1014 <= len(data):
        block = data[ptr: ptr + 1012]
        eob = data[ptr + 1012: ptr + 1014]
        if not warned and eob not in (b"", b"\x40\x40"):
            LOGGER.warning(
                "Unusual EOB marker %r — file may not be 1014-blocked. "
                "Use no_1014_blocking=True if VBS format.",
                eob,
            )
            warned = True
        raw_blocks.append(block)
        ptr += 1014

    return vbs_unpack(b"".join(raw_blocks))


def vbs_unpack(data: bytes) -> list[bytes]:
    """Unpack variable-blocked string into individual records."""
    ptr = 0
    records = []

    while ptr < len(data):
        if ptr + 4 > len(data):
            break
        (length,) = struct.unpack(">i", data[ptr: ptr + 4])
        ptr += 4
        if length == 0:
            break
        records.append(data[ptr: ptr + length])
        ptr += length

    return records


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _eb2asc(value: bytes) -> bytes:
    return codecs.encode(codecs.decode(value, "cp500"), "latin-1")


def _asc2eb(value: bytes) -> bytes:
    return codecs.encode(codecs.decode(value, "latin-1"), "cp500")


# ---------------------------------------------------------------------------
# Field-level helpers
# ---------------------------------------------------------------------------

def _get_length_size(field_type: str) -> int:
    return {"LLVAR": 2, "LLLVAR": 3}.get(field_type, 0)


def _to_python_type(data, python_type: str):
    if python_type == "int":
        return int(data)
    if python_type in ("long", "decimal"):
        return int(data)          # Python 3 has no long; decimal kept as int
    if python_type == "datetime":
        return datetime.datetime.strptime(
            data if isinstance(data, str) else data.decode("latin-1"),
            "%y%m%d%H%M%S",
        )
    return data


# ---------------------------------------------------------------------------
# PDS / DE43 sub-parsers
# ---------------------------------------------------------------------------

def _get_pds_fields(field_data) -> dict:
    """Break MasterCard PDS sub-fields out of a DE48/DE62/etc. field."""
    if isinstance(field_data, bytes):
        field_data = field_data.decode("latin-1")

    ptr = 0
    out = {}
    while ptr < len(field_data):
        tag = field_data[ptr: ptr + 4]
        try:
            length = int(field_data[ptr + 4: ptr + 7])
        except ValueError:
            break
        value = field_data[ptr + 7: ptr + 7 + length]
        out["PDS" + tag] = value
        ptr += 7 + length
    return out


def _get_de43_fields(field_data) -> dict:
    """Parse DE43 name/location field."""
    if isinstance(field_data, bytes):
        field_data = field_data.decode("latin-1")

    pattern = (
        r"(?P<DE43_NAME>.+?) *\\(?P<DE43_ADDRESS>.+?) *\\(?P<DE43_SUBURB>.+?) *\\"
        r"(?P<DE43_POSTCODE>\S{4,10}) *(?P<DE43_STATE>.{3})(?P<DE43_COUNTRY>.{3})"
    )
    m = re.match(pattern, field_data)
    if not m:
        return {}
    return m.groupdict()


def _get_icc_fields(field_data: bytes) -> dict:
    """Parse DE55 ICC / EMV TLV tags."""
    TWO_BYTE_PREFIXES = {b"\x9f", b"\x5f"}
    ptr = 0
    out = {"ICC_DATA": binascii.b2a_hex(field_data).decode()}

    while ptr < len(field_data):
        tag = field_data[ptr: ptr + 1]
        if tag in TWO_BYTE_PREFIXES:
            tag = field_data[ptr: ptr + 2]
            ptr += 2
        else:
            ptr += 1

        tag_hex = binascii.b2a_hex(tag).decode().upper()
        (length,) = struct.unpack(">B", field_data[ptr: ptr + 1])
        ptr += 1
        value = field_data[ptr: ptr + length]
        out["TAG" + tag_hex] = binascii.b2a_hex(value).decode()
        ptr += length

    return out


# ---------------------------------------------------------------------------
# Element processor
# ---------------------------------------------------------------------------

def _process_element(bit: int, cfg: dict, data: bytes, source_fmt: str) -> tuple[dict, int]:
    """Parse one ISO8583 field and return (values_dict, bytes_consumed)."""
    field_length = cfg["field_length"]
    length_size = _get_length_size(cfg["field_type"])

    if length_size > 0:
        raw_len = data[:length_size]
        if source_fmt == "ebcdic":
            raw_len = _eb2asc(raw_len)
        field_length = int(raw_len)

    field_data = data[length_size: length_size + field_length]
    processor = cfg.get("field_processor", "")

    # Decode unless ICC (raw binary)
    if processor != "ICC" and source_fmt == "ebcdic":
        field_data = _eb2asc(field_data)

    # Type conversion
    python_type = cfg.get("python_field_type", "")
    if python_type and processor != "ICC":
        field_data = _to_python_type(field_data, python_type)
    elif processor != "ICC" and isinstance(field_data, bytes):
        try:
            field_data = field_data.decode("latin-1")
        except Exception:
            pass

    out = {"DE" + str(bit): field_data}

    if processor == "PDS":
        out.update(_get_pds_fields(field_data))
    elif processor == "DE43":
        out.update(_get_de43_fields(field_data))
    elif processor == "ICC":
        out.update(_get_icc_fields(field_data))

    return out, field_length + length_size


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_record(message: bytes, bit_config: dict, source_fmt: str = "ascii") -> dict:
    """
    Parse a single ISO8583-style record into a flat dictionary.

    :param message:     Raw record bytes (MTI 4B + bitmap 16B + data).
    :param bit_config:  Field definitions loaded from mideu.yml.
    :param source_fmt:  'ascii' or 'ebcdic'.
    :returns:           Dict with keys MTI, DE2 … DE127, PDS*, TAG*, etc.
    """
    if len(message) < 20:
        LOGGER.debug("Record too short (%d bytes), skipping.", len(message))
        return {}

    msg_len = len(message) - 20
    mti_raw, bitmap_raw, msg_data = struct.unpack(
        "4s16s" + str(msg_len) + "s", message
    )

    mti = _eb2asc(mti_raw) if source_fmt == "ebcdic" else mti_raw
    try:
        mti = mti.decode("latin-1")
    except Exception:
        pass

    out = {"MTI": mti}
    bitmap = _get_bitmap_list(bitmap_raw)
    ptr = 0

    for bit in range(2, 128):
        if not bitmap[bit]:
            continue
        if bit not in bit_config:
            LOGGER.warning("No config for bit %d — skipping rest of record.", bit)
            break
        values, consumed = _process_element(
            bit, bit_config[bit], msg_data[ptr:], source_fmt
        )
        out.update(values)
        ptr += consumed

    return out