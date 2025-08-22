class Opcode:
    # Arithmetic operations
    ADD = 0x01
    SUB = 0x02
    MUL = 0x03
    DIV = 0x04
    
    # Stack operations
    PUSH1 = 0x60
    POP = 0x50
    
    # Control flow
    STOP = 0x00
    
    # Storage
    SSTORE = 0x55
    SLOAD = 0x54
    
    # Modulo operation
    MOD = 0x05
    
    # Comparison operations
    LT = 0x10    # Less than
    GT = 0x11    # Greater than
    EQ = 0x12    # Equal to
    LTE = 0x14
    GTE = 0x15
    
    # Boolean operations
    ISZERO = 0x13  # Logical NOT

    # Control flow operations
    JUMP = 0x56      # Unconditional jump
    JUMPI = 0x57     # Conditional jump
    JUMPDEST = 0x5b  # Jump destination marker
    PC = 0x58        # Program counter

OPCODE_NAMES = {
    0x01: 'ADD',
    0x02: 'SUB',
    0x03: 'MUL',
    0x04: 'DIV',
    0x60: 'PUSH1',
    0x50: 'POP',
    0x00: 'STOP',
    0x55: 'SSTORE',
    0x54: 'SLOAD',
    0x56: 'JUMP',
    0x57: 'JUMPI', 
    0x5B: 'JUMPDEST',
    0x58: 'PC',
    0x11: 'GT',
    0x10: 'LT',
    0x12: 'EQ',
    0x13: 'ISZERO',
    0x14: 'LTE',
    0x15: 'GTE'
}

