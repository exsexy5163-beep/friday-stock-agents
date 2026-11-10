#!/usr/bin/env bash
# ติดตั้ง friday บน Mac รันซ้ำได้ · ใช้: ./setup.sh  หรือ  ./setup.sh --skip-keys (ข้ามขั้นใส่ key และอีเมล)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
SKIP_KEYS=0
[ "${1:-}" = "--skip-keys" ] && SKIP_KEYS=1

die() { echo "❌ $1" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || die "friday รองรับเฉพาะ Mac"
case "$ROOT" in
  *[[:space:]]*) die "path ของโฟลเดอร์มีช่องว่าง ($ROOT) กรุณาย้ายไปที่ที่ไม่มีช่องว่าง เช่น ~/friday-stock-agents แล้วรันใหม่" ;;
esac
command -v uv >/dev/null || die "ไม่พบ uv ติดตั้งก่อนด้วย: brew install uv"
command -v claude >/dev/null || echo "⚠️  ไม่พบ Claude Code ติดตั้งก่อนใช้งานเอเจนต์: https://claude.com/claude-code"

echo "1/4 สร้างสภาพแวดล้อม Python (ครั้งแรกใช้เวลาสักครู่)"
make_venv() {
  uv venv --quiet --allow-existing --python 3.12 "$1"
  uv pip install --quiet --python "$1/bin/python" -r "$2"
}
make_venv tools/marketdata/.venv tools/marketdata/requirements.txt
make_venv .venv requirements-calc.txt
make_venv .venv-utils requirements-utils.txt

echo "2/4 ตั้งค่า path ให้ตรงกับเครื่องนี้"
OLD="$(cat .friday-root 2>/dev/null || echo "__FRIDAY_""ROOT__")"
if [ "$OLD" != "$ROOT" ]; then
  export OLD NEW="$ROOT"
  grep -rlIF --exclude=setup.sh --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.venv-utils -- "$OLD" . \
    | while IFS= read -r f; do perl -pi -e 's/\Q$ENV{OLD}\E/$ENV{NEW}/g' "$f"; done || true
  printf '%s\n' "$ROOT" > .friday-root
fi
mkdir -p outputs scratch
chmod +x tools/marketdata/marketdata

if [ "$SKIP_KEYS" = 1 ]; then
  echo "3/4 ข้ามขั้น API key และอีเมล (--skip-keys)"
else
  echo "3/4 ใส่ API key (เก็บใน Keychain ของเครื่องคุณเท่านั้น)"
  ask_key() { # service, ชื่อที่แสดง, ลิงก์สมัคร
    if security find-generic-password -s "$1" -a friday >/dev/null 2>&1; then
      echo "  ✓ มี $2 แล้ว"; return
    fi
    read -r -p "  ใส่ $2 ตอนนี้ไหม? ขอฟรีได้ที่ $3 [y/N] " yn
    case "$yn" in
      [yY]*) echo "  วาง key แล้วกด Enter สองครั้ง (จะไม่แสดงบนจอ)"
             security add-generic-password -U -a friday -s "$1" -w ;;
      *) echo "  ข้าม $2" ;;
    esac
  }
  ask_key fmp-api "FMP key" "https://site.financialmodelingprep.com/developer/docs"
  ask_key fred-api "FRED key" "https://fred.stlouisfed.org/docs/api/api_key.html"
  ask_key alphavantage-api "Alpha Vantage key (ไม่บังคับ)" "https://www.alphavantage.co/support/#api-key"

  ID_FILE=tools/marketdata/.edgar-identity
  if [ -s "$ID_FILE" ]; then
    echo "  ✓ มีอีเมลสำหรับ SEC แล้ว"
  else
    read -r -p "  อีเมลของคุณ (SEC บังคับให้ระบุเมื่อดึงงบ ไม่ถูกส่งไปที่อื่น): " email
    case "$email" in
      *@*.*) printf '%s\n' "$email" > "$ID_FILE"; chmod 600 "$ID_FILE" ;;
      *) echo "  ⚠️  รูปแบบอีเมลไม่ถูกต้อง ข้ามขั้นนี้ รัน ./setup.sh ใหม่เพื่อกรอก" ;;
    esac
  fi
fi

echo "4/4 ตรวจการติดตั้ง"
tools/marketdata/.venv/bin/python -c "import sys; sys.path.insert(0, 'tools/marketdata'); import core"
.venv-utils/bin/python tools/tony_check.py --rules >/dev/null
echo "✅ ติดตั้งเสร็จ เปิดใช้งานด้วย: claude"
echo "   ครั้งแรก Claude Code จะถามว่าอนุญาต MCP server ของโปรเจกต์นี้ไหม ให้ตอบอนุญาต"
