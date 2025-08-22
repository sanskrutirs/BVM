from bvm.opcodes import Opcode
import esprima
import hashlib

class JSCompiler:
    @staticmethod
    def compile(contract_source):
        bytecode = bytearray()
        storage_map = {}
        jump_placeholders = []  # List of (position, label) tuples
        label_positions = {}    # Dictionary of label: position
        loop_stack = []

        def get_storage_slot(var_name):
            if var_name not in storage_map:
                # Use SHA-256 and slice the first 2 bytes
                hash_bytes = hashlib.sha256(var_name.encode()).digest()
                slot = int.from_bytes(hash_bytes[:2], 'big') % 256  # 0-255
                storage_map[var_name] = slot
                print(f"Slot {slot} assigned to '{var_name}'")
            return storage_map[var_name]

        def compile_expression(expr):
            if expr.type == 'Literal':
                if isinstance(expr.value, bool):
                    bytecode.extend([Opcode.PUSH1, 1 if expr.value else 0])
                else:
                    bytecode.extend([Opcode.PUSH1, expr.value])
            elif expr.type == 'Identifier':
                slot = get_storage_slot(expr.name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SLOAD])
            elif expr.type == 'BinaryExpression':
                compile_expression(expr.left)
                compile_expression(expr.right)
                if expr.operator == '+': bytecode.append(Opcode.ADD)
                elif expr.operator == '-': bytecode.append(Opcode.SUB)
                elif expr.operator == '*': bytecode.append(Opcode.MUL)
                elif expr.operator == '/': bytecode.append(Opcode.DIV)
                elif expr.operator == '>': bytecode.append(Opcode.GT)
                elif expr.operator == '<': bytecode.append(Opcode.LT)
                elif expr.operator == '==': bytecode.append(Opcode.EQ)
                elif expr.operator == '>=': bytecode.append(Opcode.GTE)
                elif expr.operator == '<=': bytecode.append(Opcode.LTE)
            elif expr.type == 'UnaryExpression' and expr.operator == '!':
                compile_expression(expr.argument)
                bytecode.append(Opcode.ISZERO)

        def handle_if_statement(node):
            # Generate unique labels
            if_id = len(jump_placeholders)
            else_label = f"else_{if_id}"
            end_label = f"end_{if_id}"
            
            # Compile condition
            compile_expression(node.test)
            
            # Add conditional jump to else block
            bytecode.append(Opcode.ISZERO)  # Jump if condition is false
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, else_label))
            bytecode.append(Opcode.JUMPI)
            
            # Compile if body
            handle_statement(node.consequent)
            
            # Add jump to skip else block
            if node.alternate:
                bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
                jump_placeholders.append((len(bytecode)-1, end_label))
                bytecode.append(Opcode.JUMP)
                
                # Mark else position
                label_positions[else_label] = len(bytecode)
                bytecode.append(Opcode.JUMPDEST)
                
                # Compile else body
                handle_statement(node.alternate)
                
                # Mark end position
                label_positions[end_label] = len(bytecode)
                bytecode.append(Opcode.JUMPDEST)
            else:
                # No else block, just mark else position as end
                label_positions[else_label] = len(bytecode)
                bytecode.append(Opcode.JUMPDEST)

        def handle_for_loop(node):
            # Only handle simple for loops: for (let i = 0; i < n; i++)
            if (node.init.type != 'VariableDeclaration' and 
                node.test.type != 'BinaryExpression'):
                raise NotImplementedError("Only simple for loops are supported")

            # Generate unique labels for loop entry and exit
            loop_id = len(jump_placeholders)
            cond_label = f"for_cond_{loop_id}"
            end_label = f"for_end_{loop_id}"
            
            # Save in loop stack for break/continue
            loop_stack.append((cond_label, end_label))

            # Initialize loop variable
            handle_statement(node.init)

            # Mark the condition position with JUMPDEST
            label_positions[cond_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)

            # Condition check
            compile_expression(node.test)
            
            # Jump if condition fails
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode) - 1, end_label))
            bytecode.append(Opcode.JUMPI)
            
            # Loop body
            handle_statement(node.body)
            
            # Handle the update expression
            if node.update:
                if node.update.type == 'UpdateExpression':
                    # Handle i++ or i--
                    if node.update.argument.type == 'Identifier':
                        slot = get_storage_slot(node.update.argument.name)
                        bytecode.extend([
                            Opcode.PUSH1, slot,
                            Opcode.SLOAD,
                            Opcode.PUSH1, 1,
                            Opcode.ADD if node.update.operator == '++' else Opcode.SUB,
                            Opcode.PUSH1, slot,
                            Opcode.SSTORE
                        ])
                    else:
                        raise NotImplementedError("Only simple increments supported in for loop updates")
                else:
                    handle_expression_statement({'type': 'ExpressionStatement', 'expression': node.update})
            
            # Jump back to condition
            bytecode.extend([Opcode.PUSH1, label_positions[cond_label], Opcode.JUMP])
            
            # Mark end position
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Remove from loop stack
            loop_stack.pop()

        def handle_while_loop(node):
            loop_id = len(jump_placeholders)
            start_label = f"while_start_{loop_id}"
            end_label = f"while_end_{loop_id}"
            
            # Add to loop stack for break/continue
            loop_stack.append((start_label, end_label))
            
            # Start label
            label_positions[start_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Condition check
            compile_expression(node.test)
            
            # Jump if condition fails
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMPI)
            
            # Loop body
            handle_statement(node.body)
            
            # Jump back to start
            bytecode.extend([Opcode.PUSH1, label_positions[start_label], Opcode.JUMP])
            
            # End label
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Remove from loop stack
            loop_stack.pop()

        def handle_break_statement():
            if not loop_stack:
                raise SyntaxError("break outside loop")
            _, end_label = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)

        def handle_continue_statement():
            if not loop_stack:
                raise SyntaxError("continue outside loop")
            start_label, _ = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, label_positions[start_label], Opcode.JUMP])

        def handle_variable_declaration(node):
            for decl in node.declarations:
                if decl.init:
                    compile_expression(decl.init)
                    slot = get_storage_slot(decl.id.name)
                    bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])

        def handle_assignment(node):
            compile_expression(node.right)
            if node.left.type == 'Identifier':
                slot = get_storage_slot(node.left.name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])
            else:
                raise NotImplementedError("Only simple assignments supported")

        def handle_expression_statement(node):
            if node.expression.type == 'UpdateExpression':
                # Handle i++ or i--
                if node.expression.argument.type != 'Identifier':
                    raise NotImplementedError("Only simple increments supported")
                
                slot = get_storage_slot(node.expression.argument.name)
                bytecode.extend([
                    Opcode.PUSH1, slot,
                    Opcode.SLOAD,
                    Opcode.PUSH1, 1,
                    Opcode.ADD if node.expression.operator == '++' else Opcode.SUB,
                    Opcode.PUSH1, slot,
                    Opcode.SSTORE
                ])
            elif node.expression.type == 'AssignmentExpression':
                handle_assignment(node.expression)
            else:
                compile_expression(node.expression)

        def handle_statement(node):
            if node.type == 'IfStatement':
                handle_if_statement(node)
            elif node.type == 'ForStatement':
                handle_for_loop(node)
            elif node.type == 'WhileStatement':
                handle_while_loop(node)
            elif node.type == 'BreakStatement':
                handle_break_statement()
            elif node.type == 'ContinueStatement':
                handle_continue_statement()
            elif node.type == 'VariableDeclaration':
                handle_variable_declaration(node)
            elif node.type == 'ExpressionStatement':
                handle_expression_statement(node)
            elif node.type == 'AssignmentExpression':
                handle_assignment(node)
            elif node.type == 'BlockStatement':
                # Handle a block of statements
                for stmt in node.body:
                    handle_statement(stmt)
            else:
                raise NotImplementedError(f"Unsupported statement type: {node.type}")

        # Parse JavaScript code
        ast = esprima.parseScript(contract_source)
        
        # Compile each statement
        for node in ast.body:
            handle_statement(node)

        # Resolve jump placeholders
        for pos, label in jump_placeholders:
            if label in label_positions:
                bytecode[pos] = label_positions[label]
            else:
                raise Exception(f"Undefined label: {label}")

        bytecode.append(Opcode.STOP)
        return bytes(bytecode), storage_map
