"""异常基类（P1 最小可用版）

P1 只定义抽象基类，不定义具体业务异常。
各层在 P1 实现时按需继承 BaseAppException。
"""

from __future__ import annotations


class BaseAppException(Exception):
    """应用异常基类。

    所有业务异常继承此类，便于 cross 层统一捕获和处理。
    """

    def __init__(self, message: str = "", code: str = "UNKNOWN"):
        self.message = message
        self.code = code
        super().__init__(f"[{code}] {message}")


class ConfigError(BaseAppException):
    """配置错误——.env 缺失、字段类型不对等。"""

    def __init__(self, message: str = ""):
        super().__init__(message=message, code="CONFIG_ERROR")


class NotFoundError(BaseAppException):
    """资源未找到——文档、切片等不存在。"""

    def __init__(self, message: str = ""):
        super().__init__(message=message, code="NOT_FOUND")


class LLMError(BaseAppException):
    """LLM 调用异常——API 超时、限流、模型不可用等。"""

    def __init__(self, message: str = "", code: str = "LLM_ERROR"):
        super().__init__(message=message, code=code)