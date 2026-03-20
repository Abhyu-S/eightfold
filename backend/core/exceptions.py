class AgenticAuditorException(Exception):
    """Base exception for all custom Agentic Auditor exceptions."""
    pass

class FileTooLargeError(AgenticAuditorException):
    """Raised when a file exceeds the allowed processing size limit."""
    pass

class BrokenLinkError(AgenticAuditorException):
    """Raised when an extracted link is inaccessible, broken, or private."""
    pass
