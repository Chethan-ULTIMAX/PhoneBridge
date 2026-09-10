import base64, io, json, os, socket, struct, threading, tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

DISCOVERY_PORT = 38741


def send_frame(sock, obj):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    sock.sendall(struct.pack(">I", len(raw)) + raw)


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        part = sock.recv(n - len(data))
        if not part:
            raise ConnectionError("Phone disconnected")
        data.extend(part)
    return bytes(data)


def recv_frame(sock):
    size = struct.unpack(">I", recv_exact(sock, 4))[0]
    if size > 4 * 1024 * 1024:
        raise ValueError("Frame too large")
    return json.loads(recv_exact(sock, size).decode())


class PhoneConnection:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.sock = None
        self.lock = threading.Lock()

    def connect(self, code):
        self.sock = socket.create_connection((self.host, self.port), timeout=8)
        self.sock.settimeout(30)
        send_frame(self.sock, {"op": "hello", "client": "PhoneBridge Desktop", "version": 1})
        hello = recv_frame(self.sock)
        if hello.get("pairing_required"):
            send_frame(self.sock, {"op": "pair", "code": code})
            hello = recv_frame(self.sock)
        if not hello.get("ok"):
            self.close()
            raise PermissionError(hello.get("error", "Connection rejected"))
        return hello

    def request(self, op, **kwargs):
        with self.lock:
            send_frame(self.sock, {"op": op, **kwargs})
            return recv_frame(self.sock)

    def download(self, remote, local):
        with self.lock:
            send_frame(self.sock, {"op": "file.download", "path": remote})
            meta = recv_frame(self.sock)
            if not meta.get("ok"):
                raise RuntimeError(meta.get("error", "Download failed"))
            left = int(meta["size"])
            with open(local, "wb") as f:
                while left:
                    b = self.sock.recv(min(1024 * 1024, left))
                    if not b:
                        raise ConnectionError("Disconnected during download")
                    f.write(b)
                    left -= len(b)

    def upload(self, local, remote):
        size = os.path.getsize(local)
        with self.lock:
            send_frame(self.sock, {"op": "file.upload", "path": remote, "size": size})
            ready = recv_frame(self.sock)
            if not ready.get("ready"):
                raise RuntimeError(ready.get("error", "Upload rejected"))
            with open(local, "rb") as f:
                while True:
                    b = f.read(1024 * 1024)
                    if not b:
                        break
                    self.sock.sendall(b)
            result = recv_frame(self.sock)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Upload failed"))

    def stream_connection(self, code):
        return PhoneConnection(self.host, self.port).connect(code)

    def open_secondary(self, code):
        c = PhoneConnection(self.host, self.port)
        c.connect(code)
        return c

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None


class App:
    def __init__(self, root):
        self.root = root
        root.title("PhoneBridge")
        root.geometry("1100x720")
        root.minsize(900, 620)
        self.connection = None
        self.screen_connection = None
        self.pair_code = None
        self.path = ""
        self.devices = {}
        self.screen_running = False
        self.screen_photo = None
        self.ui()
        self.discover()

    def ui(self):
        top = ttk.Frame(self.root, padding=18)
        top.pack(fill="x")
        ttk.Label(top, text="PhoneBridge", font=("Segoe UI", 23, "bold")).pack(side="left")
        self.status = ttk.Label(top, text="● Searching for phones…")
        self.status.pack(side="right")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.files_tab = ttk.Frame(self.tabs, padding=14)
        self.screen_tab = ttk.Frame(self.tabs, padding=14)
        self.apps_tab = ttk.Frame(self.tabs, padding=14)
        self.terminal_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.files_tab, text="📂 Files")
        self.tabs.add(self.screen_tab, text="🖥 Screen")
        self.tabs.add(self.apps_tab, text="📱 Apps")
        self.tabs.add(self.terminal_tab, text="⌨ Terminal")

        self.build_files_tab()
        self.build_screen_tab()
        self.build_apps_tab()
        self.build_terminal_tab()

    def build_files_tab(self):
        top = ttk.Frame(self.files_tab)
        top.pack(fill="x")
        self.device_list = tk.Listbox(top, height=3, activestyle="none")
        self.device_list.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Connect", command=self.connect).pack(side="left", padx=(10, 0))
        bar = ttk.Frame(self.files_tab)
        bar.pack(fill="x", pady=(12, 0))
        self.path_label = ttk.Label(bar, text="Internal Storage", font=("Segoe UI", 11, "bold"))
        self.path_label.pack(side="left")
        for text, cmd in (("Up", self.up), ("Refresh", self.refresh), ("New folder", self.mkdir), ("Upload", self.upload), ("Download", self.download), ("Delete", self.delete)):
            ttk.Button(bar, text=text, command=cmd).pack(side="right", padx=(6, 0))
        self.tree = ttk.Treeview(self.files_tab, columns=("name", "type", "size", "modified"), show="headings")
        for c, t, w in (("name", "Name", 470), ("type", "Type", 100), ("size", "Size", 120), ("modified", "Modified", 180)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, pady=10)
        self.tree.bind("<Double-1>", self.open_folder)
        self.tree.bind("<Button-3>", self.rename_popup)
        self.info = ttk.Label(self.files_tab, text="Open PhoneBridge on Android to begin.")
        self.info.pack(fill="x")

    def build_screen_tab(self):
        controls = ttk.Frame(self.screen_tab)
        controls.pack(fill="x")
        ttk.Button(controls, text="Start screen sharing", command=self.start_screen).pack(side="left")
        ttk.Button(controls, text="Stop", command=self.stop_screen).pack(side="left", padx=6)
        ttk.Button(controls, text="Back", command=lambda: self.input_cmd("input.back")).pack(side="left", padx=6)
        ttk.Button(controls, text="Home", command=lambda: self.input_cmd("input.home")).pack(side="left")
        ttk.Button(controls, text="Recents", command=lambda: self.input_cmd("input.recents")).pack(side="left", padx=6)
        self.screen_hint = ttk.Label(controls, text="Screen permission will be requested on the phone.")
        self.screen_hint.pack(side="right")
        self.screen_canvas = tk.Label(self.screen_tab, text="No screen stream", anchor="center")
        self.screen_canvas.pack(fill="both", expand=True, pady=10)
        self.screen_canvas.bind("<Button-1>", self.screen_tap)
        self.screen_canvas.bind("<B1-Motion>", self.screen_drag)
        self.last_point = None

    def build_apps_tab(self):
        bar = ttk.Frame(self.apps_tab)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refresh apps", command=self.refresh_apps).pack(side="left")
        ttk.Button(bar, text="Launch selected", command=self.launch_app).pack(side="left", padx=6)
        self.apps_tree = ttk.Treeview(self.apps_tab, columns=("name", "package"), show="headings")
        self.apps_tree.heading("name", text="App")
        self.apps_tree.heading("package", text="Package")
        self.apps_tree.column("name", width=260)
        self.apps_tree.column("package", width=520)
        self.apps_tree.pack(fill="both", expand=True, pady=10)

    def build_terminal_tab(self):
        row = ttk.Frame(self.terminal_tab)
        row.pack(fill="x")
        self.command = ttk.Entry(row)
        self.command.insert(0, "uname")
        self.command.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Run", command=self.run_terminal).pack(side="left", padx=6)
        ttk.Label(self.terminal_tab, text="Restricted read-only commands: pwd, ls, date, whoami, uname, id").pack(anchor="w", pady=8)
        self.terminal_output = tk.Text(self.terminal_tab, wrap="none", height=25)
        self.terminal_output.pack(fill="both", expand=True)

    def discover(self):
        def worker():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", DISCOVERY_PORT))
                s.settimeout(1)
                while True:
                    try:
                        data, addr = s.recvfrom(2048)
                        p = data.decode(errors="replace").split(" ")
                        if len(p) >= 5 and p[:2] == ["PHONEBRIDGE/1", "DISCOVER"]:
                            self.devices[p[2]] = (p[3].replace("_", " "), addr[0], int(p[4]))
                            self.root.after(0, self.refresh_devices)
                    except socket.timeout:
                        pass
                    except OSError:
                        return
            finally:
                s.close()
        threading.Thread(target=worker, daemon=True).start()

    def refresh_devices(self):
        self.device_list.delete(0, "end")
        for name, host, port in self.devices.values():
            self.device_list.insert("end", f"📱 {name} — {host}:{port}")
        self.status.config(text=f"● {len(self.devices)} phone(s) discovered")

    def connect(self):
        if not self.devices:
            return messagebox.showinfo("PhoneBridge", "No phone discovered. Use the same Wi-Fi.")
        i = (self.device_list.curselection() or (0,))[0]
        name, host, port = list(self.devices.values())[i]
        code = simpledialog.askstring("Pair Phone", f"Enter the 6-digit code shown on {name}:")
        if not code:
            return
        try:
            self.connection = PhoneConnection(host, port)
            self.connection.connect(code.strip())
            self.pair_code = code.strip()
            self.status.config(text=f"● Connected to {name}")
            self.path = ""
            self.refresh()
            self.refresh_apps()
        except Exception as e:
            self.connection = None
            messagebox.showerror("Connection failed", str(e))

    def require_connection(self):
        if not self.connection:
            messagebox.showinfo("PhoneBridge", "Connect a phone first.")
            return False
        return True

    def refresh(self):
        if not self.require_connection():
            return
        try:
            r = self.connection.request("storage.list", path=self.path)
            if not r.get("ok"):
                raise RuntimeError(r.get("error", "Unable to list storage"))
            self.tree.delete(*self.tree.get_children())
            for x in r.get("entries", []):
                modified = ""
                if x.get("modified"):
                    import datetime
                    modified = datetime.datetime.fromtimestamp(x["modified"] / 1000).strftime("%Y-%m-%d %H:%M")
                self.tree.insert("", "end", values=(x["name"], "Folder" if x["directory"] else "File", self.size(x.get("size", 0)), modified))
            self.path_label.config(text="Internal Storage" + ("/" + self.path if self.path else ""))
            self.info.config(text=f"{len(r.get('entries', []))} items")
        except Exception as e:
            messagebox.showerror("PhoneBridge", str(e))

    def selected(self):
        s = self.tree.selection()
        return self.tree.item(s[0], "values") if s else None

    def open_folder(self, _=None):
        x = self.selected()
        if x and x[1] == "Folder":
            self.path = "/".join(v for v in (self.path, x[0]) if v)
            self.refresh()

    def up(self):
        if self.path:
            self.path = self.path.rsplit("/", 1)[0] if "/" in self.path else ""
            self.refresh()

    def download(self):
        x = self.selected()
        if not x or x[1] == "Folder" or not self.require_connection():
            return
        target = filedialog.asksaveasfilename(initialfile=x[0])
        if target:
            try:
                self.connection.download("/".join(v for v in (self.path, x[0]) if v), target)
                messagebox.showinfo("PhoneBridge", "Download complete.")
            except Exception as e:
                messagebox.showerror("Download failed", str(e))

    def upload(self):
        if not self.require_connection():
            return
        src = filedialog.askopenfilename()
        if not src:
            return
        try:
            self.connection.upload(src, "/".join(v for v in (self.path, os.path.basename(src)) if v))
            self.refresh()
        except Exception as e:
            messagebox.showerror("Upload failed", str(e))

    def delete(self):
        x = self.selected()
        if not x or not self.require_connection():
            return
        if not messagebox.askyesno("Delete", f"Delete {x[0]} from the phone?"):
            return
        try:
            r = self.connection.request("storage.delete", path="/".join(v for v in (self.path, x[0]) if v))
            if not r.get("ok"):
                raise RuntimeError(r.get("error", "Delete failed"))
            self.refresh()
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))

    def mkdir(self):
        if not self.require_connection():
            return
        name = simpledialog.askstring("New folder", "Folder name:")
        if name:
            try:
                r = self.connection.request("storage.mkdir", path=self.path, name=name)
                if not r.get("ok"):
                    raise RuntimeError(r.get("error", "Could not create folder"))
                self.refresh()
            except Exception as e:
                messagebox.showerror("New folder", str(e))

    def rename_popup(self, _=None):
        x = self.selected()
        if not x or not self.require_connection():
            return
        name = simpledialog.askstring("Rename", "New name:", initialvalue=x[0])
        if name:
            try:
                r = self.connection.request("storage.rename", path="/".join(v for v in (self.path, x[0]) if v), name=name)
                if not r.get("ok"):
                    raise RuntimeError(r.get("error", "Rename failed"))
                self.refresh()
            except Exception as e:
                messagebox.showerror("Rename failed", str(e))

    def start_screen(self):
        if not self.require_connection() or not self.pair_code:
            return
        if ImageTk is None:
            return messagebox.showerror("Screen", "Pillow is required for screen viewing. Use the packaged Windows build from GitHub Actions.")
        if self.screen_running:
            return
        try:
            self.screen_connection = PhoneConnection(self.connection.host, self.connection.port)
            self.screen_connection.connect(self.pair_code)
            send_frame(self.screen_connection.sock, {"op": "screen.start"})
            self.screen_running = True
            self.screen_hint.config(text="Waiting for Android screen permission…")
            threading.Thread(target=self.screen_reader, daemon=True).start()
        except Exception as e:
            self.stop_screen()
            messagebox.showerror("Screen", str(e))

    def screen_reader(self):
        try:
            while self.screen_running and self.screen_connection and self.screen_connection.sock:
                frame = recv_frame(self.screen_connection.sock)
                if frame.get("op") == "screen.frame":
                    raw = base64.b64decode(frame["jpeg"])
                    image = Image.open(io.BytesIO(raw)).convert("RGB")
                    image.thumbnail((900, 560), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self.root.after(0, self.show_screen, photo)
                elif frame.get("ok") is False:
                    self.root.after(0, lambda f=frame: self.screen_hint.config(text=f.get("error", "Screen error")))
                elif frame.get("screen"):
                    self.root.after(0, lambda: self.screen_hint.config(text="Screen live • click to tap"))
        except Exception as e:
            if self.screen_running:
                self.root.after(0, lambda: self.screen_hint.config(text=f"Screen stopped: {e}"))
        finally:
            if self.screen_connection:
                self.screen_connection.close()

    def show_screen(self, photo):
        if self.screen_running:
            self.screen_photo = photo
            self.screen_canvas.config(image=photo, text="")

    def screen_tap(self, event):
        if self.last_point:
            self.input_cmd("input.tap", x=event.x, y=event.y)

    def screen_drag(self, event):
        self.last_point = (event.x, event.y)

    def input_cmd(self, op, **kwargs):
        if not self.screen_running or not self.screen_connection:
            return
        try:
            send_frame(self.screen_connection.sock, {"op": op, **kwargs})
        except Exception:
            pass

    def stop_screen(self):
        self.screen_running = False
        if self.screen_connection:
            try:
                send_frame(self.screen_connection.sock, {"op": "screen.stop"})
            except Exception:
                pass
            self.screen_connection.close()
            self.screen_connection = None
        self.screen_canvas.config(image="", text="No screen stream")
        self.screen_photo = None

    def refresh_apps(self):
        if not self.require_connection():
            return
        try:
            r = self.connection.request("apps.list")
            if not r.get("ok"):
                raise RuntimeError(r.get("error", "Unable to list apps"))
            self.apps_tree.delete(*self.apps_tree.get_children())
            for app in r.get("apps", []):
                self.apps_tree.insert("", "end", values=(app["name"], app["package"]))
        except Exception as e:
            messagebox.showerror("Apps", str(e))

    def launch_app(self):
        s = self.apps_tree.selection()
        if not s or not self.require_connection():
            return
        pkg = self.apps_tree.item(s[0], "values")[1]
        try:
            r = self.connection.request("app.launch", package=pkg)
            if not r.get("ok"):
                raise RuntimeError(r.get("error", "Launch failed"))
        except Exception as e:
            messagebox.showerror("Apps", str(e))

    def run_terminal(self):
        if not self.require_connection():
            return
        command = self.command.get().strip()
        try:
            r = self.connection.request("terminal.exec", command=command)
            self.terminal_output.delete("1.0", "end")
            self.terminal_output.insert("end", r.get("output", r.get("error", "")))
        except Exception as e:
            self.terminal_output.insert("end", str(e))

    @staticmethod
    def size(n):
        n = float(n)
        for u in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024 or u == "TB":
                return f"{n:.0f} {u}"
            n /= 1024

    def close(self):
        self.stop_screen()
        if self.connection:
            self.connection.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
