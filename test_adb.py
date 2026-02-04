import subprocess
import os

def check_adb():
    local_adb = os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')
    if os.path.exists(local_adb):
        adb_exe = local_adb
    else:
        adb_exe = "adb"
        
    print(f"Using ADB: {adb_exe}")
    
    try:
        cmd = [adb_exe, "devices", "-l"]
        print(f"Running: {cmd}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        print(f"Return Code: {result.returncode}")
        print(f"Stdout:\n{result.stdout}")
        print(f"Stderr:\n{result.stderr}")
        
        output = result.stdout.strip().split('\n')
        print(f"Split lines: {len(output)}")
        for i, line in enumerate(output):
            print(f"{i}: {line}")
            
        found_device = None
        # Logic from adb_handler.py
        # for line in output[1:]:
        
        # Modified logic to be safer
        start_index = 0
        if len(output) > 0 and "List of devices attached" in output[0]:
            start_index = 1
            
        print(f"Scanning from index {start_index}")
        
        for line in output[start_index:]:
            if line.strip() and "device" in line and "offline" not in line:
                print(f"Found candidate line: {line}")
                parts = line.split()
                serial = parts[0]
                model = "Unknown"
                for part in parts:
                    if part.startswith("model:"):
                        model = part.split(":")[1]
                found_device = {"serial": serial, "model": model}
                break
                
        print(f"Result: {found_device}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_adb()
