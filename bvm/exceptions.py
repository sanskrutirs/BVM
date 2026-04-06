class VMException(Exception):
    pass

class OutOfGasError(VMException):
    pass

class StackUnderflowError(VMException):
    pass

class StackOverflowError(VMException):
    pass

class InvalidOpcodeError(VMException):
    pass

class InvalidJumpError(VMException):
    pass
