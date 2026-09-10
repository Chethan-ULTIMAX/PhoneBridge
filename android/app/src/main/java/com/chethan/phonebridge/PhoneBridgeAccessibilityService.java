package com.chethan.phonebridge;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.graphics.Path;
import android.os.Bundle;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityEvent;

/** Explicitly user-enabled input bridge. No hidden or background activation. */
public class PhoneBridgeAccessibilityService extends AccessibilityService {
    private static volatile PhoneBridgeAccessibilityService instance;

    @Override public void onServiceConnected() { instance = this; }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() { if (instance == this) instance = null; super.onDestroy(); }

    public static boolean isEnabled() { return instance != null; }

    public static boolean tap(float x, float y) {
        PhoneBridgeAccessibilityService s = instance;
        if (s == null) return false;
        Path p = new Path(); p.moveTo(x, y);
        GestureDescription g = new GestureDescription.Builder()
                .addStroke(new GestureDescription.StrokeDescription(p, 0, 80)).build();
        return s.dispatchGesture(g, null, null);
    }

    public static boolean swipe(float x1, float y1, float x2, float y2, long duration) {
        PhoneBridgeAccessibilityService s = instance;
        if (s == null) return false;
        Path p = new Path(); p.moveTo(x1, y1); p.lineTo(x2, y2);
        GestureDescription g = new GestureDescription.Builder()
                .addStroke(new GestureDescription.StrokeDescription(p, 0, Math.max(80, duration))).build();
        return s.dispatchGesture(g, null, null);
    }

    public static boolean back() {
        PhoneBridgeAccessibilityService s = instance;
        return s != null && s.performGlobalAction(GLOBAL_ACTION_BACK);
    }

    public static boolean home() {
        PhoneBridgeAccessibilityService s = instance;
        return s != null && s.performGlobalAction(GLOBAL_ACTION_HOME);
    }

    public static boolean recents() {
        PhoneBridgeAccessibilityService s = instance;
        return s != null && s.performGlobalAction(GLOBAL_ACTION_RECENTS);
    }

    public static boolean setFocusedText(String text) {
        PhoneBridgeAccessibilityService s = instance;
        if (s == null) return false;
        AccessibilityNodeInfo root = s.getRootInActiveWindow();
        if (root == null) return false;
        AccessibilityNodeInfo focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (focused == null) focused = root.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY);
        if (focused == null) return false;
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        return focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
    }
}
