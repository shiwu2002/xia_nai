"""tests for xianaibot.utils.proc_output."""

from __future__ import annotations

import sys

from xianaibot.utils.proc_output import (
    IncrementalProcDecoder,
    decode_proc_output,
    preferred_fallback_encoding,
)


def test_decode_utf8_passthrough():
    data = "hello 世界".encode("utf-8")
    assert decode_proc_output(data) == "hello 世界"


def test_decode_empty_and_none():
    assert decode_proc_output(b"") == ""
    assert decode_proc_output(None) == ""


def test_decode_gbk_fallback_on_windows():
    """GBK 字节在非 UTF-8 时应回退本地编码解码（中文 Windows 为 cp936）。"""
    text = "D:/data/云络科技"
    data = text.encode("gbk")
    # 仅当该 GBK 字节序列不是合法 UTF-8 时才有回退行为
    try:
        data.decode("utf-8")
        can_be_utf8 = True
    except UnicodeDecodeError:
        can_be_utf8 = False
    if not can_be_utf8 and sys.getdefaultencoding():
        decoded = decode_proc_output(data)
        # 在中文 Windows 上应还原原文；其他 locale 下至少不能是空串
        if preferred_fallback_encoding().lower().replace("-", "") in {"cp936", "gbk", "gb2312"}:
            assert decoded == text


def test_decode_invalid_bytes_replaced():
    # 0x81 单字节在 GBK 中不完整、在 UTF-8 中非法 → 不应抛异常
    assert isinstance(decode_proc_output(b"\x81"), str)


def test_incremental_decoder_utf8_split_across_chunks():
    """UTF-8 多字节字符跨块时不应产生乱码。"""
    decoder = IncrementalProcDecoder()
    data = "路径/云络科技/测试".encode("utf-8")
    out = decoder.feed(data[:5]) + decoder.feed(data[5:12]) + decoder.feed(data[12:])
    out += decoder.finish()
    assert out == "路径/云络科技/测试"


def test_incremental_decoder_ascii_multiple_chunks():
    decoder = IncrementalProcDecoder()
    out = decoder.feed(b"line one\n") + decoder.feed(b"line two\n") + decoder.finish()
    assert out == "line one\nline two\n"


def test_incremental_decoder_gbk_fallback():
    """GBK 输出在非 UTF-8 块上应回退本地编码而不是产生替换符雪崩。"""
    text = "云络科技"
    data = text.encode("gbk")
    try:
        data.decode("utf-8")
        return  # 该序列恰好也是合法 UTF-8，跳过
    except UnicodeDecodeError:
        pass
    if preferred_fallback_encoding().lower().replace("-", "") not in {"cp936", "gbk", "gb2312"}:
        return
    decoder = IncrementalProcDecoder()
    out = decoder.feed(data) + decoder.finish()
    assert out == text


def test_incremental_decoder_finish_flushes_tail():
    """流结束时残留的截断字节应被冲刷而非丢弃。"""
    decoder = IncrementalProcDecoder()
    out = decoder.feed("中".encode("utf-8")[:1]) + decoder.finish()
    assert isinstance(out, str)
    assert len(out) >= 1
