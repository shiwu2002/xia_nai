"""子进程输出解码工具。

背景
====
Windows 下，子进程写入管道的文本默认使用 ANSI 代码页（中文系统为
cp936/GBK），而非 UTF-8。若按 UTF-8 解码，中文输出（如路径中的用户名）
会变成乱码 replacement 字符。但跨平台开发工具（git、node、 ripgrep 等）
又普遍输出 UTF-8，不能一律按本地编码解。

本模块提供「先按 UTF-8 严格解码，失败再回退系统本地编码」的策略：

- :func:`decode_proc_output`：一次性解码完整输出（如 ``communicate()``）。
- :class:`IncrementalProcDecoder`：流式增量解码，处理多字节字符被
  read() 块边界截断的情况。
"""

from __future__ import annotations

import locale

__all__ = ["decode_proc_output", "preferred_fallback_encoding", "IncrementalProcDecoder"]


def preferred_fallback_encoding() -> str:
    """返回子进程输出的回退编码（Windows ANSI 代码页 / Unix locale）。"""
    try:
        return locale.getencoding()  # Python 3.11+
    except AttributeError:  # 兼容旧解释器
        return locale.getpreferredencoding(False)


def decode_proc_output(data: bytes | None) -> str:
    """解码一次性收到的完整子进程输出。

    优先按 UTF-8 严格解码；失败时回退到系统本地编码
    （Windows 中文环境为 cp936），仍失败则按 UTF-8 宽松解码。
    """
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode(preferred_fallback_encoding(), errors="replace")
    except (UnicodeDecodeError, LookupError):
        return data.decode("utf-8", errors="replace")


class IncrementalProcDecoder:
    """流式子进程输出的增量解码器。

    每收到一个数据块调用 :meth:`feed`；流结束时调用 :meth:`finish`
    冲刷残留字节。对 UTF-8 流，若解码错误仅因块边界截断了末尾的
    多字节字符，则保留尾部字节等待下一个数据块，避免误回退造成乱码；
    对本地编码（GBK 等）流，按块回退解码，个别跨块字符可能出现
    替换符（与旧实现的 UTF-8 行为一致，属可接受降级）。
    """

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, data: bytes) -> str:
        """解码一个数据块，返回该块对应的文本（可能延迟末尾截断字节）。"""
        if not data:
            return ""
        self._buf += data
        return self._drain(final=False)

    def finish(self) -> str:
        """流结束时冲刷残留缓冲，返回剩余文本。"""
        text = self._drain(final=True)
        if self._buf:
            # 理论上 _drain(final=True) 已清空，此处兜底防遗留
            text += decode_proc_output(self._buf)
            self._buf = b""
        return text

    def _drain(self, *, final: bool) -> str:
        buf = self._buf
        if not buf:
            return ""
        try:
            buf.decode("utf-8")
        except UnicodeDecodeError:
            # 检查错误是否仅由末尾被截断的多字节字符引起：
            # 去掉末尾 1~3 字节后能完整解码 → 保留尾部等待更多数据。
            if not final:
                for keep in (1, 2, 3):
                    tail = buf[-keep:]
                    try:
                        text = buf[:-keep].decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    # 尾部必须以多字节序列的 lead/continuation 字节开头，
                    # 纯 ASCII 结尾不可能被截断，直接整块解码。
                    if tail[0] >= 0x80:
                        self._buf = tail
                        return text
            # 非截断错误或已到流末尾：整块回退本地编码。
            self._buf = b""
            return decode_proc_output(buf)
        self._buf = b""
        return buf.decode("utf-8")
