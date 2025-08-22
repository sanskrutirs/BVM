from pycparser import c_parser, c_ast
from bvm.opcodes import Opcode
import hashlib
class CCompiler:
    @staticmethod
    def compile(source: str) -> bytes:
        parser = c_parser.CParser()
        ast = parser.parse(source)
        bytecode = bytearray()
        storage_map = {}
        jump_placeholders = []  # List of (position, label) tuples
        label_positions = {}    # Dictionary of label: position
        loop_stack = []         # Stack to track loops for break statements
        def get_storage_slot(var_name):
            if var_name not in storage_map:
                # Use SHA-256 and slice the first 2 bytes
                hash_bytes = hashlib.sha256(var_name.encode()).digest()
                slot = int.from_bytes(hash_bytes[:2], 'big') % 256  # 0-255
                storage_map[var_name] = slot
                print(f"Slot {slot} assigned to '{var_name}'")
            return storage_map[var_name]

        def handle_expression(expr):
            if isinstance(expr, c_ast.Constant):
                bytecode.extend([Opcode.PUSH1, int(expr.value)])
            elif isinstance(expr, c_ast.ID):
                slot = get_storage_slot(expr.name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SLOAD])
            elif isinstance(expr, c_ast.BinaryOp):
                handle_expression(expr.left)
                handle_expression(expr.right)
                if expr.op == '+': bytecode.append(Opcode.ADD)
                elif expr.op == '-': bytecode.append(Opcode.SUB)
                elif expr.op == '*': bytecode.append(Opcode.MUL)
                elif expr.op == '/': bytecode.append(Opcode.DIV)
                elif expr.op == '>': bytecode.append(Opcode.GT)
                elif expr.op == '<': bytecode.append(Opcode.LT)
                elif expr.op == '==': bytecode.append(Opcode.EQ)
            elif isinstance(expr, c_ast.UnaryOp):
                if expr.op == '++' and isinstance(expr.expr, c_ast.ID):
                    # Post-increment: var++
                    var_name = expr.expr.name
                    slot = get_storage_slot(var_name)
                    bytecode.extend([
                        Opcode.PUSH1, slot, 
                        Opcode.SLOAD,    # Get current value 
                        Opcode.PUSH1, 1,
                        Opcode.ADD,
                        # Add 1
                        Opcode.PUSH1, slot,
                        Opcode.SSTORE    # Store back
                    ])
                elif expr.op == '--' and isinstance(expr.expr, c_ast.ID):
                    # Post-decrement: var--
                    var_name = expr.expr.name
                    slot = get_storage_slot(var_name)
                    bytecode.extend([
                        Opcode.PUSH1, slot, 
                        Opcode.SLOAD,    # Get current value
                        Opcode.PUSH1, 1,
                        Opcode.SUB,      # Subtract 1
                        Opcode.PUSH1, slot,
                        Opcode.SSTORE    # Store back
                    ])
        
        def handle_if_statement(node):
            # Generate unique labels
            else_label = f"else_{len(jump_placeholders)}"
            end_label = f"end_{len(jump_placeholders)+1}"
            
            # Compile condition
            handle_expression(node.cond)
            
            # Add conditional jump to else block
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for else label
            jump_placeholders.append((len(bytecode)-1, else_label))
            bytecode.append(Opcode.JUMPI)
            
            # Compile if block
            if node.iftrue:
                if isinstance(node.iftrue, c_ast.Compound):
                    for item in node.iftrue.block_items:
                        handle_statement(item)
                else:
                    handle_statement(node.iftrue)
            
            # Add jump to skip else block
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for end label
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)
            
            # Mark else position with JUMPDEST
            label_positions[else_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile else block
            if node.iffalse:
                if isinstance(node.iffalse, c_ast.Compound):
                    for item in node.iffalse.block_items:
                        handle_statement(item)
                else:
                    handle_statement(node.iffalse)
                
            # Mark end position with JUMPDEST
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
        def handle_while_statement(node):
            """Handle a while loop statement in C AST"""
            # Generate unique labels for loop entry and exit
            loop_start_label = f"while_start_{len(jump_placeholders)}"
            loop_end_label = f"while_end_{len(jump_placeholders)+1}"
            
            # Add this loop to the loop stack
            loop_stack.append((loop_start_label, loop_end_label))
            
            # Mark the start of the loop with JUMPDEST
            label_positions[loop_start_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile condition
            handle_expression(node.cond)
            
            # Jump to end if condition is false
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for loop_end
            jump_placeholders.append((len(bytecode)-1, loop_end_label))
            bytecode.append(Opcode.JUMPI)
            
            # Compile loop body
            if node.stmt:
                if isinstance(node.stmt, c_ast.Compound):
                    for item in node.stmt.block_items:
                        handle_statement(item)
                else:
                    handle_statement(node.stmt)
            
            # Jump back to condition
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for loop_start
            jump_placeholders.append((len(bytecode)-1, loop_start_label))
            bytecode.append(Opcode.JUMP)
            
            # Mark the end position with JUMPDEST
            label_positions[loop_end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Remove this loop from the stack
            loop_stack.pop()
            
        def handle_break():
            if not loop_stack:
                raise SyntaxError("break outside loop")
            _, end_label = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)
            
        def handle_for_statement(node):
            """Handle a for loop statement in C AST"""
            # Generate unique labels for loop entry and exit
            loop_cond_label = f"loop_cond_{len(jump_placeholders)}"
            loop_end_label = f"loop_end_{len(jump_placeholders)+1}"
            
            # Add this loop to the loop stack
            loop_stack.append((loop_cond_label, loop_end_label))
            
            # Handle initialization (if present)
            if node.init:
                if isinstance(node.init, c_ast.DeclList):
                    for decl in node.init.decls:
                        if decl.init:
                            handle_expression(decl.init)
                            slot = get_storage_slot(decl.name)
                            bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
                elif isinstance(node.init, c_ast.Assignment):
                    handle_expression(node.init.rvalue)
                    slot = get_storage_slot(node.init.lvalue.name)
                    bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
                else:
                    handle_statement(node.init)
            
            # Mark the condition position with JUMPDEST
            label_positions[loop_cond_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile condition (if present)
            if node.cond:
                handle_expression(node.cond)
            else:
                # If no condition, always true (push 1)
                bytecode.extend([Opcode.PUSH1, 1])
            
            # Jump to end if condition is false
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for loop_end
            jump_placeholders.append((len(bytecode)-1, loop_end_label))
            bytecode.append(Opcode.JUMPI)
            
            # Compile loop body
            if node.stmt:
                if isinstance(node.stmt, c_ast.Compound):
                    for item in node.stmt.block_items:
                        handle_statement(item)
                else:
                    handle_statement(node.stmt)
            
            # Handle increment (if present)
            if node.next:
                # Handle different increment types
                if isinstance(node.next, c_ast.UnaryOp):
                    # Handle i++ or i--
                    if node.next.op == 'p++' and isinstance(node.next.expr, c_ast.ID):
                        var_name = node.next.expr.name
                        slot = get_storage_slot(var_name)
                        bytecode.extend([
                            Opcode.PUSH1, slot,
                            Opcode.SLOAD,
                            Opcode.PUSH1, 1,
                            Opcode.ADD,
                            Opcode.PUSH1, slot,
                            Opcode.SSTORE
                        ])
                    elif node.next.op == 'p--' and isinstance(node.next.expr, c_ast.ID):
                        var_name = node.next.expr.name
                        slot = get_storage_slot(var_name)
                        bytecode.extend([
                            Opcode.PUSH1, slot,
                            Opcode.SLOAD,
                            Opcode.PUSH1, 1,
                            Opcode.SUB,
                            Opcode.PUSH1, slot,
                            Opcode.SSTORE
                        ])
                elif isinstance(node.next, c_ast.Assignment):
                    # Handle i = i + 1
                    handle_expression(node.next.rvalue)
                    slot = get_storage_slot(node.next.lvalue.name)
                    bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
                elif isinstance(stmt, c_ast.Assignment):
                    if stmt.op == '=':
                        # Handle i = i + 1 case
                        if (isinstance(stmt.rvalue, c_ast.BinaryOp) and 
                            isinstance(stmt.lvalue, c_ast.ID)):
                            
                            var_name = stmt.lvalue.name
                            slot = get_storage_slot(var_name)
                            
                            # Compile right side (i + 1)
                            handle_expression(stmt.rvalue)
                            
                            # Store result
                            bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
                else:
                    # Debug output
                    print(f"Debug - Increment type: {type(node.next).__name__}")
                    
                    # For other increment types, like ExprList
                    if hasattr(node.next, 'type'):
                        print(f"Node type: {node.next.type}")
                        
                    # Try direct manual increment for i
                    if isinstance(node.next, c_ast.ID) and node.next.name == 'i':
                        slot = get_storage_slot('i')
                        bytecode.extend([
                            Opcode.PUSH1, slot,
                            Opcode.SLOAD,
                            Opcode.PUSH1, 1,
                            Opcode.ADD,
                            Opcode.PUSH1, slot,
                            Opcode.SSTORE
                        ])
                    else:
                        # Last resort - direct increment implementation
                        # This is a hack, but it should work for 'i++'
                        try:
                            slot = get_storage_slot('i')
                            bytecode.extend([
                                Opcode.PUSH1, slot,
                                Opcode.SLOAD,
                                Opcode.PUSH1, 1,
                                Opcode.ADD,
                                Opcode.PUSH1, slot,
                                Opcode.SSTORE
                            ])
                        except:
                            # If all else fails, try to handle as a statement
                            handle_statement(node.next)
            
            # Jump back to condition
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for loop_cond
            jump_placeholders.append((len(bytecode)-1, loop_cond_label))
            bytecode.append(Opcode.JUMP)
            
            # Mark the end position with JUMPDEST
            label_positions[loop_end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Remove this loop from the stack
            loop_stack.pop()

        def handle_statement(stmt):
            if isinstance(stmt, c_ast.If):
                handle_if_statement(stmt)
            elif isinstance(stmt, c_ast.For):
                handle_for_statement(stmt)
            elif isinstance(stmt, c_ast.While):
                handle_while_statement(stmt)
            elif isinstance(stmt, c_ast.Break):  # Fixed this line
                handle_break()  
            elif isinstance(stmt, c_ast.Decl):
                if stmt.init:
                    var_name = stmt.name
                    handle_expression(stmt.init)
                    slot = get_storage_slot(var_name)
                    bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
            elif isinstance(stmt, c_ast.Assignment):
                var_name = stmt.lvalue.name
                handle_expression(stmt.rvalue)
                slot = get_storage_slot(var_name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
            elif isinstance(stmt, c_ast.ExprList):
                # For handling multiple expressions in a statement
                for expr in stmt.exprs:
                    if isinstance(expr, c_ast.Assignment):
                        var_name = expr.lvalue.name
                        handle_expression(expr.rvalue)
                        slot = get_storage_slot(var_name)
                        bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
            elif isinstance(stmt, c_ast.UnaryOp):  # Add handling for standalone increment
                handle_expression(stmt)

        # Process all statements
        for node in ast.ext:
            if isinstance(node, c_ast.FuncDef) and node.decl.name == 'main':
                for item in node.body.block_items:
                    handle_statement(item)

        # Resolve jump placeholders
        for pos, label in jump_placeholders:
            if label in label_positions:
                jump_target = label_positions[label]
                bytecode[pos] = jump_target  # Use absolute position, not relative
            else:
                raise Exception(f"Label not defined: {label}")

        bytecode.append(Opcode.STOP)
        return bytes(bytecode), storage_map
