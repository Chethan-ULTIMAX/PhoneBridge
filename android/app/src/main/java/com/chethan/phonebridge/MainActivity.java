package com.chethan.phonebridge;

import android.app.*;
import android.content.*;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.*;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.*;
import android.widget.*;
import androidx.appcompat.app.AppCompatActivity;
import androidx.documentfile.provider.DocumentFile;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class MainActivity extends AppCompatActivity {
    static final int DISCOVERY_PORT=38741, REQUEST_TREE=42, REQUEST_SCREEN=43;
    TextView status, codeView, storageView;
    Uri treeUri;
    Server server;
    Handler handler=new Handler(Looper.getMainLooper());
    Runnable announce;
    String pairingCode;
    volatile Client screenClient;
    Client pendingScreenClient;
    MediaProjection mediaProjection;
    VirtualDisplay virtualDisplay;
    ImageReader imageReader;
    int captureWidth, captureHeight;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        buildUi();
        generateCode();
        startServices();
    }

    void buildUi() {
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32,40,32,32);
        TextView title=new TextView(this);
        title.setText("PhoneBridge"); title.setTextSize(30); title.setTypeface(null,1); root.addView(title);
        TextView sub=new TextView(this);
        sub.setText("Wireless bridge • local network only"); sub.setTextSize(16); root.addView(sub);
        status=new TextView(this); status.setText("● Starting…"); status.setTextSize(17); status.setPadding(0,35,0,10); root.addView(status);
        codeView=new TextView(this); codeView.setTextSize(32); codeView.setGravity(Gravity.CENTER); codeView.setPadding(0,20,0,20); root.addView(codeView);
        Button select=new Button(this); select.setText("Choose Internal Storage"); select.setOnClickListener(v->chooseStorage()); root.addView(select);
        storageView=new TextView(this); storageView.setPadding(0,20,0,0); root.addView(storageView);
        Button access=new Button(this); access.setText("Enable touch control (optional)"); access.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))); root.addView(access);
        TextView help=new TextView(this);
        help.setText("Keep this app open while connecting. Screen sharing uses Android's system permission dialog. Touch control requires explicitly enabling PhoneBridge in Accessibility settings.");
        help.setPadding(0,20,0,0); root.addView(help);
        setContentView(root);
    }

    void generateCode() { pairingCode=String.format(Locale.US,"%06d",new Random().nextInt(1000000)); codeView.setText("PAIR CODE\n"+pairingCode); }

    void chooseStorage() {
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(i,REQUEST_TREE);
    }

    @Override protected void onActivityResult(int req,int res,Intent data) {
        super.onActivityResult(req,res,data);
        if(req==REQUEST_TREE && res==RESULT_OK && data!=null) {
            treeUri=data.getData();
            try { getContentResolver().takePersistableUriPermission(treeUri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION); } catch(Exception ignored) {}
            storageView.setText("Storage access: ready\n"+treeUri);
        }
        if(req==REQUEST_SCREEN) {
            Client c=pendingScreenClient; pendingScreenClient=null;
            if(res==RESULT_OK && data!=null && c!=null) {
                MediaProjectionManager m=(MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);
                mediaProjection=m.getMediaProjection(res,data); startScreen(c);
            } else if(c!=null) try { c.writeJson(new JSONObject().put("ok",false).put("error","Screen capture permission was denied")); } catch(Exception ignored) {}
        }
    }

    void startServices() {
        server=new Server(); server.start();
        announce=()->{ announce(); handler.postDelayed(announce,2000); };
        handler.post(announce);
    }

    void announce() {
        new Thread(()->{ try {
            DatagramSocket s=new DatagramSocket(); s.setBroadcast(true);
            String name=Build.MODEL.replace(" ","_");
            String msg="PHONEBRIDGE/1 DISCOVER "+deviceId()+" "+name+" "+server.port;
            byte[] b=msg.getBytes(StandardCharsets.UTF_8);
            s.send(new DatagramPacket(b,b.length,InetAddress.getByName("255.255.255.255"),DISCOVERY_PORT)); s.close();
        } catch(Exception ignored) {} }).start();
    }

    String deviceId() { return Settings.Secure.getString(getContentResolver(),Settings.Secure.ANDROID_ID); }

    @Override protected void onDestroy() { handler.removeCallbacks(announce); stopScreen(); if(server!=null)server.shutdown(); super.onDestroy(); }

    void requestScreen(Client c) {
        if(mediaProjection!=null) { startScreen(c); return; }
        pendingScreenClient=c;
        MediaProjectionManager m=(MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);
        startActivityForResult(m.createScreenCaptureIntent(),REQUEST_SCREEN);
    }

    void startScreen(Client c) {
        stopScreen(); screenClient=c;
        DisplayMetrics dm=new DisplayMetrics(); getWindowManager().getDefaultDisplay().getRealMetrics(dm);
        captureWidth=Math.min(dm.widthPixels,1280); captureHeight=Math.min(dm.heightPixels,720);
        if(captureWidth<=0||captureHeight<=0) { try { c.writeJson(new JSONObject().put("ok",false).put("error","Invalid display size")); } catch(Exception ignored) {} return; }
        imageReader=ImageReader.newInstance(captureWidth,captureHeight,PixelFormat.RGBA_8888,2);
        imageReader.setOnImageAvailableListener(r->{
            Image image=null;
            try {
                image=r.acquireLatestImage(); if(image==null||screenClient==null)return;
                Image.Plane p=image.getPlanes()[0]; int pixel=p.getPixelStride(), row=p.getRowStride(); ByteBuffer buf=p.getBuffer();
                int padded=Math.max(captureWidth,row/pixel);
                Bitmap full=Bitmap.createBitmap(padded,captureHeight,Bitmap.Config.ARGB_8888); full.copyPixelsFromBuffer(buf);
                Bitmap bmp=(padded==captureWidth)?full:Bitmap.createBitmap(full,0,0,captureWidth,captureHeight);
                ByteArrayOutputStream baos=new ByteArrayOutputStream(); bmp.compress(Bitmap.CompressFormat.JPEG,45,baos);
                if(bmp!=full)full.recycle(); bmp.recycle();
                String encoded=Base64.encodeToString(baos.toByteArray(),Base64.NO_WRAP);
                JSONObject frame=new JSONObject().put("op","screen.frame").put("width",captureWidth).put("height",captureHeight).put("jpeg",encoded);
                screenClient.writeJson(frame);
            } catch(Exception ignored) { } finally { if(image!=null)image.close(); }
        },handler);
        virtualDisplay=mediaProjection.createVirtualDisplay("PhoneBridge",captureWidth,captureHeight,dm.densityDpi,DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,imageReader.getSurface(),null,handler);
        try { c.writeJson(new JSONObject().put("ok",true).put("screen",true).put("width",captureWidth).put("height",captureHeight).put("accessibility",PhoneBridgeAccessibilityService.isEnabled())); } catch(Exception ignored) {}
        postStatus("● Screen sharing with desktop");
    }

    void stopScreen() {
        screenClient=null;
        if(virtualDisplay!=null){virtualDisplay.release();virtualDisplay=null;}
        if(imageReader!=null){imageReader.close();imageReader=null;}
    }

    class Server extends Thread {
        ServerSocket ss; volatile boolean running=true; int port;
        Server(){ try { ss=new ServerSocket(0); ss.setReuseAddress(true); port=ss.getLocalPort(); } catch(IOException e){ throw new RuntimeException(e); } }
        public void run(){ while(running){ try { new Client(ss.accept()).start(); } catch(IOException e){ if(running)postStatus("Server error: "+e.getMessage()); } } }
        void shutdown(){ running=false; try{ss.close();}catch(Exception ignored){} }
    }

    class Client extends Thread {
        Socket socket; DataInputStream in; DataOutputStream out; boolean paired=false; final Object writeLock=new Object();
        Client(Socket s){ socket=s; try{socket.setSoTimeout(30000);in=new DataInputStream(new BufferedInputStream(s.getInputStream()));out=new DataOutputStream(new BufferedOutputStream(s.getOutputStream()));}catch(IOException ignored){} }
        public void run(){
            try {
                JSONObject hello=readJson(); if(!"hello".equals(hello.optString("op"))){close();return;}
                writeJson(new JSONObject().put("ok",true).put("pairing_required",true).put("device_name",Build.MODEL));
                JSONObject pair=readJson();
                if(!pairingCode.equals(pair.optString("code"))){writeJson(new JSONObject().put("ok",false).put("error","Invalid pairing code"));close();return;}
                paired=true; writeJson(new JSONObject().put("ok",true).put("device_name",Build.MODEL)); postStatus("● Paired with a desktop");
                while(paired){ JSONObject r=readJson(); handle(r); }
            } catch(Exception ignored) {} finally { if(screenClient==this)stopScreen(); close(); }
        }
        void handle(JSONObject r)throws Exception {
            String op=r.optString("op");
            if("storage.list".equals(op))list(r.optString("path",""));
            else if("file.download".equals(op))download(r.optString("path",""));
            else if("file.upload".equals(op))upload(r.optString("path",""),r.optLong("size",-1));
            else if("storage.delete".equals(op))delete(r.optString("path",""));
            else if("storage.rename".equals(op))rename(r.optString("path",""),r.optString("name",""));
            else if("storage.mkdir".equals(op))mkdir(r.optString("path",""),r.optString("name",""));
            else if("storage.stats".equals(op))stats();
            else if("device.info".equals(op))deviceInfo();
            else if("apps.list".equals(op))apps();
            else if("app.launch".equals(op))launch(r.optString("package",""));
            else if("terminal.exec".equals(op))terminal(r.optString("command",""));
            else if("screen.start".equals(op))requestScreen(this);
            else if("screen.stop".equals(op)){if(screenClient==this)stopScreen();writeJson(new JSONObject().put("ok",true));}
            else if("input.tap".equals(op))writeJson(new JSONObject().put("ok",PhoneBridgeAccessibilityService.tap((float)r.optDouble("x"),(float)r.optDouble("y")).put("accessibility",PhoneBridgeAccessibilityService.isEnabled()));
            else if("input.swipe".equals(op))writeJson(new JSONObject().put("ok",PhoneBridgeAccessibilityService.swipe((float)r.optDouble("x1"),(float)r.optDouble("y1"),(float)r.optDouble("x2"),(float)r.optDouble("y2"),(long)r.optDouble("duration",300))).put("accessibility",PhoneBridgeAccessibilityService.isEnabled()));
            else if("input.back".equals(op))writeJson(new JSONObject().put("ok",PhoneBridgeAccessibilityService.back()));
            else if("input.home".equals(op))writeJson(new JSONObject().put("ok",PhoneBridgeAccessibilityService.home()));
            else if("input.recents".equals(op))writeJson(new JSONObject().put("ok",PhoneBridgeAccessibilityService.recents()));
            else if("input.text".equals(op))writeJson(new JSONObject().put("ok",PhoneBridgeAccessibilityService.setFocusedText(r.optString("text",""))));
            else writeJson(new JSONObject().put("ok",false).put("error","Unsupported operation"));
        }
        void list(String path)throws Exception{if(treeUri==null){writeJson(new JSONObject().put("ok",false).put("error","Choose Internal Storage on the phone first"));return;}DocumentFile f=resolve(path);if(f==null||!f.isDirectory()){writeJson(new JSONObject().put("ok",false).put("error","Folder not found"));return;}JSONArray a=new JSONArray();for(DocumentFile x:f.listFiles())a.put(new JSONObject().put("name",x.getName()).put("directory",x.isDirectory()).put("size",x.isFile()?x.length():0).put("modified",x.lastModified()));writeJson(new JSONObject().put("ok",true).put("entries",a));}
        DocumentFile resolve(String path){DocumentFile f=DocumentFile.fromTreeUri(MainActivity.this,treeUri);if(f==null)return null;if(path==null||path.isEmpty())return f;for(String p:path.split("/")){if(p.isEmpty()||p.equals(".")||p.equals(".."))return null;DocumentFile next=null;for(DocumentFile x:f.listFiles())if(p.equals(x.getName())){next=x;break;}if(next==null)return null;f=next;}return f;}
        void download(String path)throws Exception{DocumentFile f=resolve(path);if(f==null||!f.isFile()){writeJson(new JSONObject().put("ok",false).put("error","File not found"));return;}writeJson(new JSONObject().put("ok",true).put("size",f.length()).put("name",f.getName()));try(InputStream src=getContentResolver().openInputStream(f.getUri())){byte[] b=new byte[1024*1024];int n;while((n=src.read(b))!=-1)out.write(b,0,n);out.flush();}}
        void upload(String path,long size)throws Exception{if(size<0||size>2L*1024*1024*1024){writeJson(new JSONObject().put("ok",false).put("error","Invalid file size"));return;}int slash=path.lastIndexOf('/');String parent=slash<0?"":path.substring(0,slash);String name=slash<0?path:path.substring(slash+1);if(name.isEmpty()||name.equals(".")||name.equals("..")||name.contains("/")){writeJson(new JSONObject().put("ok",false).put("error","Invalid filename"));return;}DocumentFile dir=resolve(parent);if(dir==null||!dir.isDirectory()){writeJson(new JSONObject().put("ok",false).put("error","Destination folder not found"));return;}DocumentFile target=dir.findFile(name);if(target!=null)target.delete();target=dir.createFile("application/octet-stream",name);if(target==null){writeJson(new JSONObject().put("ok",false).put("error","Cannot create file"));return;}writeJson(new JSONObject().put("ready",true));try(OutputStream dst=getContentResolver().openOutputStream(target.getUri())){byte[] b=new byte[1024*1024];long left=size;while(left>0){int n=in.read(b,0,(int)Math.min(b.length,left));if(n<0)throw new EOFException();dst.write(b,0,n);left-=n;}dst.flush();}writeJson(new JSONObject().put("ok",true));}
        void delete(String path)throws Exception{DocumentFile f=resolve(path);writeJson(new JSONObject().put("ok",f!=null&&f.delete()));}
        void rename(String path,String name)throws Exception{if(name.isEmpty()||name.contains("/")||name.equals(".")||name.equals("..")){writeJson(new JSONObject().put("ok",false).put("error","Invalid name"));return;}DocumentFile f=resolve(path);writeJson(new JSONObject().put("ok",f!=null&&f.renameTo(name)));}
        void mkdir(String path,String name)throws Exception{DocumentFile d=resolve(path);if(d==null||!d.isDirectory()||name.isEmpty()||name.contains("/")){writeJson(new JSONObject().put("ok",false).put("error","Invalid directory name"));return;}writeJson(new JSONObject().put("ok",d.createDirectory(name)!=null));}
        void stats()throws Exception{if(treeUri==null){writeJson(new JSONObject().put("ok",false).put("error","Storage not selected"));return;}Stat s=new Stat();walk(DocumentFile.fromTreeUri(MainActivity.this,treeUri),s);writeJson(new JSONObject().put("ok",true).put("files",s.files).put("folders",s.folders).put("bytes",s.bytes));}
        void walk(DocumentFile f,Stat s){if(f==null)return;if(f.isDirectory()){s.folders++;for(DocumentFile x:f.listFiles())walk(x,s);}else{s.files++;s.bytes+=Math.max(0,f.length());}}
        class Stat{long files,folders,bytes;}
        void deviceInfo()throws Exception{Runtime rt=Runtime.getRuntime();writeJson(new JSONObject().put("ok",true).put("model",Build.MODEL).put("manufacturer",Build.MANUFACTURER).put("android",Build.VERSION.RELEASE).put("sdk",Build.VERSION.SDK_INT).put("memory_available",rt.maxMemory()));}
        void apps()throws Exception{PackageManager pm=getPackageManager();JSONArray a=new JSONArray();for(ApplicationInfo ai:pm.getInstalledApplications(PackageManager.GET_META_DATA)){if(pm.getLaunchIntentForPackage(ai.packageName)!=null)a.put(new JSONObject().put("name",pm.getApplicationLabel(ai).toString()).put("package",ai.packageName));}writeJson(new JSONObject().put("ok",true).put("apps",a));}
        void launch(String pkg)throws Exception{if(pkg.isEmpty()){writeJson(new JSONObject().put("ok",false).put("error","Missing package"));return;}Intent i=getPackageManager().getLaunchIntentForPackage(pkg);if(i==null){writeJson(new JSONObject().put("ok",false).put("error","App cannot be launched"));return;}i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(i);writeJson(new JSONObject().put("ok",true));}
        void terminal(String command)throws Exception{String c=command.trim();if(!(c.equals("pwd")||c.equals("date")||c.equals("whoami")||c.equals("uname")||c.equals("ls")||c.equals("id"))){writeJson(new JSONObject().put("ok",false).put("error","Restricted terminal: allowed commands are pwd, ls, date, whoami, uname, id"));return;}try{java.lang.Process p=Runtime.getRuntime().exec(new String[]{"/system/bin/sh","-c",c});BufferedReader br=new BufferedReader(new InputStreamReader(p.getInputStream()));StringBuilder outText=new StringBuilder();String line;while((line=br.readLine())!=null){if(outText.length()>20000)break;outText.append(line).append('\n');}int exit=p.waitFor();writeJson(new JSONObject().put("ok",exit==0).put("exit",exit).put("output",outText.toString()));}catch(Exception e){writeJson(new JSONObject().put("ok",false).put("error",e.getMessage()));}}
        JSONObject readJson()throws Exception{int n=in.readInt();if(n<0||n>4*1024*1024)throw new IOException("Invalid frame");byte[] b=new byte[n];in.readFully(b);return new JSONObject(new String(b,StandardCharsets.UTF_8));}
        void writeJson(JSONObject o)throws Exception{byte[] b=o.toString().getBytes(StandardCharsets.UTF_8);if(b.length>4*1024*1024)throw new IOException("Frame too large");synchronized(writeLock){out.writeInt(b.length);out.write(b);out.flush();}}
        void close(){try{socket.close();}catch(Exception ignored){}}
    }
    void postStatus(String s){runOnUiThread(()->status.setText(s));}
}