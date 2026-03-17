"""
md4.py — Pure Python implementation of the MD4 hashing algorithm (RFC 1320).

Used purely as a fallback for the `ldap3` library's NTLM authentication on modern
Python versions where OpenSSL 3+ has completely disabled the insecure MD4 algorithm.
"""

import struct

def left_rotate(n, b):
    return ((n << b) | (n >> (32 - b))) & 0xffffffff

def F(x, y, z): return (x & y) | (~x & z)
def G(x, y, z): return (x & y) | (x & z) | (y & z)
def H(x, y, z): return x ^ y ^ z

class MD4:
    def __init__(self, data=b""):
        self.A = 0x67452301
        self.B = 0xefcdab89
        self.C = 0x98badcfe
        self.D = 0x10325476
        
        # 64-byte chunks
        self._unprocessed = b""
        self._message_byte_length = 0
        
        if data:
            self.update(data)

    def update(self, data: bytes) -> None:
        self._message_byte_length += len(data)
        self._unprocessed += data
        while len(self._unprocessed) >= 64:
            self._process_chunk(self._unprocessed[:64])
            self._unprocessed = self._unprocessed[64:]

    def _process_chunk(self, chunk: bytes) -> None:
        X = list(struct.unpack("<16I", chunk))
        A, B, C, D = self.A, self.B, self.C, self.D

        # Round 1
        for i in [0, 4, 8, 12]:
            A = left_rotate((A + F(B, C, D) + X[i]) & 0xffffffff, 3)
            D = left_rotate((D + F(A, B, C) + X[i+1]) & 0xffffffff, 7)
            C = left_rotate((C + F(D, A, B) + X[i+2]) & 0xffffffff, 11)
            B = left_rotate((B + F(C, D, A) + X[i+3]) & 0xffffffff, 19)

        # Round 2
        for i in [0, 1, 2, 3]:
            A = left_rotate((A + G(B, C, D) + X[i] + 0x5a827999) & 0xffffffff, 3)
            D = left_rotate((D + G(A, B, C) + X[i+4] + 0x5a827999) & 0xffffffff, 5)
            C = left_rotate((C + G(D, A, B) + X[i+8] + 0x5a827999) & 0xffffffff, 9)
            B = left_rotate((B + G(C, D, A) + X[i+12] + 0x5a827999) & 0xffffffff, 13)

        # Round 3
        for i in [0, 2, 1, 3]:
            A = left_rotate((A + H(B, C, D) + X[i] + 0x6ed9eba1) & 0xffffffff, 3)
            D = left_rotate((D + H(A, B, C) + X[i+8] + 0x6ed9eba1) & 0xffffffff, 9)
            C = left_rotate((C + H(D, A, B) + X[i+4] + 0x6ed9eba1) & 0xffffffff, 11)
            B = left_rotate((B + H(C, D, A) + X[i+12] + 0x6ed9eba1) & 0xffffffff, 15)

        self.A = (self.A + A) & 0xffffffff
        self.B = (self.B + B) & 0xffffffff
        self.C = (self.C + C) & 0xffffffff
        self.D = (self.D + D) & 0xffffffff

    def digest(self) -> bytes:
        message = self._unprocessed
        msg_len_bits = self._message_byte_length * 8
        
        message += b"\x80"
        while len(message) % 64 != 56:
            message += b"\x00"
            
        message += struct.pack("<Q", msg_len_bits)
        
        A, B, C, D = self.A, self.B, self.C, self.D
        for i in range(0, len(message), 64):
            self._process_chunk(message[i:i+64])
            
        out = struct.pack("<4I", self.A, self.B, self.C, self.D)
        
        # Restore state so digest() doesn't permanently mutate if called repeatedly
        self.A, self.B, self.C, self.D = A, B, C, D
        
        return out
