"""Chinese user-facing messages for write rejection codes."""

from zendure.protocols.local_http.write_errors import write_error_message


def test_content_length_error() -> None:
    assert write_error_message(400, "Invalid content length") == "请求内容长度无效"


def test_json_parse_error() -> None:
    assert write_error_message(400, "Failed to parse JSON") == "JSON解析失败"


def test_sn_mismatch_error() -> None:
    assert write_error_message(401, "SN does not match") == "设备序列号不匹配或缺失"


def test_invalid_sn_error() -> None:
    assert write_error_message(401, "invalid SN in JSON") == "设备序列号不匹配或缺失"


def test_buffer_overflow_error() -> None:
    assert (
        write_error_message(413, "Buffer overflow risk")
        == "接收缓冲区溢出或接收数据失败"
    )


def test_receive_data_failed() -> None:
    assert (
        write_error_message(413, "Failed to receive HTTP data")
        == "接收缓冲区溢出或接收数据失败"
    )


def test_tlv_failure_on_http_200() -> None:
    assert write_error_message(400, http_status=200) == "属性写入失败"


def test_code_400_fallback() -> None:
    assert write_error_message(400) == "请求参数错误"


def test_code_401_fallback() -> None:
    assert write_error_message(401) == "设备序列号不匹配或缺失"


def test_unknown_code_keeps_number() -> None:
    assert write_error_message(500) == "写入失败(错误码 500)"


def test_error_text_wins_over_shared_code() -> None:
    assert write_error_message(400, "Failed to parse JSON") == "JSON解析失败"
    assert write_error_message(400, "Invalid content length") == "请求内容长度无效"
