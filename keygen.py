from core.security import security_manager

def main():
    print("========================================")
    print("   SCAN MASTER PRO - KEY GENERATOR")
    print("========================================")
    
    hwid = input("Enter Hardware ID (HWID): ").strip()
    
    if not hwid:
        print("Error: HWID cannot be empty.")
        return
        
    key = security_manager.generate_key(hwid)
    
    print("\n----------------------------------------")
    print(f"License Key: {key}")
    print("----------------------------------------")
    print("\nSave this key to 'license.key' in the app directory.")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
