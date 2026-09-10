package com.chethan.phonebridge;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import androidx.appcompat.app.AppCompatActivity;
import androidx.documentfile.provider.DocumentFile;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class MainActivity extends AppCompatActivity {
    static final int DISCOVERY_PORT=38741, REQUEST_TREE=42;
    TextView status, codeView, storageView;
    Uri treeUri;
    Server server;
    Handler handler=new Handler(Looper.getMainLooper());
    Runnable announce;
    String pairingCode;

    @Override public void onCreate(Bundle b){ super.onCreate(b); buildUi(); generateCode(); startServices(); }
    void buildUi(){
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(32,40,32,32);
        TextView title=new TextView(this); title.setText("PhoneBridge"); title.setTextSize(30); title.setTypeface(null,1); root.addView(title);
        TextView sub=new TextView(this); sub.setText("Wireless bridge • local network only"); sub.setTextSize(16); root.addView(sub);
        status=new TextView(this); status.setText("● Starting…"); status.setTextSize(17); status.setPadding(0,35,0,10); root.addView(status);
        codeView=new TextView(this); codeView.setTextSize(32); codeView.setGravity(Gravity.CENTER); codeView.setPadding(0,20,0,20); root.addView(codeView);
        Button select=new Button(this); select.setText("Choose Internal Storage"); select.setOnClickListener(v->chooseStorage()); root.addView(select);
        storageView=new TextView(this); storageView.setPadding(0,20,0,0); root.addView(storageView);
        TextView help=new TextView(this); help.setText("Keep this app open while connecting. The desktop will discover this phone automatically. Approve only computers you trust."); help.setPadding(0,30,0,0); root.addView(help);
        setContentView(root);
    }
    void generateCode(){ pairingCode=String.format(Locale.US,"%06d",new Random().nextInt(1000000)); codeView.setText("PAIR CODE\n"+pairingCode); }
    void chooseStorage(){ Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE); i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION); startActivityForResult(i,REQUEST_TREE); }
    @Override protected void onActivityResult(int req,int res,Intent data){ super.onActivityResult(req,res,data); if(req==REQUEST_TREE&&res==RESULT_OK&&data!=null){ treeUri=data.getData(); try{getContentResolver().takePersistableUriPermission(treeUri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);}catch(Exception ignored){} storageView.setText("Storage access: ready\n"+treeUri); } }
    void startServices(){
        server=new Server(); server.start();
        announce=()->{ announce(); handler.postDelayed(announce,2000); }; handler.post(announce);
    }
    void announce(){ new Thread(()->{ try{ DatagramSocket s=new DatagramSocket(); s.setBroadcast(true); String name=android.os.Build.MODEL.replace(" ","_"); String msg="PHONEBRIDGE/1 DISCOVER "+deviceId()+" "+name+" "+server.port; byte[] b=msg.getBytes(StandardCharsets.UTF_8); s.send(new DatagramPacket(b,b.length,InetAddress.getByName("255.255.255.255"),DISCOVERY_PORT)); s.close(); }catch(Exception ignored){} }).start(); }
    String deviceId(){ return Settings.Secure.getString(getContentResolver(),Settings.Secure.ANDROID_ID); }
    @Override protected void onDestroy(){ handler.removeCallbacks(announce); if(server!=null)server.shutdown(); super.onDestroy(); }

    class Server extends Thread{
        ServerSocket ss; volatile boolean running=true; int port;
        Server(){ try{ss=new ServerSocket(0); ss.setReuseAddress(true); port=ss.getLocalPort();}catch(IOException e){throw new RuntimeException(e);} }
        public void run(){ while(running){ try{ Socket s=ss.accept(); new Client(s).start(); }catch(IOException e){if(running)postStatus("Server error: "+e.getMessage());} } }
        void shutdown(){running=false;try{ss.close();}catch(Exception ignored){}}
    }
    class Client extends Thread{
        Socket socket; DataInputStream in; DataOutputStream out; boolean paired=false;
        Client(Socket s){socket=s;try{socket.setSoTimeout(30000);in=new DataInputStream(new BufferedInputStream(s.getInputStream()));out=new DataOutputStream(new BufferedOutputStream(s.getOutputStream()));}catch(IOException e){}}
        public void run(){try{ JSONObject hello=readJson(); if(!"hello".equals(hello.optString("op"))){close();return;} writeJson(new JSONObject().put("ok",true).put("pairing_required",true).put("device_name",Build.MODEL)); JSONObject pair=readJson(); if(!pairingCode.equals(pair.optString("code"))){writeJson(new JSONObject().put("ok",false).put("error","Invalid pairing code"));close();return;} paired=true; writeJson(new JSONObject().put("ok",true).put("device_name",Build.MODEL)); postStatus("● Paired with a desktop"); while(paired){JSONObject r=readJson(); handle(r);} }catch(Exception e){ }finally{close();}}
        void handle(JSONObject r)throws Exception{String op=r.optString("op"); if("storage.list".equals(op))list(r.optString("path","")); else if("file.download".equals(op))download(r.optString("path","")); else if("file.upload".equals(op))upload(r.optString("path",""),r.optLong("size",-1)); else writeJson(new JSONObject().put("ok",false).put("error","Unsupported operation"));}
        void list(String path)throws Exception{ if(treeUri==null){writeJson(new JSONObject().put("ok",false).put("error","Choose Internal Storage on the phone first"));return;} DocumentFile f=resolve(path); if(f==null||!f.isDirectory()){writeJson(new JSONObject().put("ok",false).put("error","Folder not found"));return;} JSONArray a=new JSONArray(); for(DocumentFile x:f.listFiles())a.put(new JSONObject().put("name",x.getName()).put("directory",x.isDirectory()).put("size",x.isFile()?x.length():0)); writeJson(new JSONObject().put("ok",true).put("entries",a)); }
        DocumentFile resolve(String path){ DocumentFile f=DocumentFile.fromTreeUri(MainActivity.this,treeUri); if(f==null)return null; if(path==null||path.isEmpty())return f; for(String p:path.split("/")){if(p.isEmpty()||p.equals(".")||p.equals(".."))return null; DocumentFile next=null; for(DocumentFile x:f.listFiles())if(p.equals(x.getName())){next=x;break;} if(next==null)return null; f=next;} return f; }
        void download(String path)throws Exception{DocumentFile f=resolve(path);if(f==null||!f.isFile()){writeJson(new JSONObject().put("ok",false).put("error","File not found"));return;} writeJson(new JSONObject().put("ok",true).put("size",f.length()).put("name",f.getName())); try(InputStream src=getContentResolver().openInputStream(f.getUri())){byte[] b=new byte[1024*1024];int n;while((n=src.read(b))!=-1)out.write(b,0,n);out.flush();}}
        void upload(String path,long size)throws Exception{if(size<0||size>2L*1024*1024*1024){writeJson(new JSONObject().put("ok",false).put("error","Invalid file size"));return;} int slash=path.lastIndexOf('/');String parent=slash<0?"":path.substring(0,slash);String name=slash<0?path:path.substring(slash+1);if(name.isEmpty()||name.contains("..")){writeJson(new JSONObject().put("ok",false).put("error","Invalid filename"));return;}DocumentFile dir=resolve(parent);if(dir==null||!dir.isDirectory()){writeJson(new JSONObject().put("ok",false).put("error","Destination folder not found"));return;}DocumentFile target=dir.findFile(name);if(target!=null)target.delete();target=dir.createFile("application/octet-stream",name);if(target==null){writeJson(new JSONObject().put("ok",false).put("error","Cannot create file"));return;}writeJson(new JSONObject().put("ready",true));try(OutputStream dst=getContentResolver().openOutputStream(target.getUri())){byte[] b=new byte[1024*1024];long left=size;while(left>0){int n=in.read(b,0,(int)Math.min(b.length,left));if(n<0)throw new EOFException();dst.write(b,0,n);left-=n;}dst.flush();}writeJson(new JSONObject().put("ok",true));}
        JSONObject readJson()throws Exception{int n=in.readInt();if(n<0||n>4*1024*1024)throw new IOException("Invalid frame");byte[] b=new byte[n];in.readFully(b);return new JSONObject(new String(b,StandardCharsets.UTF_8));}
        void writeJson(JSONObject o)throws Exception{byte[] b=o.toString().getBytes(StandardCharsets.UTF_8);out.writeInt(b.length);out.write(b);out.flush();}
        void close(){try{socket.close();}catch(Exception ignored){}}
    }
    void postStatus(String s){runOnUiThread(()->status.setText(s));}
}
