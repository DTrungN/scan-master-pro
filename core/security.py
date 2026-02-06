import subprocess
import hashlib
import uuid
import os

class Security:
    def __init__(self):
        self.hwid = self._get_hwid()
        self.license_file = "license.key"
        self.is_valid = False
        
    def _get_hwid(self):
        """Get Hardware ID based on Motherboard Serial + CPU ID"""
        try:
            # Get Board Serial
            board_serial = subprocess.check_output(
                'wmic baseboard get serialnumber', shell=True
            ).decode().split('\n')[1].strip()
            
            # Get CPU ID
            cpu_id = subprocess.check_output(
                'wmic cpu get processorid', shell=True
            ).decode().split('\n')[1].strip()
            
            raw_id = f"{board_serial}{cpu_id}"
            return hashlib.sha256(raw_id.encode()).hexdigest().upper()
        except Exception:
            # Fallback for dev/error cases
            return "UNKNOWN_HWID_FALLBACK"

    def generate_key(self, hwid_input):
        """Generate License Key from HWID (Admin Tool Logic)"""
        salt = "SCAN_MASTER_PRO_SECRET_SALT_2026"
        data = f"{hwid_input}{salt}"
        return hashlib.sha256(data.encode()).hexdigest().upper()[:32] # 32 chars key

    def check_license(self):
        """Verify if current machine has valid license"""
        if not os.path.exists(self.license_file):
            self.is_valid = False
            return False
            
        try:
            with open(self.license_file, 'r') as f:
                stored_key = f.read().strip()
                
            expected_key = self.generate_key(self.hwid)
            
            if stored_key == expected_key:
                self.is_valid = True
                return True
            else:
                self.is_valid = False
                return False
        except:
            self.is_valid = False
            return False

# Global Instance
security_manager = Security()
