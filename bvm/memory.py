class Memory:
    def __init__(self):
        self.memory = bytearray()
        
    def extend(self, offset, size):
        if offset + size > len(self.memory):
            extension = bytearray(offset + size - len(self.memory))
            self.memory.extend(extension)
    
    def store(self, offset, value, size=32):
        """Store a value in memory"""
        self.extend(offset, size)
        self.memory[offset:offset+size] = value.to_bytes(size, 'big')
    
    def load(self, offset, size=32):
        """Load a value from memory"""
        self.extend(offset, size)
        return int.from_bytes(self.memory[offset:offset+size], 'big')
    
    def get_memory_region(self, offset, size):
        """Get a memory region as bytes"""
        self.extend(offset, size)
        return bytes(self.memory[offset:offset+size])
