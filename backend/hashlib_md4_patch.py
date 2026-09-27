"""Monkey patch hashlib to support MD4 using pycryptodomex"""
import hashlib
import sys

def enable_md4():
    """Enable MD4 support in hashlib using Cryptodome"""
    try:
        # Test if MD4 already works
        hashlib.new('md4')
        return
    except ValueError:
        pass
    
    try:
        from Cryptodome.Hash import MD4 as _MD4
        
        class MD4Hash:
            def __init__(self, data=b''):
                self._hash = _MD4.new()
                if data:
                    self._hash.update(data)
            
            def update(self, data):
                self._hash.update(data)
                
            def digest(self):
                return self._hash.digest()
                
            def hexdigest(self):
                return self._hash.hexdigest()
            
            def copy(self):
                new_hash = MD4Hash()
                new_hash._hash = self._hash.copy()
                return new_hash
            
            @property
            def digest_size(self):
                return self._hash.digest_size
            
            @property
            def block_size(self):
                return self._hash.block_size
            
            @property
            def name(self):
                return 'md4'
        
        # Monkey patch hashlib.new
        _original_hashlib_new = hashlib.new
        
        def patched_new(name, data=b'', **kwargs):
            if name.lower() == 'md4':
                return MD4Hash(data)
            return _original_hashlib_new(name, data, **kwargs)
        
        hashlib.new = patched_new
        # Also add md4 to algorithms_available
        hashlib.algorithms_available.add('md4')
        print("MD4 support enabled via Cryptodome")
        
    except ImportError as e:
        print(f"Failed to enable MD4 support: {e}")
        raise

# Enable MD4 when module is imported
enable_md4()
