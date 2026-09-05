#!/usr/bin/env bash
set -e

APK_PATH="$1"

if [ -z "$APK_PATH" ]; then
    echo "用法: ./scripts/install_line_apk.sh <path_to_line.apk>"
    echo ""
    echo "提示: 您可以從手機備份、APKPure 或 Uptodown 下載 LINE APK 放到本主機後執行。"
    exit 1
fi

if [ ! -f "$APK_PATH" ]; then
    echo "[-] 檔案不存在: $APK_PATH"
    exit 1
fi

echo "[+] 正在安裝 $APK_PATH 至 Waydroid (透過 ADB)..."
adb install -r "$APK_PATH"
echo "[+] 安裝完成！"
