#!/usr/bin/env bash

echo "=========================================="
echo " Stopping Waydroid + Weston Environment   "
echo "=========================================="

echo "[+] 停止 Waydroid Session..."
waydroid session stop 2>/dev/null || true

echo "[+] 關閉 Weston..."
killall weston 2>/dev/null || true

echo "[+] 斷開 ADB 連線..."
adb disconnect 2>/dev/null || true

echo "[+] 清理 Wayland Sockets..."
rm -f /run/user/$(id -u)/wayland-* 2>/dev/null || true

echo "[+] 完成！Waydroid 與 Weston 已停止。"
