"""Map device write rejection codes to Chinese user-facing messages.

Several device codes (400, 401) cover more than one cause. The English
``error`` text in the reply is the discriminator; if it is missing, the
numeric code gets a generic Chinese fallback.
"""

from typing import Final

_ERROR_TEXT: Final[tuple[tuple[str, str], ...]] = (
    ("invalid content length", "请求内容长度无效"),
    ("failed to parse json", "JSON解析失败"),
    ("sn does not match", "设备序列号不匹配或缺失"),
    ("invalid sn in json", "设备序列号不匹配或缺失"),
    ("buffer overflow risk", "接收缓冲区溢出或接收数据失败"),
    ("failed to receive http data", "接收缓冲区溢出或接收数据失败"),
)

_CODE_FALLBACK: Final[dict[int, str]] = {
    400: "请求参数错误",
    401: "设备序列号不匹配或缺失",
    413: "接收缓冲区溢出或接收数据失败",
}

_TLV_FAILURE: Final = "属性写入失败"


def write_error_message(
    code: int,
    error: str | None = None,
    *,
    http_status: int | None = None,
) -> str:
    """Return the Chinese message for a write rejection.

    ``http_status=200`` plus device ``code=400`` is the TLV write failure
    (the device accepted HTTP, then failed to apply properties).
    """
    if error:
        lowered = error.casefold()
        for needle, message in _ERROR_TEXT:
            if needle in lowered:
                return message
    if http_status == 200 and code == 400:
        return _TLV_FAILURE
    return _CODE_FALLBACK.get(code, f"写入失败(错误码 {code})")


__all__ = ["write_error_message"]
