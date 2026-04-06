from bvm.opcodes import Opcode
import javalang  # Java parser
from typing import Dict, List, Optional
import hashlib

class JavaCompiler:
    @staticmethod
    def compile(java_source: str):
        bytecode = bytearray()
        storage_map = {}  # Maps variable names to storage slots
        register_map = {}  # Maps variable names to memory registers (for optimization)
        jump_placeholders = []  # (position, label) tuples
        label_positions = {}    # label: position mappings
        loop_stack = []         # For break/continue handling
        next_register = 0       # Next available register

        def get_storage_slot(var_name: str) -> int:
            """Assign storage slots using hashing similar to Python compiler"""
            if var_name not in storage_map:
                hash_bytes = hashlib.sha256(var_name.encode()).digest()
                slot = int.from_bytes(hash_bytes[:2], 'big') % 256
                storage_map[var_name] = slot
                print(f"Slot {slot} assigned to '{var_name}'")
            return storage_map[var_name]

        def get_or_assign_register(var_name: str) -> int:
            """Get or assign a register for loop variables (optimization)"""
            nonlocal next_register
            if var_name not in register_map:
                register_map[var_name] = next_register
                next_register += 1
            return register_map[var_name]

        def is_loop_variable(var_name: str) -> bool:
            """Check if variable is a loop counter (for optimization)"""
            return var_name in register_map

        def load_variable(var_name: str):
            """Load variable value to stack, using register or storage"""
            if is_loop_variable(var_name):
                reg = register_map[var_name]
                bytecode.extend([Opcode.DUP0 + reg])  # Use appropriate DUP opcode
            else:
                slot = get_storage_slot(var_name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SLOAD])

        def store_variable(var_name: str):
            """Store stack top to variable, using register or storage"""
            if is_loop_variable(var_name):
                reg = register_map[var_name]
                if reg <= 16:  # We can use SWAP only up to 16
                    bytecode.extend([Opcode.SWAP1 + reg - 1, Opcode.POP])
                else:
                    # Fall back to storage for high registers
                    slot = get_storage_slot(var_name)
                    bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
            else:
                slot = get_storage_slot(var_name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])

        def compile_expression(expr) -> None:
            """Compile Java expressions to bytecode"""
            if isinstance(expr, javalang.tree.Literal):
                if expr.value.isdigit():
                    bytecode.extend([Opcode.PUSH1, int(expr.value)])
                else:
                    raise NotImplementedError("Only numeric literals supported")
            
            elif isinstance(expr, javalang.tree.MemberReference):
                load_variable(expr.member)
            
            elif isinstance(expr, javalang.tree.BinaryOperation):
                compile_expression(expr.operandl)
                compile_expression(expr.operandr)
                
                if expr.operator == '+': bytecode.append(Opcode.ADD)
                elif expr.operator == '-': bytecode.append(Opcode.SUB)
                elif expr.operator == '*': bytecode.append(Opcode.MUL)
                elif expr.operator == '/': bytecode.append(Opcode.DIV)
                elif expr.operator == '>': bytecode.append(Opcode.GT)
                elif expr.operator == '<': bytecode.append(Opcode.LT)
                elif expr.operator == '==': bytecode.append(Opcode.EQ)
                elif expr.operator == '>=': bytecode.append(Opcode.GTE)
                elif expr.operator == '<=': bytecode.append(Opcode.LTE)
                elif expr.operator == '++':  # Handle increment
                    bytecode.append(Opcode.PUSH1)
                    bytecode.append(1)
                    bytecode.append(Opcode.ADD)
            
            elif isinstance(expr, javalang.tree.Assignment):
                # First compile the right-hand side (value being assigned)
                compile_expression(expr.value)
                
                # Then handle the left-hand side (target)
                if isinstance(expr.expressionl, javalang.tree.MemberReference):
                    store_variable(expr.expressionl.member)
                else:
                    raise NotImplementedError("Complex left-hand assignments not supported")
            
            elif isinstance(expr, javalang.tree.MethodInvocation):
                if expr.member == 'println':
                    compile_expression(expr.arguments[0])
                    bytecode.append(Opcode.PRINT)
            else:
                raise NotImplementedError(f"Expression type {type(expr)} not supported")

        def handle_if(node: javalang.tree.IfStatement) -> None:
            """Compile if statements with possible else"""
            else_label = f"else_{len(jump_placeholders)}"
            end_label = f"end_{len(jump_placeholders)+1}"
            
            # Compile condition
            compile_expression(node.condition)
            
            # Jump if false
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, else_label))
            bytecode.append(Opcode.JUMPI)
            
            # Compile if body (which is a BlockStatement)
            if node.then_statement:
                handle_statement(node.then_statement)
            
            # Jump to end
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)
            
            # Else label
            label_positions[else_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile else if exists
            if node.else_statement:
                handle_statement(node.else_statement)
                
            # End label
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
    
        def handle_for(node: javalang.tree.ForStatement) -> None:
            """Compile Java for loops to bytecode - optimized for gas efficiency"""
            loop_id = len(loop_stack)
            start_label = f"for_start_{loop_id}"
            condition_label = f"for_condition_{loop_id}"
            update_label = f"for_update_{loop_id}"
            end_label = f"for_end_{loop_id}"
            
            # Push loop context for break/continue
            loop_stack.append((update_label, end_label))
            
            # Identify loop variables for optimization
            loop_vars = set()
            if node.control and node.control.init:
                for init in node.control.init:
                    if isinstance(init, javalang.tree.VariableDeclaration):
                        for declarator in init.declarators:
                            loop_vars.add(declarator.name)
                            get_or_assign_register(declarator.name)
            
            # Compile initialization
            if node.control and node.control.init:
                for init in node.control.init:
                    if isinstance(init, javalang.tree.VariableDeclaration):
                        for declarator in init.declarators:
                            if declarator.initializer:
                                compile_expression(declarator.initializer)
                            else:
                                # Initialize to 0 if no initializer
                                bytecode.extend([Opcode.PUSH1, 0])
                            store_variable(declarator.name)
    
            # Condition label
            label_positions[condition_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile condition
            if node.control and node.control.condition:
                compile_expression(node.control.condition)
                # If condition is false (zero), jump to end
                bytecode.append(Opcode.ISZERO)
                bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
                jump_placeholders.append((len(bytecode)-1, end_label))
                bytecode.append(Opcode.JUMPI)
            
            # Body label
            label_positions[start_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile loop body
            if node.body:
                handle_statement(node.body)
            
            # Update label
            label_positions[update_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile update - optimized for i++ type updates
            if node.control and node.control.update:
                for update in node.control.update:
                    if isinstance(update, javalang.tree.UnaryOperation) and update.operator == '++':
                        if isinstance(update.expression, javalang.tree.MemberReference):
                            var_name = update.expression.member
                            if var_name in loop_vars:
                                # Optimized i++ for loop variables
                                load_variable(var_name)
                                bytecode.extend([Opcode.PUSH1, 1, Opcode.ADD])
                                store_variable(var_name)
                    elif isinstance(update, javalang.tree.Assignment):
                        # Optimized variable update
                        if isinstance(update.expressionl, javalang.tree.MemberReference):
                            var_name = update.expressionl.member
                            # For i = i + 1 pattern
                            if isinstance(update.value, javalang.tree.BinaryOperation) and update.value.operator == '+':
                                if var_name in loop_vars:
                                    # Load current value
                                    load_variable(var_name)
                                    # Add 1
                                    bytecode.extend([Opcode.PUSH1, 1, Opcode.ADD])
                                    # Store back
                                    store_variable(var_name)
                                    continue
                            # Default case
                            compile_expression(update)
                    else:
                        compile_expression(update)
            
            # Jump back to condition check
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, condition_label))
            bytecode.append(Opcode.JUMP)
            
            # End label
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Write register values back to storage at end of loop if needed
            for var_name in loop_vars:
                if is_loop_variable(var_name):
                    slot = get_storage_slot(var_name)
                    reg = register_map[var_name]
                    if reg <= 16:  # Can only access certain registers directly
                        bytecode.extend([Opcode.DUP0 + reg, Opcode.PUSH1, slot, Opcode.SSTORE])
            
            # Pop loop context
            loop_stack.pop()

        def handle_while(node: javalang.tree.WhileStatement) -> None:
            """Compile while loops with break/continue support"""
            loop_id = len(loop_stack)
            condition_label = f"while_condition_{loop_id}"
            body_label = f"while_body_{loop_id}"
            end_label = f"while_end_{loop_id}"
            
            # Push loop context for break/continue
            loop_stack.append((condition_label, end_label))
            
            # Condition label
            label_positions[condition_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Condition
            compile_expression(node.condition)
            
            # If condition is false (zero), jump to end
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMPI)
            
            # Body label
            label_positions[body_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Body
            handle_statement(node.body)
            
            # Jump back to condition
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, condition_label))
            bytecode.append(Opcode.JUMP)
            
            # End label
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Pop loop context
            loop_stack.pop()

        def handle_break() -> None:
            """Handle break statements"""
            if not loop_stack:
                raise SyntaxError("break outside loop")
            _, end_label = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)

        def handle_continue() -> None:
            """Handle continue statements"""
            if not loop_stack:
                raise SyntaxError("continue outside loop")
            start_label, _ = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, start_label))
            bytecode.append(Opcode.JUMP)

        def handle_statement(node) -> None:
            """Route to appropriate statement handler"""
            if isinstance(node, javalang.tree.IfStatement):
                handle_if(node)
            elif isinstance(node, javalang.tree.WhileStatement):
                handle_while(node)
            elif isinstance(node, javalang.tree.ForStatement):
                handle_for(node)
            elif isinstance(node, javalang.tree.BreakStatement):
                handle_break()
            elif isinstance(node, javalang.tree.ContinueStatement):
                handle_continue()
            elif isinstance(node, javalang.tree.VariableDeclaration):
                # Variable declaration with optional init
                for declarator in node.declarators:
                    if declarator.initializer:
                        compile_expression(declarator.initializer)
                    else:
                        # Initialize to 0 if no initializer
                        bytecode.extend([Opcode.PUSH1, 0])
                    store_variable(declarator.name)
            elif isinstance(node, javalang.tree.StatementExpression):
                # Expression statements (method calls, assignments)
                compile_expression(node.expression)
                
                # Only pop if the expression is not an assignment
                if not isinstance(node.expression, javalang.tree.Assignment):
                    bytecode.append(Opcode.POP)
            elif isinstance(node, javalang.tree.BlockStatement):
                # Handle blocks of statements
                if hasattr(node, 'statements'):
                    for stmt in node.statements:
                        handle_statement(stmt)
            else:
                raise NotImplementedError(f"Statement type {type(node)} not supported")

        # Parse and compile the Java code
        try:
            tree = javalang.parse.parse(java_source)
            
            # Find main method and compile it
            for path, node in tree.filter(javalang.tree.MethodDeclaration):
                if node.name == 'main':
                    for stmt in node.body:
                        handle_statement(stmt)
                    break
            
            # Ensure final values are written to storage
            for var_name, reg in register_map.items():
                if reg <= 16:  # Can only access certain registers directly
                    slot = get_storage_slot(var_name)
                    bytecode.extend([Opcode.DUP0 + reg, Opcode.PUSH1, slot, Opcode.SSTORE])
            
            # Resolve jump targets
            for pos, label in jump_placeholders:
                if label in label_positions:
                    bytecode[pos] = label_positions[label]
                else:
                    raise Exception(f"Undefined label: {label}")
            
            bytecode.append(Opcode.STOP)
            return bytes(bytecode), storage_map
            
        except Exception as e:
            raise CompilationError(f"Compilation failed: {str(e)}") from e

class CompilationError(Exception):
    pass
