import json, os, socket, struct, threading, tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog

DISCOVERY_PORT = 38741

def send_frame(sock, obj):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    sock.sendall(struct.pack(">I", len(raw)) + raw)

def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        part = sock.recv(n-len(data))
        if not part: raise ConnectionError("Phone disconnected")
        data.extend(part)
    return bytes(data)

def recv_frame(sock):
    size = struct.unpack(">I", recv_exact(sock, 4))[0]
    if size > 4*1024*1024: raise ValueError("Frame too large")
    return json.loads(recv_exact(sock, size).decode())

class PhoneConnection:
    def __init__(self, host, port):
        self.host, self.port, self.sock = host, port, None
        self.lock = threading.Lock()
    def connect(self, code):
        self.sock = socket.create_connection((self.host,self.port), timeout=8)
        self.sock.settimeout(30)
        send_frame(self.sock, {"op":"hello","client":"PhoneBridge Desktop","version":1})
        hello = recv_frame(self.sock)
        if hello.get("pairing_required"):
            send_frame(self.sock, {"op":"pair","code":code})
            hello = recv_frame(self.sock)
        if not hello.get("ok"):
            self.close(); raise PermissionError(hello.get("error","Connection rejected"))
        return hello
    def request(self, op, **kwargs):
        with self.lock:
            send_frame(self.sock, {"op":op, **kwargs}); return recv_frame(self.sock)
    def download(self, remote, local):
        with self.lock:
            send_frame(self.sock,{"op":"file.download","path":remote})
            meta=recv_frame(self.sock)
            if not meta.get("ok"): raise RuntimeError(meta.get("error","Download failed"))
            left=int(meta["size"])
            with open(local,"wb") as f:
                while left:
                    b=self.sock.recv(min(1024*1024,left))
                    if not b: raise ConnectionError("Disconnected during download")
                    f.write(b); left-=len(b)
    def upload(self, local, remote):
        size=os.path.getsize(local)
        with self.lock:
            send_frame(self.sock,{"op":"file.upload","path":remote,"size":size})
            ready=recv_frame(self.sock)
            if not ready.get("ready"): raise RuntimeError(ready.get("error","Upload rejected"))
            with open(local,"rb") as f:
                while True:
                    b=f.read(1024*1024)
                    if not b: break
                    self.sock.sendall(b)
            result=recv_frame(self.sock)
            if not result.get("ok"): raise RuntimeError(result.get("error","Upload failed"))
    def close(self):
        if self.sock:
            try:self.sock.close()
            finally:self.sock=None

class App:
    def __init__(self, root):
        self.root=root; root.title("PhoneBridge"); root.geometry("920x640"); root.minsize(760,520)
        self.connection=None; self.path=""; self.devices={}; self.ui(); self.discover()
    def ui(self):
        top=ttk.Frame(self.root,padding=18); top.pack(fill="x")
        ttk.Label(top,text="PhoneBridge",font=("Segoe UI",21,"bold")).pack(side="left")
        self.status=ttk.Label(top,text="● Searching for phones…"); self.status.pack(side="right")
        body=ttk.Frame(self.root,padding=18); body.pack(fill="both",expand=True)
        self.list= tk.Listbox(body,height=4,activestyle="none"); self.list.pack(fill="x",pady=(0,10))
        ttk.Button(body,text="Connect selected phone",command=self.connect).pack(anchor="w",pady=(0,14))
        bar=ttk.Frame(body); bar.pack(fill="x")
        self.path_label=ttk.Label(bar,text="Internal Storage",font=("Segoe UI",11,"bold")); self.path_label.pack(side="left")
        for text,cmd in (("Up",self.up),("Refresh",self.refresh),("Upload",self.upload),("Download",self.download)):
            ttk.Button(bar,text=text,command=cmd).pack(side="right",padx=(6,0))
        self.tree=ttk.Treeview(body,columns=("name","type","size"),show="headings")
        for c,t,w in (("name","Name",540),("type","Type",110),("size","Size",120)):
            self.tree.heading(c,text=t); self.tree.column(c,width=w)
        self.tree.pack(fill="both",expand=True,pady=10); self.tree.bind("<Double-1>",self.open)
        self.info=ttk.Label(body,text="Open PhoneBridge on Android to begin."); self.info.pack(fill="x")
    def discover(self):
        def worker():
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(("",DISCOVERY_PORT)); s.settimeout(1)
            while True:
                try:
                    data,addr=s.recvfrom(2048); p=data.decode(errors="replace").split(" ")
                    if len(p)>=5 and p[:2]==["PHONEBRIDGE/1","DISCOVER"]:
                        self.devices[p[2]]=(p[3],addr[0],int(p[4])); self.root.after(0,self.refresh_devices)
                except socket.timeout: pass
                except OSError: return
        threading.Thread(target=worker,daemon=True).start()
    def refresh_devices(self):
        self.list.delete(0,"end")
        for name,host,port in self.devices.values(): self.list.insert("end",f"📱 {name} — {host}:{port}")
        self.status.config(text=f"● {len(self.devices)} phone(s) discovered")
    def connect(self):
        if not self.devices: return messagebox.showinfo("PhoneBridge","No phone discovered. Use the same Wi-Fi.")
        i=(self.list.curselection() or (0,))[0]; name,host,port=list(self.devices.values())[i]
        code=simpledialog.askstring("Pair Phone",f"Enter the 6-digit code shown on {name}:")
        if not code:return
        try:
            self.connection=PhoneConnection(host,port); r=self.connection.connect(code.strip()); self.status.config(text=f"● Connected to {r.get('device_name',name)}"); self.path=""; self.refresh()
        except Exception as e: self.connection=None; messagebox.showerror("Connection failed",str(e))
    def refresh(self):
        if not self.connection:return
        try:
            r=self.connection.request("storage.list",path=self.path)
            if not r.get("ok"):raise RuntimeError(r.get("error","Unable to list storage"))
            self.tree.delete(*self.tree.get_children())
            for x in r.get("entries",[]):self.tree.insert("","end",values=(x["name"],"Folder" if x["directory"] else "File",self.size(x.get("size",0))))
            self.path_label.config(text="Internal Storage"+("/"+self.path if self.path else "")); self.info.config(text=f"{len(r.get('entries',[]))} items")
        except Exception as e:messagebox.showerror("PhoneBridge",str(e))
    def selected(self):
        s=self.tree.selection(); return self.tree.item(s[0],"values") if s else None
    def open(self,_=None):
        x=self.selected()
        if x and x[1]=="Folder":self.path="/".join(v for v in (self.path,x[0]) if v); self.refresh()
    def up(self):
        if self.path:self.path=self.path.rsplit("/",1)[0] if "/" in self.path else ""; self.refresh()
    def download(self):
        x=self.selected()
        if not x or x[1]=="Folder" or not self.connection:return
        target=filedialog.asksaveasfilename(initialfile=x[0])
        if target:
            try:self.connection.download("/".join(v for v in (self.path,x[0]) if v),target); messagebox.showinfo("PhoneBridge","Download complete.")
            except Exception as e:messagebox.showerror("Download failed",str(e))
    def upload(self):
        if not self.connection:return
        src=filedialog.askopenfilename()
        if not src:return
        try:self.connection.upload(src,"/".join(v for v in (self.path,os.path.basename(src)) if v)); self.refresh()
        except Exception as e:messagebox.showerror("Upload failed",str(e))
    @staticmethod
    def size(n):
        n=float(n)
        for u in ("B","KB","MB","GB","TB"):
            if n<1024 or u=="TB":return f"{n:.0f} {u}"
            n/=1024

if __name__=="__main__":
    root=tk.Tk(); App(root); root.mainloop()
