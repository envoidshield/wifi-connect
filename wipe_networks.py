#!/usr/bin/env python3
import subprocess

def run(cmd):
    """Run a shell command and return stripped stdout."""
    result = subprocess.run(cmd, shell=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0 and result.stderr:
        print(f"[!] Error running '{cmd}': {result.stderr.strip()}")
    return result.stdout.strip()

def get_connections():
    """Return a list of saved connection names."""
    output = run("nmcli -t -f NAME connection show")
    return [line.strip() for line in output.splitlines() if line.strip()]

def disable_autoconnect(name):
    """Disable autoconnect for a given connection."""
    print(f"[-] Disabling autoconnect for: {name}")
    run(f"sudo nmcli connection modify '{name}' connection.autoconnect no")

def delete_connection(name):
    """Delete a given connection."""
    print(f"[x] Deleting connection: {name}")
    run(f"sudo nmcli connection delete '{name}'")

def restart_networkmanager():
    """Restart NetworkManager service."""
    print("[↻] Restarting NetworkManager...")
    run("sudo systemctl restart NetworkManager")

def main():
    print("[*] Fetching saved connections...")
    connections = get_connections()

    if not connections:
        print("[✓] No saved connections found.")
        return

    print(f"[*] Found {len(connections)} saved connections.")
    for name in connections:
        disable_autoconnect(name)
        delete_connection(name)

    restart_networkmanager()
    print("[✓] All saved connections removed successfully.")

if __name__ == "__main__":
    main()
