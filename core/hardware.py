import serial
import time
import os
import cv2
import numpy as np
import subprocess
import shutil
from .adb_handler import ADBHandler

class NikonHandler:
    def __init__(self):
        self.connected = False
        self.use_mock = True
        self.check_gphoto2_availability()
        
    def check_gphoto2_availability(self):
        """Check if gphoto2 is installed and available in PATH"""
        if shutil.which("gphoto2"):
            self.use_mock = False
            print("GPhoto2 found. Using real camera driver.")
        else:
            self.use_mock = True
            print("GPhoto2 NOT found. Using Mock mode.")

    def run_gphoto2_command(self, args):
        """Run a gphoto2 command and return output"""
        if self.use_mock:
            return None
            
        try:
            cmd = ["gphoto2"] + args
            # Add timeout to prevent hanging
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            print(f"GPhoto2 Command Timeout: {' '.join(args)}")
            return None
        except subprocess.CalledProcessError as e:
            print(f"GPhoto2 Error: {e.stderr}")
            return None
        except Exception as e:
            print(f"GPhoto2 Execution Error: {e}")
            return None

    def check_connection(self):
        if self.use_mock:
            return {"connected": True, "device": "Nikon Z30 (Mock)", "color_theme": "nikon-blue"}
        
        output = self.run_gphoto2_command(["--auto-detect"])
        if output and "Nikon" in output: # Basic check, might need refinement based on output
            self.connected = True
            return {"connected": True, "device": "Nikon Z30", "color_theme": "nikon-blue"}
        else:
            self.connected = False
            return {"connected": False, "device": "Disconnected", "color_theme": "nikon-blue"}

    def set_config(self, config_name, value):
        if self.use_mock:
            print(f"Mock Set {config_name} to {value}")
            return True
            
        # Example: gphoto2 --set-config iso=100
        output = self.run_gphoto2_command(["--set-config", f"{config_name}={value}"])
        return output is not None

    def get_config(self, config_name):
        if self.use_mock:
            # Return dummy values for mock
            defaults = {
                "iso": "100",
                "aperture": "5.6",
                "shutterspeed": "1/100",
                "imagesize": "Large"
            }
            return defaults.get(config_name, "N/A")
            
        # Example output of --get-config iso:
        # Label: ISO Speed
        # Type: RADIO
        # Current: 100
        # Choice: 0 100
        # ...
        output = self.run_gphoto2_command(["--get-config", config_name])
        if output:
            current = None
            choices = []
            for line in output.split('\n'):
                if line.startswith("Current:"):
                    current = line.split("Current:")[1].strip()
                if line.startswith("Choice:"):
                    # Choice: 0 Large -> "Large"
                    # Choice: 0 100 -> "100"
                    parts = line.split("Choice:")[1].strip().split(" ")
                    if len(parts) > 1:
                        choices.append(" ".join(parts[1:]))
                    else:
                        choices.append(parts[0])

            if config_name == 'imagesize' and choices:
                # Return current and list of choices to imply we know the max
                return f"{current} (Options: {', '.join(choices)})"
                
            return current
        return None

    def capture_preview(self, save_path):
        if self.use_mock:
            # Generate dummy preview
            img = np.zeros((400, 600, 3), dtype=np.uint8)
            img[:] = (50, 50, 50)
            cv2.putText(img, "Nikon Z30 Preview", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.imwrite(save_path, img)
            return save_path

        try:
            # gphoto2 --capture-preview --force-overwrite --filename ...
            cmd = ["gphoto2", "--capture-preview", "--force-overwrite", "--filename", os.path.basename(save_path)]
            subprocess.run(cmd, check=True, cwd=os.path.dirname(save_path), timeout=10)
            return save_path
        except subprocess.TimeoutExpired:
            print("Preview Timeout")
            return None
        except Exception as e:
            print(f"Preview failed: {e}")
            return None

    def drive_focus(self, step_size):
        """
        Drive lens focus. 
        step_size: 
            - Integer: +ve for Near, -ve for Far. Magnitude = speed/amount (1=Small, 2=Medium, 3=Large).
            - String: "Near 1", "Far 2", etc.
        """
        if self.use_mock:
            print(f"Mock Focus Drive: {step_size}")
            return True
            
        try:
            value = None
            if isinstance(step_size, str):
                # Normalize string: "near 1" -> "Near 1"
                parts = step_size.strip().split()
                if len(parts) == 2:
                    direction = parts[0].capitalize() # Near/Far
                    level = parts[1]
                    if direction in ["Near", "Far"] and level in ["1", "2", "3"]:
                         value = f"{direction} {level}"
            
            if not value and isinstance(step_size, int):
                # Heuristic mapping for integers
                # Nikon Z series typically supports: Near 1, Near 2, Near 3, Far 1, Far 2, Far 3
                # 1=Small, 2=Medium, 3=Large
                
                mag = abs(step_size)
                level = 1
                if mag >= 80: level = 3
                elif mag >= 30: level = 2
                
                direction = "Near" if step_size > 0 else "Far"
                value = f"{direction} {level}"
            
            if not value:
                 value = str(step_size)

            print(f"Driving Focus: {value}")
            # gphoto2 --set-config manualfocusdrive="Near 1"
            self.run_gphoto2_command(["--set-config", f"manualfocusdrive={value}"])
            return True
        except Exception as e:
            print(f"Focus drive failed: {e}")
            return False

    def capture_and_pull(self, upload_folder):
        if self.use_mock:
            print("Nikon Z30 (Mock): Capturing...")
            time.sleep(1)
            timestamp = int(time.time())
            filename = f"scan_{timestamp}.jpg"
            filepath = os.path.join(upload_folder, filename)
            
            # Create dummy high-quality image
            img = np.zeros((1000,1000,3), dtype=np.uint8)
            img[:] = (100, 100, 140) # Nikon blue tint
            cv2.putText(img, "Nikon Z30 Capture", (100, 500), cv2.FONT_HERSHEY_SIMPLEX, 2, (255,255,255), 3)
            
            # Add mock metadata text
            cv2.putText(img, "ISO: 100 f/5.6 1/100", (100, 600), cv2.FONT_HERSHEY_SIMPLEX, 1, (200,200,200), 2)
            
            cv2.imwrite(filepath, img)
            return filepath
        
        # Real Capture
        print("Nikon Z30: Capturing...")
        timestamp = int(time.time())
        filename = f"scan_{timestamp}.jpg"
        filepath = os.path.join(upload_folder, filename)
        
        # gphoto2 --capture-image-and-download --filename "..."
        # Note: --filename argument behavior depends on version, often requires absolute path or pattern
        # Easier to capture to current dir then move
        
        try:
            # Capture and download to current directory
            cmd = ["gphoto2", "--capture-image-and-download", "--force-overwrite", "--filename", filename]
            subprocess.run(cmd, check=True, cwd=upload_folder, timeout=20) # Run inside upload folder to save directly there
            
            if os.path.exists(filepath):
                return filepath
            else:
                print("Error: File not found after capture")
                return None
        except subprocess.TimeoutExpired:
            print("Capture Timeout")
            return None
        except Exception as e:
            print(f"Capture failed: {e}")
            return None

class HardwareController:
    def __init__(self, upload_folder='scans'):
        self.upload_folder = upload_folder
        self.adb = ADBHandler()
        self.nikon = NikonHandler()
        self.arduino = None
        self.connect_arduino()

    def connect_arduino(self, port='COM3', baudrate=9600):
        try:
            self.arduino = serial.Serial(port, baudrate, timeout=1)
            time.sleep(2) # Wait for Arduino to reset
            print(f"Connected to Arduino on {port}")
        except Exception as e:
            # print(f"Arduino connection failed: {e}") # Suppress for dev
            self.arduino = None

    def set_light(self, index):
        """
        index: 0=OFF, 1=North, 2=East, 3=South, 4=West
        """
        if self.arduino:
            try:
                self.arduino.write(str(index).encode())
                time.sleep(0.5) # Wait for light to stabilize
            except Exception as e:
                print(f"Error setting light: {e}")
        else:
            # print(f"Mock Light: {index}")
            pass

    def get_device_handler(self, device_type):
        if device_type == 'z30':
            return self.nikon
        return self.adb

    def capture_focus_stack(self, roi_size=10, roi_offset=None, device_type='z30', steps=5, focus_step=-20):
        """
        Captures a sequence of images with focus shifts.
        steps: Number of images to capture (including the first one).
        focus_step: Amount to drive focus between shots. 
                    Negative = Far (default for stacking from Near to Far).
                    Magnitude determines step size (20=Level 1, 50=Level 2, 100=Level 3).
        """
        device = self.get_device_handler(device_type)
        captured_files = []
        
        # Ensure connected
        status = device.check_connection()
        if not status.get("connected"):
            print(f"Device {device_type} not connected for focus stack.")
            if not device.use_mock:
                return []

        timestamp = int(time.time())
        
        # 1. Initial Shot (Start point)
        print("Capturing stack frame 1...")
        path = device.capture_and_pull(self.upload_folder)
        if path: captured_files.append(path)
        
        # 2. Shift and Capture Loop
        for i in range(steps - 1):
            print(f"Shifting focus step {i+1}...")
            
            if device_type == 'z30':
                # Drive Focus Motor
                device.drive_focus(focus_step) 
                time.sleep(1.5) # Wait for motor and vibration to settle
                
            elif device_type == 'mi13' or device_type == 'adb':
                # ADB Swipe for focus
                # Configurable or hardcoded for Mi 13 Pro
                # Swipe Up (Far)
                x_pos = 2800
                y_start = 800
                y_end = 700 
                
                if hasattr(device, 'swipe'):
                    device.swipe(x_pos, y_start, x_pos, y_end, duration=200)
                    time.sleep(1.5)
            
            print(f"Capturing stack frame {i+2}...")
            path = device.capture_and_pull(self.upload_folder)
            
            if path:
                # Rename to include index
                dir_name = os.path.dirname(path)
                base = os.path.basename(path)
                name, ext = os.path.splitext(base)
                new_name = f"{name}_stack_{i+2}{ext}"
                new_path = os.path.join(dir_name, new_name)
                os.rename(path, new_path)
                captured_files.append(new_path)
            elif device.use_mock: 
                # Mock generation
                dummy_path = os.path.join(self.upload_folder, f"mock_stack_{timestamp}_{i+2}.jpg")
                img = np.zeros((500,500,3), dtype=np.uint8)
                img[:] = (128,128,128)
                cv2.circle(img, (250,250), 50 + i*20, (255,255,255), 2)
                cv2.imwrite(dummy_path, img)
                captured_files.append(dummy_path)

        return captured_files

    def capture_photometric_sequence(self, roi_size=10, roi_offset=None, device_type='mi13'):
        """
        Captures 4 images (N, E, S, W) and returns the paths.
        """
        directions = ['north', 'east', 'south', 'west']
        captured_files = {}
        
        device = self.get_device_handler(device_type)

        # Ensure connected
        status = device.check_connection()
        if not status.get("connected"):
            # If explicit device requested but not connected, maybe fallback or error?
            # For dev mock, we proceed if it's just ADB check failing
            pass

        timestamp = int(time.time())

        for i, direction in enumerate(directions):
            # 1. Turn on Light (1-4)
            print(f"Switching light to {direction}...")
            self.set_light(i + 1)

            # 2. Capture & Pull
            print(f"Capturing {direction} image...")
            image_path = device.capture_and_pull(self.upload_folder)
            
            # MOCK if capture failed (dev mode or mock handler)
            if not image_path:
                print("Mocking capture for dev...")
                # Create a dummy file if not exists
                dummy_path = os.path.join(self.upload_folder, f"mock_{timestamp}_{direction}.jpg")
                # Create a gray image
                img = np.zeros((500,500,3), dtype=np.uint8)
                img[:] = (128,128,128)
                # Add some variation based on direction to test photometric
                if direction == 'north': cv2.circle(img, (250,250), 100, (200,200,200), -1)
                if direction == 'east': cv2.circle(img, (260,250), 100, (200,200,200), -1)
                if direction == 'south': cv2.circle(img, (250,260), 100, (200,200,200), -1)
                if direction == 'west': cv2.circle(img, (240,250), 100, (200,200,200), -1)
                cv2.imwrite(dummy_path, img)
                image_path = dummy_path
            
            if not image_path:
                raise Exception(f"Failed to capture {direction} image")
                
            # Rename to include direction for easier debugging/processing
            # image_path is absolute path
            dirname, basename = os.path.split(image_path)
            # If it's not the mock file (which already has direction), rename it
            if "mock_" not in basename and f"_{direction}" not in basename:
                # Need to be careful not to double rename if handler already named it
                name_no_ext, ext = os.path.splitext(basename)
                new_basename = f"{name_no_ext}_{direction}{ext}"
                new_path = os.path.join(dirname, new_basename)
                os.rename(image_path, new_path)
                captured_files[direction] = new_path
            else:
                captured_files[direction] = image_path
            
            # 3. Turn off light (0)
            self.set_light(0)
            
            time.sleep(1) # Cooldown/Buffer

        # Turn off all lights at end
        self.set_light(0)
        
        return captured_files

    def capture_single(self, device_type='mi13'):
        device = self.get_device_handler(device_type)
        status = device.check_connection()
        
        # If device is connected, use it.
        # If not, but we are in dev/mock environment, generate mock.
        if status.get("connected"):
            path = device.capture_and_pull(self.upload_folder)
            if path:
                return path
            else:
                print("Capture failed, returning None")
                return None
        
        # Fallback to Mock only if explicit mock device or completely failed
        # But we should respect the real device if selected. 
        # For now, if check_connection fails, we return mock to allow UI testing.
        print("Device not connected, using Mock generation.")
        timestamp = int(time.time())
        dummy_path = os.path.join(self.upload_folder, f"scan_{timestamp}.jpg")
        img = np.zeros((500,500,3), dtype=np.uint8)
        img[:] = (128,128,128)
        cv2.putText(img, "Mock Capture", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        cv2.imwrite(dummy_path, img)
        return dummy_path
