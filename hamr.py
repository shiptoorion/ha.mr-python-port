"""hamr.py — Port of ha.mr (https://github.com/p2r3/ha.mr), MIT License, Copyright (c) 2026 p2r3.
Code written by AI agent Kimi K3.

Воспроизводит `compress()` из compress.js бит-в-бит: те же словари Хаффмана
(hamr_data.py), та же арифметика произвольной точности (int вместо BigInt),
та же семантика нормализации URL (WHATWG URL, encodeURI/decodeURI).

Основной вход — функция `compress(link)`; `shorten(link)` возвращает готовую
ссылку вида "http://ha.mr#<payload>", идентичную той, что выдаёт сайт.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from hamr_data import (
    VERSION,
    TLD_ENCODE,
    SLD_ENCODE,
    DOMAIN_ENCODE,
    PATH_ENCODE,
    OUTPUT_ALPHABET_ASCII,
    OUTPUT_ALPHABET_QR,
    OUTPUT_ALPHABET_EMOJI,
)

__all__ = [
    "compress",
    "shorten",
    "decompress",
    "unshorten",
    "HamrError",
    "OUTPUT_ALPHABET_ASCII",
    "OUTPUT_ALPHABET_QR",
    "OUTPUT_ALPHABET_EMOJI",
]


class HamrError(ValueError):
    """Ссылка не может быть сжата (аналог "Invalid link" на сайте)."""


# --------------------------------------------------------------------------
# Данные из compress.js
# --------------------------------------------------------------------------

# Growing subcategories of the full URL alphabet
# Each also includes the hyphen and underscore as common separators
SUBALPHABETS = [
    # Numbers only
    "0123456789-_",
    # Uppercase only
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ-_",
    # Lowercase only
    "abcdefghijklmnopqrstuvwxyz-_",
    # Uppercase and numbers
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
    # Lowercase and numbers
    "abcdefghijklmnopqrstuvwxyz0123456789-_",
    # Uppercase and lowercase
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_",
    # Upercase, lowercase and numbers (base64)
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
    # Full alphabet without slash character
    "!#$&'()*+,-.0123456789:;=?~@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]_abcdefghijklmnopqrstuvwxyz%",
]

# Object.keys(sldEncode).sort((a, b) => b.length - a.length) — сортировка
# в JS стабильная, python sorted тоже: порядок совпадает.
SLD_LIST = sorted(SLD_ENCODE.keys(), key=len, reverse=True)

# Инвертированные словари для декодирования (код Хаффмана -> значение)
TLD_DECODE = {code: key for key, code in TLD_ENCODE.items()}
SLD_DECODE = {code: key for key, code in SLD_ENCODE.items()}
DOMAIN_DECODE = {code: key for key, code in DOMAIN_ENCODE.items()}
PATH_DECODE = {code: key for key, code in PATH_ENCODE.items()}


# --------------------------------------------------------------------------
# Битовый поток произвольной точности (аналог BigInt-арифметики из JS)
# --------------------------------------------------------------------------

def number_to_string(number: int, alphabet: list[str]) -> str:
    size = len(alphabet)
    out = []
    while number > 0:
        number -= 1
        out.append(alphabet[number % size])
        number //= size
    return "".join(out)


def huffman_encode(number: int, sequence: str) -> int:
    for i in range(len(sequence) - 1, -1, -1):
        number <<= 1
        if sequence[i] == "1":
            number += 1
    return number


def string_to_number(string: str, alphabet: list[str]) -> int:
    """Эквивалент stringToNumber() из compress.js.

    Алфавит упорядочен от длинных последовательностей к коротким (emoji),
    поэтому первое совпадение с конца строки — правильное.
    """
    size = len(alphabet)
    number = 0
    while string:
        digit = next((i for i, c in enumerate(alphabet) if string.endswith(c)), -1)
        if digit < 0:
            raise HamrError(f'Invalid character: "{string[-1]}"')
        number *= size
        number += digit
        number += 1
        string = string[: -len(alphabet[digit])]
    return number


def huffman_decode(number: int, lookup: dict[str, str]) -> tuple[int, str]:
    """Эквивалент huffmanDecode() из compress.js: (новое число, символ)."""
    sequence = ""
    while True:
        sequence += str(number & 1)
        number >>= 1
        if len(sequence) > 20:
            raise HamrError(f'Huffman sequence too long: "{sequence}".')
        if sequence in lookup:
            return number, lookup[sequence]


# --------------------------------------------------------------------------
# encodeURI / decodeURI (семантика ECMAScript)
# --------------------------------------------------------------------------

_ENCODE_URI_KEPT = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    ";,/?:@&=+$-_.!~*'()#"
)

# Байты зарезервированных символов, которые decodeURI НЕ раскодирует:
# ; / ? : @ & = + $ , #
_DECODE_URI_RESERVED = frozenset(
    (0x3B, 0x2F, 0x3F, 0x3A, 0x40, 0x26, 0x3D, 0x2B, 0x24, 0x2C, 0x23)
)

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def encode_uri(s: str) -> str:
    """Эквивалент JS encodeURI()."""
    out = []
    for ch in s:
        if ch in _ENCODE_URI_KEPT:
            out.append(ch)
        else:
            for byte in ch.encode("utf-8"):
                out.append("%{:02X}".format(byte))
    return "".join(out)


def decode_uri(s: str) -> str:
    """Эквивалент JS decodeURI(); бросает HamrError на malformed-последовательностях."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        if i + 2 >= n or s[i + 1] not in _HEX_DIGITS or s[i + 2] not in _HEX_DIGITS:
            raise HamrError(f"URIError: malformed URI sequence at index {i}")
        b0 = int(s[i + 1 : i + 3], 16)
        if b0 in _DECODE_URI_RESERVED:
            out.append(s[i : i + 3])
            i += 3
            continue
        # UTF-8 последовательность из %XX-байтов
        if b0 < 0x80:
            length = 1
        elif 0xC2 <= b0 <= 0xDF:
            length = 2
        elif 0xE0 <= b0 <= 0xEF:
            length = 3
        elif 0xF0 <= b0 <= 0xF4:
            length = 4
        else:
            raise HamrError(f"URIError: malformed URI sequence at index {i}")
        raw = bytearray([b0])
        for k in range(1, length):
            j = i + 3 * k
            if (
                j + 2 >= n
                or s[j] != "%"
                or s[j + 1] not in _HEX_DIGITS
                or s[j + 2] not in _HEX_DIGITS
            ):
                raise HamrError(f"URIError: malformed URI sequence at index {i}")
            raw.append(int(s[j + 1 : j + 3], 16))
        try:
            out.append(bytes(raw).decode("utf-8"))
        except UnicodeDecodeError:
            raise HamrError(f"URIError: malformed URI sequence at index {i}")
        i += 3 * length
    return "".join(out)


# --------------------------------------------------------------------------
# Минимальный WHATWG URL-парсер (подмножество, достаточное для compress())
# --------------------------------------------------------------------------

_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")

_SPECIAL_SCHEMES = frozenset(("http", "https", "ws", "wss", "ftp", "file"))
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}

# Запрещённые код-поинты в домене (WHATWG "forbidden domain code point")
_FORBIDDEN_DOMAIN = frozenset(
    "\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f"
    "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
    " #%/:<>?@[\\]^|"
)

# WHATWG percent-encode sets (дополнительные байты поверх C0+space+>0x7E)
_C0_EXTRA = frozenset()
_FRAGMENT_EXTRA = frozenset(b'"<>`')
_QUERY_EXTRA = _FRAGMENT_EXTRA | frozenset(b"#")
_SPECIAL_QUERY_EXTRA = _QUERY_EXTRA | frozenset(b"'")
_PATH_EXTRA = _QUERY_EXTRA | frozenset(b"?`{}")


def _percent_encode(s: str, extra: frozenset) -> str:
    out = []
    for ch in s:
        for byte in ch.encode("utf-8"):
            if byte < 0x21 or byte > 0x7E or byte in extra:
                out.append("%{:02X}".format(byte))
            else:
                out.append(chr(byte))
    return "".join(out)


def _form_decode(s: str) -> str:
    """application/x-www-form-urlencoded decode (URLSearchParams): '+' -> ' '."""
    s = s.replace("+", " ")
    out = bytearray()
    i = 0
    n = len(s)
    while i < n:
        if (
            s[i] == "%"
            and i + 2 < n
            and s[i + 1] in _HEX_DIGITS
            and s[i + 2] in _HEX_DIGITS
        ):
            out.append(int(s[i + 1 : i + 3], 16))
            i += 3
        else:
            out.extend(s[i].encode("utf-8"))
            i += 1
    return out.decode("utf-8", errors="replace")


def _ipv4_number(part: str) -> int:
    if part == "":
        raise ValueError("empty IPv4 part")
    base = 10
    digits = part
    if len(part) >= 2 and part[:2].lower() == "0x":
        base, digits = 16, part[2:]
    elif len(part) >= 2 and part[0] == "0":
        base, digits = 8, part[1:]
    if digits == "":
        return 0
    try:
        return int(digits, base)
    except ValueError:
        raise ValueError(f"invalid IPv4 part {part!r}") from None


_NUMERICISH_RE = re.compile(r"([0-9]+|0[xX][0-9a-fA-F]+)$")


def _maybe_ipv4(host: str) -> str:
    """WHATWG IPv4-парсер: срабатывает, если хост заканчивается числом."""
    parts = host.split(".")
    if parts and parts[-1] == "":
        parts = parts[:-1]  # trailing dot
    if not parts or not _NUMERICISH_RE.fullmatch(parts[-1]):
        return host
    nums = [_ipv4_number(p) for p in parts]
    if len(nums) > 4:
        raise ValueError("IPv4 too many parts")
    for n in nums[:-1]:
        if n > 255:
            raise ValueError("IPv4 part out of range")
    if nums[-1] >= 256 ** (5 - len(nums)):
        raise ValueError("IPv4 last part out of range")
    addr = nums[-1]
    for i, n in enumerate(nums[:-1]):
        addr += n * (256 ** (3 - i))
    return ".".join(str((addr >> shift) & 0xFF) for shift in (24, 16, 8, 0))


_DOT_SEGS = frozenset((".", "%2e"))
_DOTDOT_SEGS = frozenset(("..", ".%2e", "%2e.", "%2e%2e"))


def _resolve_dot_segments(path: str) -> str:
    """WHATWG 'shorten path': разрешение '.' и '..' (учитывая %2e-формы)."""
    segs = path.split("/")
    out: list[str] = []
    for idx, seg in enumerate(segs):
        low = seg.lower()
        is_last = idx == len(segs) - 1
        if low in _DOT_SEGS:
            if is_last:
                out.append("")
        elif low in _DOTDOT_SEGS:
            if out and out[-1] != "":
                out.pop()
            if is_last:
                out.append("")
        else:
            out.append(seg)
    return "/".join(out)


class _URL:
    __slots__ = ("protocol", "hostname", "port", "pathname", "search", "hash")


def _parse_url(input_str: str) -> _URL:
    """Упрощённый new URL() без базы. Невалидный ввод -> ValueError."""
    # WHATWG: убрать табы/переводы строк, обрезать C0-контролы и пробелы по краям
    s = input_str.replace("\t", "").replace("\n", "").replace("\r", "")
    s = s.strip("".join(chr(c) for c in range(0x21)))
    m = _SCHEME_RE.match(s)
    if not m:
        raise ValueError("missing URL scheme")
    scheme = m.group(1).lower()
    special = scheme in _SPECIAL_SCHEMES
    rest = s[m.end() :]

    url = _URL()
    url.protocol = scheme + ":"
    url.hostname = ""
    url.port = ""
    url.pathname = ""
    url.search = ""
    url.hash = ""

    authority = None
    if special:
        # Пропускаем ведущие '/' и '\' (special authority slashes)
        i = 0
        while i < len(rest) and rest[i] in "/\\":
            i += 1
        rest = rest[i:]
        m2 = re.search(r"[/\\?#]", rest)
        if m2:
            authority, rest = rest[: m2.start()], rest[m2.start() :]
        else:
            authority, rest = rest, ""
    elif rest.startswith("//"):
        m2 = re.search(r"[/?#]", rest[2:])
        if m2:
            cut = 2 + m2.start()
            authority, rest = rest[2:cut], rest[cut:]
        else:
            authority, rest = rest[2:], ""

    if authority is not None:
        url.hostname, url.port = _parse_authority(authority, scheme, special)
        if special and url.hostname == "":
            raise ValueError("empty host for special scheme")

    # --- path ---
    if special:
        q = re.search(r"[?#]", rest)
        path_raw = rest[: q.start()] if q else rest
        rest = rest[q.start() :] if q else ""
        path_raw = path_raw.replace("\\", "/")
        encoded = _percent_encode(path_raw, _PATH_EXTRA)
        url.pathname = _resolve_dot_segments(encoded)
        if url.pathname == "" or not url.pathname.startswith("/"):
            url.pathname = "/" + url.pathname if url.pathname else "/"
    elif authority is not None:
        q = re.search(r"[?#]", rest)
        path_raw = rest[: q.start()] if q else rest
        rest = rest[q.start() :] if q else ""
        encoded = _percent_encode(path_raw, _PATH_EXTRA)
        url.pathname = _resolve_dot_segments(encoded) if encoded.startswith("/") else encoded
    else:
        # opaque path (mailto:..., example.com:8080/path и т.п.)
        q = re.search(r"[?#]", rest)
        path_raw = rest[: q.start()] if q else rest
        rest = rest[q.start() :] if q else ""
        url.pathname = _percent_encode(path_raw, _C0_EXTRA)

    # --- query ---
    if rest.startswith("?"):
        qend = rest.find("#")
        qraw = rest[1:qend] if qend != -1 else rest[1:]
        encoded = _percent_encode(
            qraw, _SPECIAL_QUERY_EXTRA if special else _QUERY_EXTRA
        )
        if encoded:
            url.search = "?" + encoded
        rest = rest[qend:] if qend != -1 else ""

    # --- fragment ---
    if rest.startswith("#"):
        encoded = _percent_encode(rest[1:], _FRAGMENT_EXTRA)
        if encoded:
            url.hash = "#" + encoded

    return url


def _parse_authority(authority: str, scheme: str, special: bool) -> tuple[str, str]:
    # userinfo отбрасывается: берём часть после последнего '@'
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    if authority.startswith("["):
        end = authority.find("]")
        if end == -1:
            raise ValueError("unclosed IPv6")
        host, tail = authority[: end + 1], authority[end + 1 :]
        if tail.startswith(":"):
            port_str = tail[1:]
        elif tail:
            raise ValueError("garbage after IPv6")
        else:
            port_str = ""
    else:
        host, sep, port_str = authority.partition(":")
        if not sep:
            port_str = ""
    port = ""
    if port_str:
        if not port_str.isascii() or not port_str.isdigit():
            raise ValueError("non-numeric port")
        port_int = int(port_str)
        if port_int > 65535:
            raise ValueError("port out of range")
        if _DEFAULT_PORTS.get(scheme) != port_int:
            port = str(port_int)
    if host.startswith("["):
        return host.lower(), port  # IPv6: оставляем как есть (сожмётся не весь)

    # percent-decode хоста (UTF-8), как в WHATWG
    decoded = _form_decode(host)
    if any(ch in _FORBIDDEN_DOMAIN or ord(ch) < 0x20 for ch in decoded):
        raise ValueError("forbidden code point in host")
    decoded = decoded.lower()
    if decoded.isascii():
        ascii_host = decoded
    else:
        try:
            ascii_host = decoded.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise ValueError("IDN failure") from None
    if special:
        ascii_host = _maybe_ipv4(ascii_host)
    return ascii_host, port


def _can_parse(input_str: str) -> bool:
    try:
        _parse_url(input_str)
        return True
    except ValueError:
        return False


def _parse_search_params(search: str) -> list[str]:
    """Эквивалент Array.from(url.searchParams).flat()."""
    if not search.startswith("?"):
        return []
    flat: list[str] = []
    for piece in search[1:].split("&"):
        if piece == "":
            continue
        key, eq, value = piece.partition("=")
        flat.append(_form_decode(key))
        flat.append(_form_decode(value) if eq else "")
    return flat


# --------------------------------------------------------------------------
# compress() — точный порт из compress.js
# --------------------------------------------------------------------------

def compress(input: str, alphabet: list[str] | None = None) -> str:
    """Сжимает ссылку в payload, бит-в-бит как compress() из ha.mr.

    :param input: исходная ссылка (с протоколом или без)
    :param alphabet: выходной алфавит; по умолчанию outputAlphabetASCII
    :returns: payload-строка (не полная ссылка!)
    :raises HamrError: если ссылка невалидна или содержит неподдерживаемые символы
    """
    if alphabet is None:
        alphabet = OUTPUT_ALPHABET_ASCII

    number = 1

    # Validate URL, add protocol if needed
    try:
        url = _parse_url(input) if _can_parse(input) else _parse_url("http://" + input)
    except ValueError:
        raise HamrError(f"Invalid link: {input!r}") from None

    hostname = url.hostname.lower()
    port = int(url.port) if url.port else 0
    tld = hostname.split(".")[-1].lower() if "." in hostname else False

    if tld in TLD_ENCODE:
        hostname = ".".join(hostname.split(".")[:-1])

    is_https = url.protocol == "https:"
    has_www = url.hostname.lower().startswith("www.")
    if has_www:
        hostname = hostname[4:]

    known_sld = next((c for c in SLD_LIST if hostname.endswith(c)), "")
    subdomain = hostname[: -len(known_sld)] if known_sld else ""

    # Read URL path, split it into segments
    path = url.pathname

    # Remove "index" suffixes, encoded separately later
    has_index_html = path.endswith("/index.html")
    has_index_php = path.endswith("/index.php")
    if has_index_html:
        path = path[: -len("/index.html")]
    elif has_index_php:
        path = path[: -len("/index.php")]

    path_segments = [
        {"type": "path", "value": c} for c in path.split("/") if len(c)
    ]

    # Add search/query parameters to path segments
    for value in _parse_search_params(url.search):
        path_segments.append({"type": "query", "value": value})

    # Add hash value to path segments
    if url.hash and len(url.hash) > 1:
        path_segments.append({"type": "hash", "value": url.hash[1:]})

    # Normalize path segment encoding
    for segment in path_segments:
        segment["value"] = encode_uri(decode_uri(segment["value"]))

    # Encode path following domain segment-by-segment, using best algorithm for each
    last_segment_type = path_segments[-1]["type"] if path_segments else None
    query_param_index = 0
    for j in range(len(path_segments) - 1, -1, -1):
        segment = path_segments[j]
        first_iteration = j == len(path_segments) - 1
        if not first_iteration and query_param_index % 2 != 1:
            # Indicate change of segment type (path -> param -> hash)
            number <<= 1
            if last_segment_type == "hash" and segment["type"] == "query":
                number += 1
            elif last_segment_type == "hash" and segment["type"] == "path":
                number += 1
                number <<= 1
                number += 1
            elif last_segment_type != segment["type"]:
                number <<= 1
                number += 1
            last_segment_type = segment["type"]
        if segment["type"] == "query":
            query_param_index += 1

        # Look for smallest subalphabet that fits this path segment
        subalphabet = None
        subalphabet_index = -1
        for i, candidate in enumerate(SUBALPHABETS):
            if all(c in candidate for c in segment["value"]):
                subalphabet = candidate
                subalphabet_index = i
                break

        # Compute number after Huffman coding
        huffman_number = (
            number if first_iteration else huffman_encode(number, PATH_ENCODE["#"])
        )
        value = segment["value"]
        i = len(value) - 1
        while i >= 0:
            if i >= 2 and value[i - 2] == "%":
                byte = int(value[i - 1 : i + 1], 16)
                huffman_number *= 256
                huffman_number += byte
                huffman_number = huffman_encode(huffman_number, PATH_ENCODE["%"])
                i -= 3
                continue
            ch = value[i]
            if ch == "~":
                # HACK (как в оригинале): '~' нет в дереве Хаффмана,
                # кодируется как %-encoded байт 126
                huffman_number *= 256
                huffman_number += 126
                huffman_number = huffman_encode(huffman_number, PATH_ENCODE["%"])
            else:
                code = PATH_ENCODE.get(ch)
                if code is None:
                    raise HamrError(f"Invalid link: unsupported character {ch!r}")
                huffman_number = huffman_encode(huffman_number, code)
            i -= 1

        # Encode segment variant as 0
        # (+1 вводит 0 как специальное значение для Huffman)
        huffman_number *= len(SUBALPHABETS) + 1
        # If no subalphabet fits this segment, Huffman is the only option.
        if not subalphabet:
            number = huffman_number
            continue

        # Compute number after encoding with chosen subalphabet
        subalphabet_length = len(subalphabet) + 1
        subalphabet_number = (
            number if first_iteration else number * subalphabet_length
        )
        for i in range(len(value) - 1, -1, -1):
            subalphabet_number *= subalphabet_length
            subalphabet_number += subalphabet.index(value[i]) + 1
        # Encode segment variant as subalphabet index + 1
        subalphabet_number *= len(SUBALPHABETS) + 1
        subalphabet_number += subalphabet_index + 1
        # Compare candidate numbers, pick smallest one
        number = min(huffman_number, subalphabet_number)

    # Encode type of first path segment
    if path_segments:
        number *= 3
        first_type = path_segments[0]["type"]
        if first_type == "query":
            number += 1
        elif first_type == "hash":
            number += 2

    # Encode either SLD + subdomain or full hostname
    if not known_sld:
        # Write stopping token only if path follows
        if path_segments:
            number = huffman_encode(number, DOMAIN_ENCODE["END"])
        for i in range(len(hostname) - 1, -1, -1):
            code = DOMAIN_ENCODE.get(hostname[i])
            if code is None:
                raise HamrError(
                    f"Invalid link: unsupported host character {hostname[i]!r}"
                )
            number = huffman_encode(number, code)
    else:
        # Encode subdomain
        if subdomain:
            if path_segments:
                number = huffman_encode(number, DOMAIN_ENCODE["END"])
            for i in range(len(subdomain) - 1, -1, -1):
                code = DOMAIN_ENCODE.get(subdomain[i])
                if code is None:
                    raise HamrError(
                        f"Invalid link: unsupported host character {subdomain[i]!r}"
                    )
                number = huffman_encode(number, code)
        # Encode Huffman code of known SLD
        number = huffman_encode(number, SLD_ENCODE[known_sld])

    # Indicate presence of known SLD and optional subdomain
    if known_sld:
        number <<= 1
        if subdomain:
            number += 1
    number <<= 1
    if known_sld:
        number += 1

    # Encode "index.html"/"index.php" suffix
    number <<= 1
    if has_index_php:
        number += 1
    if has_index_html or has_index_php:
        number <<= 1
        number += 1
    # Encode protocol
    number <<= 1
    if is_https:
        number += 1
    # Encode "www." prefix
    number <<= 1
    if has_www:
        number += 1
    # Encode TLD
    number = huffman_encode(number, TLD_ENCODE.get(tld) or TLD_ENCODE[""])
    # Encode port number
    if port:
        number *= 65536
        number += port
    number <<= 1
    if port:
        number += 1

    # Encode version number
    for _ in range(VERSION):
        number <<= 1
        number += 1
    number <<= 1

    return number_to_string(number, alphabet)


def shorten(input: str, alphabet: list[str] | None = None) -> str:
    """Полная короткая ссылка, как на сайте: "http://ha.mr#<payload>"."""
    return f"http://ha.mr#{compress(input, alphabet)}"


# --------------------------------------------------------------------------
# decompress() — точный порт из compress.js
# --------------------------------------------------------------------------

def decompress(input: str, alphabet: list[str] | None = None) -> str:
    """Разжимает payload обратно в полную ссылку (порт decompress() из ha.mr).

    :param input: payload-строка (то, что идёт после "ha.mr#")
    :param alphabet: алфавит payload'а; по умолчанию outputAlphabetASCII
    :returns: полная ссылка
    :raises HamrError: если payload содержит чужеродные символы или битый поток
    """
    if alphabet is None:
        alphabet = OUTPUT_ALPHABET_ASCII

    number = string_to_number(input, alphabet)

    # Version number - currently unused
    version = 0
    while number & 1:
        version += 1
        number >>= 1
    number >>= 1

    # Decode port number
    has_port = number & 1
    number >>= 1
    port = 0
    if has_port:
        port = number % 65536
        number //= 65536
    # Decode TLD
    number, tld = huffman_decode(number, TLD_DECODE)
    # Decode "www." prefix
    has_www = number & 1
    number >>= 1
    # Decode protocol
    is_https = number & 1
    number >>= 1
    # Decode "index.html"/"index.php" suffix
    index_suffix = ""
    if number & 1:
        number >>= 1
        index_suffix = "/index.php" if (number & 1) else "/index.html"
    number >>= 1
    # Determine domain format
    has_known_sld = number & 1
    number >>= 1
    has_subdomain = False
    if has_known_sld:
        has_subdomain = bool(number & 1)
        number >>= 1

    domain = ""
    subdomain = ""
    path = ""

    if has_known_sld:
        number, domain = huffman_decode(number, SLD_DECODE)
        if has_subdomain:
            while number > 1:
                number, digit = huffman_decode(number, DOMAIN_DECODE)
                if digit == "END":
                    break
                subdomain += digit
    else:
        while number > 1:
            number, digit = huffman_decode(number, DOMAIN_DECODE)
            if digit == "END":
                break
            domain += digit

    segment_type_index = number % 3
    number //= 3
    current_segment_type = ("path", "query", "hash")[segment_type_index]

    query_param_index = 0

    while number > 1:
        if current_segment_type == "path":
            path += "/"
        elif current_segment_type == "hash":
            path += "#"
        else:
            if query_param_index % 2:
                path += "="
            elif query_param_index == 0:
                path += "?"
            else:
                path += "&"
            query_param_index += 1
        # Get path segment variant
        variant = number % (len(SUBALPHABETS) + 1)
        number //= len(SUBALPHABETS) + 1
        # Variant 0 is Huffman code, rest are subalphabets
        if variant == 0:
            while number > 1:
                number, digit = huffman_decode(number, PATH_DECODE)
                if digit == "#" and current_segment_type != "hash":
                    break
                path += digit
                if digit == "%":
                    byte = number % 256
                    path += format(byte, "02x")
                    number //= 256
        else:
            subalphabet = SUBALPHABETS[variant - 1]
            subalphabet_length = len(subalphabet) + 1
            while number > 1:
                index = number % subalphabet_length
                number //= subalphabet_length
                if index == 0:
                    break
                path += subalphabet[index - 1]
        # Handle changing between path segment types, unless we're in the
        # middle of decoding a query parameter key/value pair
        if query_param_index % 2:
            continue
        if number & 1:  # Changing segment type?
            if current_segment_type == "path":
                number >>= 1
                if number & 1:  # Skipping to hash?
                    current_segment_type = "hash"
                else:
                    current_segment_type = "query"
            else:
                current_segment_type = "hash"
        number >>= 1

    m = re.search(r"[?#]", path)
    path_before_query = path[: m.start()] if m else path
    path_from_query = path[m.start() :] if m else ""

    return (
        ("https://" if is_https else "http://")
        + ("www." if has_www else "")
        + subdomain
        + domain
        + ("." + tld if tld else "")
        + (":" + str(port) if has_port else "")
        + path_before_query
        + index_suffix
        + path_from_query
    )


def unshorten(link: str) -> str:
    """Разжимает короткую ссылку ha.mr обратно в исходную.

    Повторяет логику редиректа из main.js: payload берётся из "#..."
    (алфавит ASCII либо emoji — определяется по наличию не-ASCII символов),
    либо из пути (QR-форма "HTTP://HA.MR/<payload>", алфавит QR).
    """
    if "#" in link:
        payload = unquote(link.split("#", 1)[1]).replace(" ", "")
        ascii_set = set(OUTPUT_ALPHABET_ASCII)
        alphabet = (
            OUTPUT_ALPHABET_EMOJI
            if any(c not in ascii_set for c in payload)
            else OUTPUT_ALPHABET_ASCII
        )
    else:
        payload = unquote(link.rsplit("/", 1)[-1])
        alphabet = OUTPUT_ALPHABET_QR
    return decompress(payload, alphabet)
