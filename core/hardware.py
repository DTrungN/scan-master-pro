import serial
import time
import os
import cv2
import numpy as np
import subprocess
import shutil
import exifread
from .adb_handler import ADBHandler

class NikonHandler:
    def __init__(self):
        self.connected = False
        self.backend = 'mock' # 'digicamcontrol', 'gphoto2', 'mock'
        self.digicam_path = self._find_digicamcontrol()
        self.manual_lens = True # TTArtisan 40mm f/2.8 Macro is Manual Focus
        self.detect_backend()
        
    def _find_digicamcontrol(self):
        """Locate CameraControlCmd.exe"""
        # Common paths
        paths = [
            r"C:\Program Files (x86)\DigiCamControl\CameraControlCmd.exe",
            r"C:\Program Files\DigiCamControl\CameraControlCmd.exe",
            os.path.join(os.getcwd(), "tools", "DigiCamControl", "CameraControlCmd.exe")
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return None

    def detect_backend(self):
        """Check available backends"""
        if self.digicam_path:
            self.backend = 'digicamcontrol'
            print(f"DigiCamControl found at {self.digicam_path}")
        elif shutil.which("gphoto2"):
            self.backend = 'gphoto2'
            print("GPhoto2 found.")
        else:
            self.backend = 'mock'
            print("No camera driver found. Using Mock mode.")
        
        # Override if user forces mock via env or something? No, keep it simple.
        # But allow fallback if device not connected? 
        # No, backend detection is about software availability. 
        # check_connection handles device presence.

    def run_command(self, args):
        """Run backend specific command"""
        if self.backend == 'digicamcontrol':
            return self._run_digicam(args)
        elif self.backend == 'gphoto2':
            return self._run_gphoto2(args)
        return None

    def _run_digicam(self, args):
        try:
            # CameraControlCmd.exe /filename ... /capture
            cmd = [self.digicam_path] + args
            # subprocess list is safer
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20)
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            print(f"DigiCam Timeout: {args}")
            return None
        except Exception as e:
            print(f"DigiCam Error: {e}")
            return None

    def _run_gphoto2(self, args):
        try:
            cmd = ["gphoto2"] + args
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
            return result.stdout.strip()
        except Exception as e:
            print(f"GPhoto2 Error: {e}")
            return None

    @property
    def use_mock(self):
        return self.backend == 'mock'

    def check_connection(self):
        if self.backend == 'mock':
            return {"connected": True, "device": "Nikon Z30 (Mock)", "color_theme": "nikon-blue"}
        
        if self.backend == 'digicamcontrol':
            # CameraControlCmd.exe /cameras
            output = self.run_command(["/cameras"])
            # If output contains "No camera", or is empty/error
            if output and "No camera is connected" not in output:
                 return {"connected": True, "device": "Nikon Z30 (DCC)", "color_theme": "nikon-blue"}
        
        if self.backend == 'gphoto2':
            output = self.run_command(["--auto-detect"])
            if output and "Nikon" in output:
                return {"connected": True, "device": "Nikon Z30", "color_theme": "nikon-blue"}
            
        return {"connected": False, "device": "Disconnected", "color_theme": "nikon-blue"}

    def set_config(self, config_name, value):
        # Handle Manual Lens Limitations
        if self.manual_lens and config_name in ['aperture', 'focus']:
            print(f"Skipping {config_name} set for Manual Lens (TTArtisan 40mm)")
            return True # Pretend success to not break workflow

        if self.backend == 'mock':
            print(f"Mock Set {config_name} to {value}")
            return True
            
        if self.backend == 'digicamcontrol':
            # Map common names to DCC commands
            cmd_map = {
                'iso': '/iso',
                'aperture': '/aperture',
                'shutterspeed': '/shutter',
                'imagesize': '/imagesize' 
            }
            if config_name in cmd_map:
                self.run_command([cmd_map[config_name], str(value)])
                return True
            return False

        if self.backend == 'gphoto2':
            output = self.run_command(["--set-config", f"{config_name}={value}"])
            return output is not None
        return False

    def get_config(self, config_name):
        if self.backend == 'mock':
            defaults = {"iso": "100", "aperture": "5.6", "shutterspeed": "1/100", "imagesize": "Large"}
            return defaults.get(config_name, "N/A")
            
        if self.backend == 'digicamcontrol':
             # DCC doesn't easily return current value via CLI without /session or json
             return "N/A (DCC)"

        if self.backend == 'gphoto2':
            output = self.run_command(["--get-config", config_name])
            if output:
                current = None
                for line in output.split('\n'):
                    if line.startswith("Current:"):
                        current = line.split("Current:")[1].strip()
                        return current
        return None

    def get_focus_distance(self, image_path):
        """
        Reads Nikon Z-series absolute focus position from EXIF.
        User info: Infinity ~0, MFD ~Large Integer.
        """
        if not os.path.exists(image_path):
            return None
            
        try:
            with open(image_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                # Search for focus related tags
                focus_info = {}
                for tag in tags.keys():
                    if "Focus" in tag:
                        focus_info[tag] = str(tags[tag])
                
                # Try to find specific Nikon focus tags
                # Common candidates: MakerNote FocusDistance, MakerNote FocusPosition
                # Note: Exact tag name depends on exifread's mapping for Z series
                return focus_info
        except Exception as e:
            print(f"Error reading EXIF: {e}")
            return None

    def capture_preview(self, save_path):
        if self.backend == 'mock':
            img = np.zeros((400, 600, 3), dtype=np.uint8)
            img[:] = (50, 50, 50)
            cv2.putText(img, "Nikon Z30 Preview", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.imwrite(save_path, img)
            return save_path

        if self.backend == 'digicamcontrol':
            # DCC: Try capturing a small jpeg?
            print("Preview not supported in simple DCC CLI mode")
            return None

        if self.backend == 'gphoto2':
            try:
                cmd = ["gphoto2", "--capture-preview", "--force-overwrite", "--filename", os.path.basename(save_path)]
                subprocess.run(cmd, check=True, cwd=os.path.dirname(save_path), timeout=10)
                return save_path
            except:
                return None
        return None

    def drive_focus(self, step_size):
        """
        Drive lens focus. 
        step_size: 
            - Integer: +ve for Near, -ve for Far. 
        """
        if self.manual_lens:
            print("Manual Lens detected. Skipping drive_focus.")
            return False

        if self.backend == 'mock':
            print(f"Mock Focus Drive: {step_size}")
            return True
            
        if self.backend == 'digicamcontrol':
            # CameraControlCmd.exe /focus <step>
            try:
                # DCC uses integer steps. 
                # Need to map logic if needed, but usually just pass int.
                val = int(step_size)
                self.run_command(["/focus", str(val)])
                return True
            except:
                return False

        if self.backend == 'gphoto2':
            try:
                # Use previous logic for gphoto2
                value = None
                if isinstance(step_size, int):
                    mag = abs(step_size)
                    level = 1
                    if mag >= 80: level = 3
                    elif mag >= 30: level = 2
                    direction = "Near" if step_size > 0 else "Far"
                    value = f"{direction} {level}"
                else:
                    value = str(step_size)

                self.run_command(["--set-config", f"manualfocusdrive={value}"])
                return True
            except:
                return False
        return False

    def capture_and_pull(self, upload_folder):
        timestamp = int(time.time())
        filename = f"scan_{timestamp}.jpg"
        filepath = os.path.join(upload_folder, filename)

        if self.backend == 'mock':
            print("Nikon Z30 (Mock): Capturing...")
            time.sleep(1)
            img = np.zeros((1000,1000,3), dtype=np.uint8)
            img[:] = (100, 100, 140) 
            cv2.putText(img, "Nikon Z30 Capture", (100, 500), cv2.FONT_HERSHEY_SIMPLEX, 2, (255,255,255), 3)
            cv2.imwrite(filepath, img)
            return filepath
        
        print("Nikon Z30: Capturing...")
        
        if self.backend == 'digicamcontrol':
            # CameraControlCmd.exe /filename "C:\path\to\file.jpg" /capture
            try:
                # DCC requires absolute path
                abs_path = os.path.abspath(filepath)
                self.run_command(["/filename", abs_path, "/capture"])
                
                # Wait for file
                for _ in range(20): # Wait up to 10s
                    if os.path.exists(abs_path):
                         if os.path.getsize(abs_path) > 0:
                             time.sleep(0.5) 
                             return abs_path
                    time.sleep(0.5)
                return None
            except Exception as e:
                print(f"DCC Capture Error: {e}")
                return None

        if self.backend == 'gphoto2':
            try:
                cmd = ["gphoto2", "--capture-image-and-download", "--force-overwrite", "--filename", filename]
                subprocess.run(cmd, check=True, cwd=upload_folder, timeout=20)
                if os.path.exists(filepath):
                    return filepath
                return None
            except:
                return None
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

    def drive_rail(self, step):
        """
        Drive Macro Rail via Arduino (if available)
        step: +ve (Forward), -ve (Backward)
        Protocol: 'M:step' (Example)
        """
        if self.arduino:
            try:
                cmd = f"M:{step}\n"
                self.arduino.write(cmd.encode())
                time.sleep(1.0) # Wait for movement
                return True
            except Exception as e:
                print(f"Error driving rail: {e}")
                return False
        return False

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
                # For Manual Lens without Rail, we DO NOT shift focus in software.
                # User requested single shot for this lens.
                if device.manual_lens and not self.arduino:
                     print("Manual Lens (No Rail): Skipping focus shift loop. Capture once only.")
                     break 

                # Try Rail first if configured
                moved = False
                if self.arduino: 
                    moved = self.drive_rail(focus_step)
                
                if not moved and not device.manual_lens:
                    device.drive_focus(focus_step) 
                    time.sleep(1.5)
            
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
