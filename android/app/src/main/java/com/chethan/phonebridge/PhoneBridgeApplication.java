package com.chethan.phonebridge;

import android.app.Activity;
import android.app.Application;
import android.os.Bundle;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.nio.charset.StandardCharsets;
import java.util.Enumeration;

/** Adds interface-specific discovery broadcasts for Wi-Fi and phone-hotspot networks. */
public class PhoneBridgeApplication extends Application {
    private volatile MainActivity activity;
    private volatile boolean running;

    @Override public void onCreate() {
        super.onCreate();
        registerActivityLifecycleCallbacks(new ActivityLifecycleCallbacks() {
            @Override public void onActivityCreated(Activity a, Bundle state) {
                if (a instanceof MainActivity) {
                    activity = (MainActivity) a;
                    startAnnouncer();
                }
            }
            @Override public void onActivityDestroyed(Activity a) {
                if (a == activity) activity = null;
            }
            @Override public void onActivityStarted(Activity a) {}
            @Override public void onActivityResumed(Activity a) {}
            @Override public void onActivityPaused(Activity a) {}
            @Override public void onActivityStopped(Activity a) {}
            @Override public void onActivitySaveInstanceState(Activity a, Bundle state) {}
        });
    }

    private synchronized void startAnnouncer() {
        if (running) return;
        running = true;
        Thread t = new Thread(() -> {
            while (running) {
                announceOnInterfaces();
                try { Thread.sleep(2000L); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
            }
        }, "PhoneBridge-InterfaceDiscovery");
        t.setDaemon(true);
        t.start();
    }

    private void announceOnInterfaces() {
        MainActivity a = activity;
        if (a == null || a.server == null || a.server.port <= 0) return;

        String model = android.os.Build.MODEL.replace(' ', '_');
        String message = "PHONEBRIDGE/1 DISCOVER " + a.deviceId() + " " + model + " " + a.server.port;
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setBroadcast(true);
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            if (interfaces == null) return;
            while (interfaces.hasMoreElements()) {
                NetworkInterface ni = interfaces.nextElement();
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    InetAddress broadcast = ia.getBroadcast();
                    if (broadcast == null) continue;
                    try {
                        socket.send(new DatagramPacket(bytes, bytes.length, broadcast, MainActivity.DISCOVERY_PORT));
                    } catch (Exception ignored) {}
                }
            }
        } catch (Exception ignored) {}
    }
}
