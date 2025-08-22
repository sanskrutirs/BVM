from bvm.opcodes import Opcode
import ast
import hashlib
class Compiler:
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
            if isinstance(expr, ast.Num):
                bytecode.extend([Opcode.PUSH1, expr.n])
            elif isinstance(expr, ast.Name):
                slot = get_storage_slot(expr.id)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SLOAD])
            elif isinstance(expr, ast.BinOp):
                compile_expression(expr.left)
                compile_expression(expr.right)
                if isinstance(expr.op, ast.Add): bytecode.append(Opcode.ADD)
                elif isinstance(expr.op, ast.Sub): bytecode.append(Opcode.SUB)
                elif isinstance(expr.op, ast.Mult): bytecode.append(Opcode.MUL)
                elif isinstance(expr.op, ast.Div): bytecode.append(Opcode.DIV)
            elif isinstance(expr, ast.Compare):
                compile_expression(expr.left)
                compile_expression(expr.comparators[0])
                if isinstance(expr.ops[0], ast.Gt): bytecode.append(Opcode.GT)
                elif isinstance(expr.ops[0], ast.Lt): bytecode.append(Opcode.LT)
                elif isinstance(expr.ops[0], ast.Eq): bytecode.append(Opcode.EQ)
                elif isinstance(expr.ops[0], ast.GtE): bytecode.append(Opcode.GTE)
                elif isinstance(expr.ops[0], ast.LtE): bytecode.append(Opcode.LTE)

        def handle_if(node):
            # Generate unique labels
            else_label = f"else_{len(jump_placeholders)}"
            end_label = f"end_{len(jump_placeholders)+1}"
            
            # Compile condition
            compile_expression(node.test)
            
            # Add conditional jump to else block
            bytecode.append(Opcode.ISZERO)  # Jump if condition is false
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, else_label))
            bytecode.append(Opcode.JUMPI)
            
            # Compile if body
            for stmt in node.body:
                handle_statement(stmt)
            
            # Add jump to skip else block
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)
            
            # Mark else position
            label_positions[else_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Compile else body
            for stmt in node.orelse:
                handle_statement(stmt)
                
            # Mark end position
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)

        def handle_for(node):
            # Only handle simple: for i in range(n)
            if not (isinstance(node.iter, ast.Call) and 
                    isinstance(node.iter.func, ast.Name) and 
                    node.iter.func.id == 'range' and
                    len(node.iter.args) == 1):
                raise NotImplementedError("Only for i in range(n) supported")

            # Get storage slot for loop variable
            var_name = node.target.id
            slot = get_storage_slot(var_name)
            stop = node.iter.args[0]

            # Initialize i = 0
            bytecode.extend([
                Opcode.PUSH1, 0,
                Opcode.PUSH1, slot,
                Opcode.SSTORE
            ])

            # Loop start (JUMPDEST)
            loop_start = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)

            # Condition: i < n
            bytecode.extend([
                Opcode.PUSH1, slot,
                Opcode.SLOAD,        # Load i
            ])
            compile_expression(stop) # Load n
            bytecode.extend([
                Opcode.LT,           # i < n
                Opcode.ISZERO,       # Invert for JUMPI
                Opcode.PUSH1, 0,     # Placeholder for end position
                Opcode.JUMPI         # Jump to end if i >= n
            ])
            end_jump_pos = len(bytecode) - 2

            # Loop body
            for stmt in node.body:
                handle_statement(stmt)

            # Increment i (i += 1)
            bytecode.extend([
                Opcode.PUSH1, slot,
                Opcode.SLOAD,
                Opcode.PUSH1, 1,
                Opcode.ADD,
                Opcode.PUSH1, slot,
                Opcode.SSTORE
            ])

            # Jump back to start
            bytecode.extend([
                Opcode.PUSH1, loop_start,
                Opcode.JUMP
            ])

            # Set end position
            loop_end = len(bytecode)
            bytecode[end_jump_pos] = loop_end
            bytecode.append(Opcode.JUMPDEST)

        def handle_while(node):
            loop_id = len(loop_stack)
            start_label = f"while_start_{loop_id}"
            end_label = f"while_end_{loop_id}"
            loop_stack.append((start_label, end_label))
            
            # Start label
            label_positions[start_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            
            # Condition check
            compile_expression(node.test)
            
            # Jump if condition fails
            bytecode.extend([Opcode.ISZERO, Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMPI)
            
            # Loop body
            for stmt in node.body:
                handle_statement(stmt)
            
            # Jump back to start
            bytecode.extend([Opcode.PUSH1, label_positions[start_label], Opcode.JUMP])
            
            # End label
            label_positions[end_label] = len(bytecode)
            bytecode.append(Opcode.JUMPDEST)
            loop_stack.pop()

        def handle_break():
            if not loop_stack:
                raise SyntaxError("break outside loop")
            _, end_label = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, 0])  # Placeholder
            jump_placeholders.append((len(bytecode)-1, end_label))
            bytecode.append(Opcode.JUMP)

        def handle_continue():
            if not loop_stack:
                raise SyntaxError("continue outside loop")
            start_label, _ = loop_stack[-1]
            bytecode.extend([Opcode.PUSH1, label_positions[start_label], Opcode.JUMP])


        def handle_statement(node):
            if isinstance(node, ast.If):
                handle_if(node)
            elif isinstance(node, ast.For):
                handle_for(node)
            elif isinstance(node, ast.While):
                handle_while(node)
            elif isinstance(node, ast.Break):
                handle_break()
            elif isinstance(node, ast.Continue):
                handle_continue()
            elif isinstance(node, ast.Assign):
                var_name = node.targets[0].id
                compile_expression(node.value)
                slot = get_storage_slot(var_name)
                bytecode.extend([Opcode.PUSH1, slot, Opcode.SSTORE])

        # Parse and compile
        tree = ast.parse(contract_source)
        for node in tree.body:
            handle_statement(node)

        # Resolve jump placeholders
        for pos, label in jump_placeholders:
            if label in label_positions:
                bytecode[pos] = label_positions[label]
            else:
                raise Exception(f"Undefined label: {label}")

        bytecode.append(Opcode.STOP)
        return bytes(bytecode), storage_map
