import os
import time
import sys
import subprocess
from datetime import datetime

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ADBHandler:
    def __init__(self):
        self.serial = None
        self.model = None
        
        # Setup ADB path if local adb exists
        self.adb_exe = "adb" # Default to PATH
        
        # Check bundled path (PyInstaller) or local path
        local_adb = resource_path(os.path.join('platform-tools', 'adb.exe'))
        
        if os.path.exists(local_adb):
            self.adb_exe = local_adb
        else:
             # Fallback to current dir if not found in resource path (Dev mode sometimes)
             local_adb_dev = os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')
             if os.path.exists(local_adb_dev):
                 self.adb_exe = local_adb_dev
        
    def check_connection(self):
        """Kiểm tra thiết bị kết nối qua ADB sử dụng subprocess"""
        try:
            # Run adb devices -l
            cmd = [self.adb_exe, "devices", "-l"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                 return {"connected": False, "error": "ADB Error"}
                 
            output = result.stdout.strip().split('\n')
            # First line is "List of devices attached"
            # Subsequent lines: "SERIAL device product:X model:Y device:Z transport_id:N"
            
            found_device = None
            for line in output[1:]:
                if line.strip() and "device" in line and "offline" not in line:
                    parts = line.split()
                    serial = parts[0]
                    model = "Unknown"
                    for part in parts:
                        if part.startswith("model:"):
                            model = part.split(":")[1]
                    
                    found_device = {"serial": serial, "model": model}
                    break # Take first device
            
            if found_device:
                self.serial = found_device['serial']
                self.model = found_device['model']
                
                is_xiaomi = "Xiaomi" in self.model or "2210132C" in self.model
                
                return {
                    "connected": True,
                    "device": self.model,
                    "type": "xiaomi" if is_xiaomi else "android",
                    "color_theme": "leica-red" if is_xiaomi else "slate"
                }
            
            self.serial = None
            self.model = None
            return {"connected": False, "device": None}
            
        except Exception as e:
            self.serial = None
            self.model = None
            print(f"ADB Connection Error: {e}")
            return {"connected": False, "error": str(e)}

    def capture_preview(self):
        """Capture a low-res preview for ROI selection"""
        # Always check connection first
        status = self.check_connection()
        if not status.get("connected"):
            return None
        
        try:
            remote_path = "/sdcard/Download/preview.png"
            
            # 1. Screencap
            cmd = [self.adb_exe, "-s", self.serial, "shell", f"screencap -p {remote_path}"]
            subprocess.run(cmd, timeout=5, check=True, capture_output=True)
            
            # 2. Pull
            local_path = os.path.join(os.getcwd(), "preview_temp.png")
            if os.path.exists(local_path):
                os.remove(local_path)
            
            cmd_pull = [self.adb_exe, "-s", self.serial, "pull", remote_path, local_path]
            subprocess.run(cmd_pull, timeout=10, check=True, capture_output=True)
            
            if os.path.exists(local_path):
                return local_path
            else:
                return None
                
        except Exception as e:
            print(f"Preview error: {e}")
            return None

    def get_config(self, config_name):
        """Get device configuration"""
        if not self.serial:
            self.check_connection()
            
        if config_name == "imagesize":
            try:
                cmd = [self.adb_exe, "-s", self.serial, "shell", "wm size"]
                result = subprocess.run(cmd, timeout=5, capture_output=True, text=True)
                output = result.stdout
                if output and "Physical size:" in output:
                    return f"Screen: {output.split('Physical size:')[1].strip()} (Camera: App Setting)"
            except:
                pass
            return "Native (Check Camera App)"
            
        return "N/A"

    def set_config(self, config_name, value):
        return False

    def swipe(self, x1, y1, x2, y2, duration=300):
        """Simulate a swipe gesture"""
        status = self.check_connection()
        if not status.get("connected"):
            return False
            
        try:
            cmd = [self.adb_exe, "-s", self.serial, "shell", f"input swipe {x1} {y1} {x2} {y2} {duration}"]
            subprocess.run(cmd, timeout=5, check=True, capture_output=True)
            return True
        except Exception as e:
            print(f"Swipe error: {e}")
            return False

    def capture_and_pull(self, output_folder):
        """Gửi lệnh chụp và kéo ảnh về (Smart Wait for New File)"""
        status = self.check_connection()
        if not status.get("connected"):
            print("Device disconnected, cannot capture.")
            return None

        # 1. Get current latest file (to compare later)
        camera_path = "/sdcard/DCIM/Camera/"
        initial_latest_file = None
        try:
            cmd_ls = [self.adb_exe, "-s", self.serial, "shell", f"ls -t {camera_path} | head -n 1"]
            result_ls = subprocess.run(cmd_ls, timeout=5, capture_output=True, text=True)
            if result_ls.returncode == 0 and result_ls.stdout.strip():
                initial_latest_file = result_ls.stdout.strip()
        except Exception:
            pass 
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scan_{timestamp}.jpg"
        local_path = os.path.join(output_folder, filename)
        
        try:
            # 2. Trigger capture
            print(f"Capturing on {self.model}...")
            cmd_trigger = [self.adb_exe, "-s", self.serial, "shell", "input keyevent 27"]
            subprocess.run(cmd_trigger, timeout=5, check=True, capture_output=True)
            
            # 3. Wait for NEW file to appear
            start_time = time.time()
            new_photo_remote_path = None
            
            while (time.time() - start_time) < 15: # Increased to 15s for safety
                time.sleep(1)
                
                try:
                    cmd_check = [self.adb_exe, "-s", self.serial, "shell", f"ls -t {camera_path} | head -n 1"]
                    res = subprocess.run(cmd_check, timeout=3, capture_output=True, text=True)
                    if res.returncode == 0 and res.stdout.strip():
                        current_latest = res.stdout.strip()
                        if current_latest != initial_latest_file:
                            new_photo_remote_path = f"{camera_path}{current_latest}"
                            # Wait for file write
                            time.sleep(1.5) 
                            break
                except Exception as e:
                    print(f"Polling error: {e}")
            
            if not new_photo_remote_path:
                print("Timeout: No new photo found after capture trigger.")
                return None
                
            # 4. Pull file
            print(f"Pulling {new_photo_remote_path}...")
            cmd_pull = [self.adb_exe, "-s", self.serial, "pull", new_photo_remote_path, local_path]
            subprocess.run(cmd_pull, timeout=20, check=True, capture_output=True)
            
            if os.path.exists(local_path):
                return local_path
            else:
                return None
            
        except Exception as e:
            print(f"Error capturing with adb: {e}")
            return None
