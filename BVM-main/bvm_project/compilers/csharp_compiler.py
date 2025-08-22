import hashlib
from bvm.opcodes import Opcode

class CSharpCompiler:
    @staticmethod
    def compile(source: str) -> (bytes, dict):
        """Compile C# source code to bytecode"""
        lines = [line.strip() for line in source.split('\n') if line.strip()]
        
        bytecode = bytearray()
        storage_map = {}
        jump_placeholders = []
        label_positions = {}
        loop_stack = []
        current_class = None
        in_method = False

        def get_storage_slot(var_name: str) -> int:
            """Get storage slot only for valid variable names"""
            # Clean the variable name
            var_name = var_name.strip()
            if not var_name.isidentifier() or var_name in ['else', 'if']:
                raise ValueError(f"Invalid variable name: {var_name}")
            
            if var_name not in storage_map:
                hash_bytes = hashlib.sha256(var_name.encode()).digest()
                slot = int.from_bytes(hash_bytes[:2], 'big') % 256
                storage_map[var_name] = slot
                print(f"Slot {slot} assigned to '{var_name}'")
            return storage_map[var_name]
        def handle_expression(expr: str):
            """Handle expressions with proper parentheses and operator handling"""
            expr = expr.strip()
            
            # Handle parentheses by recursively processing the inner expression
            if expr.startswith('(') and expr.endswith(')'):
                handle_expression(expr[1:-1].strip())
                return
            
            # Handle comparison operators with proper precedence
            for op in ['>', '<', '==', '!=', '>=', '<=']:
                if op in expr:
                    parts = expr.split(op, 1)
                    if len(parts) == 2:
                        left, right = parts
                        handle_expression(left.strip())
                        handle_expression(right.strip())
                        
                        if op == '>':
                            bytecode.append(Opcode.GT)
                        elif op == '<':
                            bytecode.append(Opcode.LT)
                        elif op == '==':
                            bytecode.append(Opcode.EQ)
                        elif op == '!=':
                            bytecode.append(Opcode.NEQ)
                        elif op == '>=':
                            bytecode.append(Opcode.GTE)
                        elif op == '<=':
                            bytecode.append(Opcode.LTE)
                        return
            
            # Handle arithmetic operators
            for op in ['+', '-', '*', '/']:
                if op in expr:
                    parts = expr.split(op, 1)
                    if len(parts) == 2:
                        left, right = parts
                        handle_expression(left.strip())
                        handle_expression(right.strip())
                        
                        if op == '+':
                            bytecode.append(Opcode.ADD)
                        elif op == '-':
                            bytecode.append(Opcode.SUB)
                        elif op == '*':
                            bytecode.append(Opcode.MUL)
                        elif op == '/':
                            bytecode.append(Opcode.DIV)
                        return
            
            # Handle variables and literals
            if expr.isdigit():
                bytecode.extend([Opcode.PUSH1, int(expr)])
            elif expr.isidentifier():
                slot = get_storage_slot(expr)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SLOAD])
            else:
                raise ValueError(f"Invalid expression: {expr}")



        def handle_assignment(target: str, value: str):
            """Handle variable assignment"""
            handle_expression(value)
            slot = get_storage_slot(target)
            bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])

        def handle_if_statement(condition: str, line_index: int, lines: list):
            """Handle if statements with proper condition evaluation"""
            else_label = f"else_{len(jump_placeholders)}"
            end_label = f"end_{len(jump_placeholders)+1}"
            
            # Evaluate the condition
            handle_expression(condition)
            
            # Add ISZERO to invert the condition (true becomes 0, false becomes 1)
            bytecode.append(Opcode.ISZERO)
            
            # Jump to else if condition is false (after ISZERO, false is 1)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder for jump destination
            jump_placeholders.append((len(bytecode)-1, else_label))
            bytecode.append(Opcode.JUMPI)
            
            # Find the if block
            i = line_index + 1
            if_block = []
            block_count = 1
            
            # Skip opening brace
            while i < len(lines) and lines[i].strip() != '{':
                i += 1
            i += 1  # Move past the opening brace
            
            # Collect statements until closing brace
            while i < len(lines) and block_count > 0:
                line = lines[i].strip()
                if line == '{':
                    block_count += 1
                elif line == '}':
                    block_count -= 1
                
                if block_count > 0:
                    if_block.append(lines[i])
                i += 1
            
            # Check for else block
            else_block = []
            if i < len(lines) and lines[i].strip().startswith('else'):
                i += 1
                if i < len(lines) and lines[i].strip() == '{':
                    i += 1
                    block_count = 1
                    
                    while i < len(lines) and block_count > 0:
                        line = lines[i].strip()
                        if line == '{':
                            block_count += 1
                        elif line == '}':
                            block_count -= 1
                        
                        if block_count > 0:
                            else_block.append(lines[i])
                        i += 1
            
            # Compile if block - executes when condition is true (ISZERO makes it 0, so no jump)
            for stmt in if_block:
                if stmt.strip():  # Skip empty lines
                    handle_statement(stmt)
            
            # Jump to end to skip else block
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)
            
            # Else block - executes when condition is false (ISZERO makes it 1, so it jumps here)
            label_positions[else_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            if else_block:
                for stmt in else_block:
                    if stmt.strip():  # Skip empty lines
                        handle_statement(stmt)
            
            # End label - both if and else blocks converge here
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)

        def handle_while(condition: str, body: list):
            """Handle while loops"""
            start_label = f"while_{len(jump_placeholders)}"
            end_label = f"endwhile_{len(jump_placeholders)+1}"
            
            loop_stack.append((start_label, end_label))
            
            label_positions[start_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            handle_expression(condition)
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMPI)
            
            for stmt in body:
                handle_statement(stmt)
            
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, start_label))
            bytecode.append(Opcode.JUMP)
            
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            loop_stack.pop()

        def handle_for(init: str, condition: str, increment: str, body: list):
            """Handle for loops"""
            start_label = f"for_{len(jump_placeholders)}"
            end_label = f"endfor_{len(jump_placeholders)+1}"
            
            loop_stack.append((start_label, end_label))
            
            if init:
                handle_statement(init)
            
            label_positions[start_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            if condition:
                handle_expression(condition)
            else:
                bytecode.extend([Opcode.PUSH1, 1])
            
            bytecode.append(Opcode.ISZERO)
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMPI)
            
            for stmt in body:
                handle_statement(stmt)
            
            if increment:
                handle_statement(increment)
            
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, start_label))
            bytecode.append(Opcode.JUMP)
            
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            loop_stack.pop()

        def handle_break():
            """Handle break statements"""
            if not loop_stack:
                raise SyntaxError("break outside loop")
            _, end_label = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)

        def handle_method_decl(name: str, body: list):
            """Handle method declarations"""
            nonlocal in_method
            if name == "Main":
                in_method = True
                for stmt in body:
                    handle_statement(stmt)
                in_method = False

        def handle_statement(stmt: str):
            """Handle statements with proper variable declaration checking"""
            stmt = stmt.strip()
            if not stmt or stmt.startswith("//"):
                return
                
            # Skip using directives and class declarations
            if stmt.startswith(("using ", "class ", "static ", "public ", "private ")):
                return
                
            # Remove semicolon if present
            stmt = stmt.rstrip(';')
            
            # Handle blocks
            if stmt in ["{", "}"]:
                return
                
            # Handle if statements
            if stmt.startswith("if ("):
                # This should be handled in the main compilation loop
                return
                
            # Handle variable assignments
            if '=' in stmt:
                target, value = stmt.split('=', 1)
                target = target.strip()
                value = value.strip()
                
                # Check if variable is declared
                if any(target.startswith(t) for t in ['int ', 'float ', 'double ', 'bool ']):
                    # Variable declaration with assignment
                    var_name = target.split()[-1].strip()
                    handle_assignment(var_name, value)
                else:
                    # Regular assignment
                    handle_assignment(target, value)
                return
                
            # Handle expressions
            try:
                handle_expression(stmt)
            except ValueError as e:
                print(f"Warning: {e}")

        # Main compilation loop
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.startswith("if ("):
                cond_end = line.find(')')
                if cond_end > 0:
                    condition = line[3:cond_end+1].strip()
                    handle_if_statement(condition, i, lines)
                    # Skip to the end of the if-else block
                    block_count = 0
                    while i < len(lines):
                        if '{' in lines[i]:
                            block_count += 1
                        if '}' in lines[i]:
                            block_count -= 1
                            if block_count == 0 and not lines[i+1:i+2] or not lines[i+1].strip().startswith('else'):
                                break
                        i += 1
                i += 1
            else:
                handle_statement(line)
                i += 1

        # Resolve jumps
        for pos, label in jump_placeholders:
            if label in label_positions:
                bytecode[pos] = label_positions[label]
            else:
                raise Exception(f"Undefined label: {label}")

        bytecode.append(Opcode.STOP)
        return bytes(bytecode), storage_map
