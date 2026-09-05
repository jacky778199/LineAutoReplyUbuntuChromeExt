#!/usr/bin/env bash
set -e

USER_ID=$(id -u)
RUNTIME_DIR="/run/user/${USER_ID}"
export XDG_RUNTIME_DIR="${RUNTIME_DIR}"
mkdir -p /home/dinghonjay/.local/share/waydroid

echo "=========================================="
echo " Starting Waydroid + Weston Environment   "
echo "=========================================="

# 1. 確保 Xvfb (:99) 正常運作
if ! pgrep -f "Xvfb :99" > /dev/null; then
    echo "[+] 正在啟動 Xvfb :99 (1920x1080)..."
    Xvfb :99 -screen 0 1920x1080x24 &
    sleep 1
else
    echo "[*] Xvfb :99 已在運行中。"
fi

# 2. 確保 x11vnc 正常運作
if ! pgrep -f "x11vnc.*:99" > /dev/null; then
    echo "[+] 正在啟動 x11vnc (:99)..."
    x11vnc -display :99 -rfbauth /home/dinghonjay/.vnc/passwd -localhost -forever -bg >/dev/null 2>&1 || true
    sleep 1
else
    echo "[*] x11vnc 已在運行中。"
fi

# 3. 確保 pipewire-pulse 運作 (解決 LXC 音訊 socket 掛載問題)
systemctl --user start pipewire-pulse >/dev/null 2>&1 || true
if [ ! -S "${RUNTIME_DIR}/pulse/native" ]; then
    echo "[!] 警告: ${RUNTIME_DIR}/pulse/native 尚未就緒，嘗試再次啟動 pipewire-pulse..."
    systemctl --user restart pipewire-pulse >/dev/null 2>&1 || true
    sleep 1
fi

# 4. 啟動 Weston (嵌套在 DISPLAY :99，以手機比例 720x1280 呈現)
if ! pgrep -x weston > /dev/null; then
    echo "[+] 清理舊的 Wayland socket..."
    rm -f "${RUNTIME_DIR}"/wayland-* 2>/dev/null || true

    echo "[+] 正在啟動 Weston (540x960)..."
    DISPLAY=:99 weston --backend=x11 --width=540 --height=960 > /home/dinghonjay/.local/share/waydroid/weston.log 2>&1 &
    sleep 2
else
    echo "[*] Weston 已在運行中。"
fi

# 5. 取得現有 Wayland Display
W_DISP=$(ls -t "${RUNTIME_DIR}"/wayland-[0-9] 2>/dev/null | head -n 1 | xargs -r basename)
if [ -z "${W_DISP}" ]; then
    echo "[-] 錯誤: 找不到運作中的 Wayland socket！請檢查 ~/.local/share/waydroid/weston.log"
    exit 1
fi
export WAYLAND_DISPLAY="${W_DISP}"
echo "[+] 偵測到 Wayland Display: ${WAYLAND_DISPLAY}"

# 6. 確保 waydroid-container 服務執行中
if ! systemctl is-active --quiet waydroid-container; then
    echo "[+] 正在確認 waydroid-container.service..."
    sudo -n systemctl start waydroid-container 2>/dev/null || true
    sleep 2
fi

# 7. 啟動 Waydroid Session
SESSION_STATUS=$(waydroid status 2>/dev/null | grep "Session:" | awk '{print $2}' || true)
if [ "${SESSION_STATUS}" != "RUNNING" ]; then
    echo "[+] 正在啟動 Waydroid Session..."
    waydroid session start > /home/dinghonjay/.local/share/waydroid/session.log 2>&1 &
    
    for i in $(seq 1 20); do
        sleep 1
        SESSION_STATUS=$(waydroid status 2>/dev/null | grep "Session:" | awk '{print $2}' || true)
        if [ "${SESSION_STATUS}" = "RUNNING" ]; then
            echo "[+] Waydroid Session 成功啟動！"
            break
        fi
    done
else
    echo "[*] Waydroid Session 已在運行中。"
fi

# 8. 等待 Android 系統開機完成 (sys.boot_completed == 1)
echo "[+] 等待 Android 系統開機完成..."
BOOTED=0
for i in $(seq 1 40); do
    STATUS=$(waydroid shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)
    if [ "${STATUS}" = "1" ]; then
        BOOTED=1
        echo "[+] Android 系統已開機完畢！(耗時約 $((i * 2)) 秒)"
        break
    fi
    sleep 2
done

if [ "${BOOTED}" -ne 1 ]; then
    echo "[!] 警告: 開機逾時，但將繼續嘗試連線 ADB 與開啟介面。"
fi

# 9. 取得 IP 並連接 ADB
adb start-server >/dev/null 2>&1 || true
sleep 1
IP=$(grep -oE "([0-9]{1,3}\.){3}[0-9]{1,3}" /var/lib/misc/dnsmasq.waydroid0.leases 2>/dev/null | tail -n 1 || true)
if [ -n "${IP}" ]; then
    echo "[+] 連接 ADB 到 Waydroid IP: ${IP}:5555..."
    adb connect "${IP}:5555" || true
fi
adb devices

# 10. 拉起 Android 完整桌面 UI
echo "[+] 啟動 Waydroid 完整手機 UI..."
waydroid show-full-ui >/dev/null 2>&1 &

echo "=========================================="
echo " Waydroid 環境已成功就緒！                "
echo " 您可透過 VNC (Port 5900) 查看 Android 畫面 "
echo "=========================================="
