"""平台公共错误：调用方只收到稳定码和允许公开的描述。"""


class PlatformError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


class PlatformConfigurationError(ValueError):
    """配置错误不能把原始 DSN、Token 或供应商响应写入异常。"""
