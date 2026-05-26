# fix_uuid.py
import sys
import uuid

# Mock the uuid_utils module
class MockCompat:
    @staticmethod
    def uuid7():
        return str(uuid.uuid4())

class MockUUIDUtils:
    compat = MockCompat()

sys.modules['uuid_utils'] = MockUUIDUtils()
sys.modules['uuid_utils.compat'] = MockCompat

print("✓ UUID patch applied")