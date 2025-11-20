# server.py - DEBUG VERSION
import uasyncio as asyncio
import os
import ujson
import _thread

AUTH_USER = "admin"
AUTH_PASS = "admin"
UPLOAD_DIR = "." 

LOCKED_FILES = [
    'boot.py', 'main.py', 'server.py', 
    'index.html', 'style.css', 'app.js', 
    'webrepl_cfg.py', 'uploads'
]

running_flags = {}

def get_fs_stats():
    try:
        stats = os.statvfs('/')
        block_size = stats[0]
        total_blocks = stats[2]
        free_blocks = stats[3]
        total_kb = (total_blocks * block_size) / 1024
        free_kb = (free_blocks * block_size) / 1024
        used_kb = total_kb - free_kb
        return int(total_kb), int(used_kb), int(free_kb)
    except: return 0, 0, 0

def get_file_info(path):
    try:
        st = os.stat(path)
        is_dir = (st[0] & 0o170000) == 0o040000
        size = st[6]
        if is_dir: return {'name': path, 'type': 'dir', 'size': 0}
        else: return {'name': path, 'type': 'file', 'size': size}
    except: return None

def check_auth(headers):
    auth = headers.get('Authorization')
    if not auth: return False
    try:
        import ubinascii
        token = auth.split(" ")[1]
        decoded = ubinascii.a2b_base64(token).decode().split(":")
        return decoded[0] == AUTH_USER and decoded[1] == AUTH_PASS
    except: return False

def run_script_thread(filename, flag_ref):
    try:
        exec(open(filename).read(), {'stop_flag': flag_ref, 'print': print, 'machine': __import__('machine'), 'time': __import__('time')})
    except Exception as e: print(f"Script Error: {e}")

def ensure_dir(path):
    parts = path.split('/')
    current = ""
    for p in parts[:-1]: 
        if p == "." or p == "": continue
        current += p + "/"
        try: os.stat(current)
        except: 
            try: os.mkdir(current.rstrip('/'))
            except: pass

async def save_upload(reader, boundary):
    state = 0 
    filename = None
    f = None
    while True:
        line = await reader.readline()
        if not line: break
        if state == 0:
            if b'filename="' in line:
                try:
                    line_str = line.decode()
                    parts = line_str.split('filename="')
                    fn = parts[1].split('"')[0]
                    fn = fn.replace("..", "")
                    if fn.startswith("/"): fn = fn[1:]
                    if "/" not in fn and fn in LOCKED_FILES: return False
                    filename = f"{UPLOAD_DIR}/{fn}"
                    if "/" in fn: ensure_dir(filename)
                    print(f"Saving: {filename}") # DEBUG PRINT
                except: return False
            if line == b'\r\n':
                if filename:
                    state = 1
                    f = open(filename, 'wb')
                else: return False 
        elif state == 1:
            if boundary in line:
                if f: f.close()
                return True
            else:
                if f: f.write(line)
    if f: f.close()
    return False

async def handle_client(reader, writer):
    try:
        request_line = await reader.readline()
        if not request_line: return
        parts = request_line.decode().split()
        if len(parts) < 3: return
        method, path, proto = parts
        
        headers = {}
        while True:
            line = await reader.readline()
            if not line or line == b'\r\n': break
            key, val = line.decode().split(":", 1)
            headers[key.strip()] = val.strip()

        if not check_auth(headers):
            await send_auth_challenge(writer)
            return

        clean_path = path.split('?')[0]
        
        # DEBUG: Print request
        print(f"Request: {method} {clean_path}")

        # 1. SMART ROUTING
        if clean_path == "/": 
            clean_path = "/index.html"
        
        # Try to find if it's a folder
        try:
            # Remove leading slash for os.stat
            check_path = clean_path
            if check_path.startswith("/"): check_path = check_path[1:]
            if check_path == "": check_path = "."
            
            st = os.stat(check_path)
            if (st[0] & 0o170000) == 0o040000: # Is Directory
                # Redirect if missing trailing slash
                if not clean_path.endswith("/"):
                     print(f"Redirecting {clean_path} to {clean_path}/")
                     await send_redirect(writer, clean_path + "/")
                     return
                
                clean_path = clean_path + "index.html"
                print(f"Serving Index: {clean_path}")
        except:
            pass 

        # 2. STATIC FILES
        if clean_path.endswith(".html"):
            await send_file(writer, clean_path, "text/html")
        elif clean_path.endswith(".css"):
            await send_file(writer, clean_path, "text/css")
        elif clean_path.endswith(".js"):
            await send_file(writer, clean_path, "application/javascript")
        elif clean_path.endswith(".png"):
            await send_file(writer, clean_path, "image/png")
        elif clean_path.endswith(".jpg"):
            await send_file(writer, clean_path, "image/jpeg")

        # API: FILES
        elif clean_path == "/api/files" and method == "GET":
            try:
                all_items = os.listdir(UPLOAD_DIR)
                file_list = []
                for item in all_items:
                    if item in LOCKED_FILES: continue
                    info = get_file_info(item)
                    if info: file_list.append(info)
            except: file_list = []
            await send_response(writer, 200, "application/json", ujson.dumps(file_list))

        # API: RUN
        elif path.startswith("/api/run") and method == "POST":
            target = path.split("=")[1]
            flag = [False]
            running_flags[target] = flag
            _thread.start_new_thread(run_script_thread, (target, flag))
            await send_response(writer, 200, "application/json", '{"status": "started"}')

        # API: STOP
        elif path.startswith("/api/stop") and method == "POST":
            target = path.split("=")[1]
            if target == "ALL":
                for k in running_flags: running_flags[k][0] = True
            elif target in running_flags:
                running_flags[target][0] = True
            await send_response(writer, 200, "application/json", '{"status": "stopping"}')

        # API: STATS
        elif clean_path == "/api/stats":
            t, u, f = get_fs_stats()
            await send_response(writer, 200, "application/json", '{"total":%d,"used":%d,"free":%d}'%(t,u,f))

        # API: READ
        elif path.startswith("/api/read") and method == "GET":
            target = path.split("=")[1]
            if target in LOCKED_FILES and "/" not in target:
                await send_response(writer, 403, "text/plain", "Access Denied")
                return
            try:
                with open(target, 'r') as f: content = f.read()
                await send_response(writer, 200, "text/plain", content)
            except:
                await send_response(writer, 404, "text/plain", "")

        # API: SAVE
        elif clean_path == "/api/save" and method == "POST":
            try:
                length = int(headers.get('Content-Length', 0))
                content = await reader.read(length)
                data = ujson.loads(content)
                filename = data['filename']
                code = data['code']
                if filename in LOCKED_FILES and "/" not in filename:
                    await send_response(writer, 403, "application/json", '{"error": "Protected"}')
                else:
                    with open(filename, 'w') as f: f.write(code)
                    await send_response(writer, 200, "application/json", '{"status": "saved"}')
            except: await send_response(writer, 500, "application/json", '{"error": "Save failed"}')

        # API: DELETE
        elif path.startswith("/api/delete") and method == "POST":
            target = path.split("=")[1]
            if target in LOCKED_FILES and "/" not in target:
                await send_response(writer, 403, "application/json", '{"error": "Protected"}')
            else:
                try:
                    try:
                        st = os.stat(target)
                        if (st[0] & 0o170000) == 0o040000:
                            for f in os.listdir(target): os.remove(f"{target}/{f}")
                            os.rmdir(target)
                        else: os.remove(target)
                    except: os.remove(target)
                    await send_response(writer, 200, "application/json", '{"status": "deleted"}')
                except:
                    await send_response(writer, 404, "application/json", '{"error": "failed"}')

        # API: UPLOAD
        elif clean_path == "/api/upload" and method == "POST":
            content_type = headers.get("Content-Type", "")
            if "boundary=" in content_type:
                boundary = content_type.split("boundary=")[1].encode()
                boundary = b"--" + boundary
                success = await save_upload(reader, boundary)
                if success: await send_response(writer, 200, "application/json", '{"status": "uploaded"}')
                else: await send_response(writer, 500, "application/json", '{"status": "failed"}')
            else: await send_response(writer, 400, "application/json", '{"error": "no boundary"}')

        else:
            print(f"404 Not Found: {clean_path}")
            await send_response(writer, 404, "text/plain", "Not Found")
    except Exception as e:
        print("Server Error:", e)
    finally:
        await writer.aclose()

async def send_file(writer, filename, mime):
    # Clean filename (remove leading /)
    if filename.startswith("/"): filename = filename[1:]
    
    print(f"Serving File: {filename}")
    try:
        size = os.stat(filename)[6]
        writer.write(f"HTTP/1.1 200 OK\r\nContent-Type: {mime}\r\nContent-Length: {size}\r\n\r\n".encode())
        await writer.drain()
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(1024)
                if not chunk: break
                writer.write(chunk)
                await writer.drain()
    except Exception as e:
        print(f"File Error {filename}: {e}")
        await send_response(writer, 404, "text/plain", "File Not Found")

async def send_response(writer, code, mime, body):
    response = f"HTTP/1.1 {code} OK\r\nContent-Type: {mime}\r\nAccess-Control-Allow-Origin: *\r\n\r\n{body}"
    writer.write(response.encode())
    await writer.drain()

async def send_redirect(writer, location):
    response = f"HTTP/1.1 301 Moved Permanently\r\nLocation: {location}\r\n\r\n"
    writer.write(response.encode())
    await writer.drain()

async def send_auth_challenge(writer):
    writer.write(b'HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Basic realm="ESP32"\r\n\r\n')
    await writer.drain()

async def start_server():
    await asyncio.start_server(handle_client, "0.0.0.0", 80)