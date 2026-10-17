import os
import subprocess
import time

def mount_e01_via_wsl(e01_windows_path):
    """
    Translates a Windows path to WSL path, uses Kali to mount it via ewfmount,
    and returns the Windows path to the raw ewf1 file exposed by WSL.
    """
    # Create the mount point in Kali
    subprocess.run(["wsl", "-d", "kali-linux", "-u", "root", "mkdir", "-p", "/mnt/ewf"], capture_output=True)
    subprocess.run(["wsl", "-d", "kali-linux", "-u", "root", "umount", "/mnt/ewf"], capture_output=True) # Unmount if already mounted
    
    # Translate Windows path to WSL path
    # Translate Windows path to WSL path
    e01_windows_path = e01_windows_path.replace('\\', '/')
    if e01_windows_path.startswith('Z:/'):
        wsl_e01_path = e01_windows_path.replace('Z:/', '/mnt/z/')
    else:
        res = subprocess.run(["wsl", "-d", "kali-linux", "wslpath", "-a", e01_windows_path], capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"Failed to translate path to WSL: {res.stderr}")
        wsl_e01_path = res.stdout.strip()
    
    print(f"Mounting {wsl_e01_path} via ewfmount in Kali...")
    # Run ewfmount
    mount_res = subprocess.run(["wsl", "-d", "kali-linux", "-u", "root", "ewfmount", wsl_e01_path, "/mnt/ewf"], capture_output=True, text=True)
    if mount_res.returncode != 0:
        raise Exception(f"ewfmount failed: {mount_res.stderr}")
        
    # The raw file is now exposed to Windows via the WSL share!
    wsl_raw_windows_path = r"\\wsl.localhost\kali-linux\mnt\ewf\ewf1"
    
    # Wait a second for mount to propagate
    time.sleep(1)
    if not os.path.exists(wsl_raw_windows_path):
        raise Exception(f"Mount succeeded in Kali, but Windows cannot see {wsl_raw_windows_path}")
        
    return wsl_raw_windows_path
