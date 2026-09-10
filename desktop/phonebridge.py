import json
import os
import socket
import struct
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DISCOVERY_PORT = 38741
MAGIC = b"PHONEBRIDGE/1"


def send_frame(sock, obj):
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack(">I", len(raw)) + raw)


def recv_frame(sock):
    header = _recv_exact(sock, 4)
    if not header:
        return None
    size = struct.unpack(">I", header)[0]
    if size > 4 * 1024 * 1024:
        raise ValueError("Frame is too large")
    return json.loads(_recv_exact(sock, size).decode("utf-8"))


def _recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise ConnectionError("Phone disconnected")
        data.extend(part)
    return bytes(data)


class PhoneConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()

    def connect(self, code=None):
        self.sock = socket.create_connection((self.host, self.port), timeout=8)
        self.sock.settimeout(15)
        send_frame(self.sock, {"op": "hello", "client": "PhoneBridge Desktop", "version": 1})
        reply = recv_frame(self.sock)
        if reply.get("pairing_required"):
            if not code:
                self.close()
                raise PermissionError("Pairing code required")
            send_frame(self.sock, {"op": "pair", "code": code})
            reply = recv_frame(self.sock)
        if not reply.get("ok"):
            self.close()
            raise PermissionError(reply.get("error", "Connection rejected"))
        return reply

    def request(self, op, **kwargs):
        with self.lock:
            send_frame(self.sock, {"op": op, **kwargs})
            return recv_frame(self.sock)

    def download(self, remote_path, local_path):
        with self.lock:
            send_frame(self.sock, {"op": "file.download", "path": remote_path})
            meta = recv_frame(self.sock)
            if not meta.get("ok"):
                raise RuntimeError(meta.get("error", "Download failed"))
            remaining = int(meta["size"])
            with open(local_path, "wb") as out:
                while remaining:
                    chunk = self.sock.recv(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError("Phone disconnected during download")
                    out.write(chunk)
                    remaining -= len(chunk)

    def upload(self, local_path, remote_path):
        size = os.path.getsize(local_path)
        with self.lock:
            send_frame(self.sock, {"op": "file.upload", "path": remote_path, "size": size})
            reply = recv_frame(self.sock)
            if not reply.get("ready"):
                raise RuntimeError(reply.get("error", "Upload rejected"))
            with open(local_path, "rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    self.sock.sendall(chunk)
            result = recv_frame(self.sock)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Upload failed"))

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None


class PhoneBridgeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PhoneBridge")
        self.root.geometry("900x620")
        self.root.minsize(760, 520)
        self.connection = None
        self.current_path = ""
        self.discovery = {}
        self._build_ui()
        self.root.after(400, self.start_discovery)

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        header = ttk.Frame(self.root, padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text="PhoneBridge", font=("Segoe UI", 20, "bold")).pack(side="left")
        self.status = ttk.Label(header, text="● Searching for phones…")
        self.status.pack(side="right", pady=7)

        body = ttk.Frame(self.root, padding=18)
        body.pack(fill="both", expand=True)

        self.devices = tk.Listbox(body, height=5, activestyle="none")
        self.devices.pack(fill="x", pady=(0, 12))
        ttk.Button(body, text="Connect selected phone", command=self.connect_selected).pack(anchor="w", pady=(0, 15))

        toolbar = ttk.Frame(body)
        toolbar.pack(fill="x")
        self.path_label = ttk.Label(toolbar, text="Internal Storage", font=("Segoe UI", 11, "bold"))
        self.path_label.pack(side="left")
        ttk.Button(toolbar, text="Up", command=self.go_up).pack(side="right")
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="right", padx=6)
        ttk.Button(toolbar, text="Upload", command=self.upload).pack(side="right")
        ttk.Button(toolbar, text="Download", command=self.download).pack(side="right", padx=6)

        columns = ("name", "type", "size")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("size", text="Size")
        self.tree.column("name", width=520)
        self.tree.column("type", width=110)
        self.tree.column("size", width=120)
        self.tree.pack(fill="both", expand=True, pady=(10, 0))
        self.tree.bind("<Double-1>", self.open_item)

        self.info = ttk.Label(body, text="Connect a phone to browse its shared storage.")
        self.info.pack(fill="x", pady=(10, 0))

    def start_discovery(self):
        def worker():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(1)
            while True:
                try:
                    data, addr = sock.recvfrom(2048)
                    text = data.decode("utf-8", "replace")
                    if text.startswith("PHONEBRIDGE/1 DISCOVER "):
                        parts = text.split(" ")
                        if len(parts) >= 5:
                            device_id, name, port = parts[2], parts[3], int(parts[4])
                            self.discovery[device_id] = (name, addr[0], port)
                            self.root.after(0, self.refresh_devices)
                except socket.timeout:
                    continue
                except OSError:
                    break
        threading.Thread(target=worker, daemon=True).start()

    def refresh_devices(self):
        self.devices.delete(0, "end")
        for device_id, (name, host, port) in self.discovery.items():
            self.devices.insert("end", f"📱 {name}  —  {host}:{port}")
        self.status.config(text=f"● {len(self.discovery)} phone(s) discovered")

    def connect_selected(self):
        if not self.discovery:
            messagebox.showinfo("PhoneBridge", "No phone discovered. Put the phone and PC on the same Wi-Fi and open the PhoneBridge app.")
            return
        index = self.devices.curselection()
        if not index:
            index = (0,)
        item = list(self.discovery.values())[index[0]]
        name, host, port = item
        code = tk.simpledialog.askstring("Pair Phone", f"Enter the 6-digit code shown on {name}:")
        if not code:
            return
        try:
            self.connection = PhoneConnection(host, port)
            reply = self.connection.connect(code)
            self.status.config(text=f"● Connected to {reply.get('device_name', name)}")
            self.current_path = ""
            self.refresh()
        except Exception as exc:
            self.connection = None
            messagebox.showerror("Connection failed", str(exc))

    def refresh(self):
        if not self.connection:
            return
        try:
            reply = self.connection.request("storage.list", "path" if False else path=self.current_path)
            if not reply.get("ok"):
                raise RuntimeError(reply.get("error", "Unable to list storage"))
            self.tree.delete(*self.tree.get_children())
            for entry in reply.get("entries", []):
                self.tree.insert("", "end", values=(entry["name"], "Folder" if entry["directory"] else "File", self.human_size(entry.get("size", 0))))
            self.path_label.config(text="Internal Storage" + ("/" + self.current_path if self.current_path else ""))
            self.info.config(text=f"{len(reply.get('entries', []))} items")
        except Exception as exc:
            messagebox.showerror("PhoneBridge", str(exc))

    def selected(self):
        item = self.tree.selection()
        if not item:
            return None
        return self.tree.item(item[0], "values")

    def open_item(self, _event=None):
        entry = self.selected()
        if not entry or entry[1] != "Folder":
            return
        self.current_path = "/".join(x for x in (self.current_path, entry[0]) if x)
        self.refresh()

    def go_up(self):
        if self.current_path:
            self.current_path = self.current_path.rsplit("/", 1)[0] if "/" in self.current_path else ""
            self.refresh()

    def download(self):
        entry = self.selected()
        if not entry or entry[1] == "Folder" or not self.connection:
            return
        remote = "/".join(x for x in (self.current_path, entry[0]) if x)
        target = filedialog.asksaveasfilename(initialfile=entry[0])
        if not target:
            return
        try:
            self.connection.download(remote, target)
            messagebox.showinfo("PhoneBridge", "Download complete.")
        except Exception as exc:
            messagebox.showerror("Download failed", str(exc))

    def upload(self):
        if not self.connection:
            return
        source = filedialog.askopenfilename()
        if not source:
            return
        remote = "/".join(x for x in (self.current_path, os.path.basename(source)) if x)
        try:
            self.connection.upload(source, remote)
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Upload failed", str(exc))

    @staticmethod
    def human_size(size):
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.0f} {unit}"
            size /= 1024


if __name__ == "__main__":
    import tkinter.simpledialog
    root = tk.Tk()
    PhoneBridgeApp(root)
    root.mainloop()
