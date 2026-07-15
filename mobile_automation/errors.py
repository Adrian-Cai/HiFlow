from __future__ import annotations


class HiFlowMobileError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkflowError(HiFlowMobileError):
    pass


class AutomationError(HiFlowMobileError):
    pass


class UserActionRequired(AutomationError):
    pass
