import requests
import time
import sys

BASE_URL = "http://127.0.0.1:5000"

def test_endpoint(name, url):
    try:
        print(f"Testing {name} ({url})...", end=" ")
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print("OK")
            return True
        else:
            print(f"Failed (Status {response.status_code})")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def run_tests():
    print("Waiting for server to start...")
    # Try connecting for up to 10 seconds
    for _ in range(10):
        try:
            requests.get(BASE_URL)
            break
        except:
            time.sleep(1)
            print(".", end="", flush=True)
    print()

    # 1. Test Index
    if not test_endpoint("Home Page", BASE_URL):
        print("CRITICAL: Server not reachable")
        sys.exit(1)

    # 2. Test Status API
    test_endpoint("Device Status (Mi13)", f"{BASE_URL}/api/status?device=mi13")
    
    # 3. Test History API (New logic)
    test_endpoint("History API", f"{BASE_URL}/api/history")

    print("\nTests Completed.")

if __name__ == "__main__":
    run_tests()
