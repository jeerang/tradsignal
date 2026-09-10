# 📈 XAUUSD Buy/Sell Signal Generator (`main.py`)

ระบบวิเคราะห์และส่งสัญญาณซื้อขาย (Buy/Sell Signal) สำหรับราคาทองคำ **XAUUSD (Gold)** แบบ **Lightweight (LIGHT)** พัฒนาด้วย Python

---

## 🌟 คุณสมบัติเด่น (Features)
- 🚀 **Lightweight & Fast**: ทำงานรวดเร็ว ไม่ซับซ้อน ใช้ Resource น้อย
- 📊 **Technical Indicators**:
  - **EMA Crossover**: Exponential Moving Average 9 & 21 สัญญาณจุดตัดแนวโน้ม
  - **RSI (Relative Strength Index)**: วัดสภาวะ Overbought / Oversold
  - **ATR (Average True Range)**: คำนวณจุดตัดขาดทุน (Stop Loss) และทำกำไร (Take Profit)
- 🔔 **Signal Output**: แสดงผลสัญญาณชัดเจน (`BUY`, `SELL`, `HOLD`) พร้อมเหตุผลประกอบ
- 🛡️ **Environment Safety**: รองรับไฟล์ `.env` สำหรับซ่อน API Keys / Tokens

---

## 🛠️ การติดตั้งและการใช้งาน (Installation & Usage)

```bash
# 1. ติดตั้ง Package
pip install -r requirements.txt

# 2. รันโปรแกรมส่งสัญญาณ
python main.py
```

---

## 🚀 ขั้นตอนการ Push ขึ้น GitHub (Git Commands Workflow)

```bash
# 1. สร้างไฟล์ .gitignore (แนะนำ เพื่อไม่ให้ Push ข้อมูลสำคัญ เช่น API Key / รหัสผ่าน)
echo "__pycache__/" > .gitignore
echo "*.env" >> .gitignore  

# 2 เริ่มต้นระบบ Git ในโฟลเดอร์
git init 

# 3. เพิ่มไฟล์ทั้งหมดเข้าสู่ Staging
git add . 

# 4. บันทึก Commit แรก
git commit -m "Initial commit: add main.py" 

# 5. ตั้งชื่อ branch หลักเป็น main
git branch -M main 

# 6. ผูกโฟลเดอร์ในเครื่องกับ GitHub Repository URL ที่สร้างไว้
git remote add origin https://github.com/jeerang/tradsignal 

# 7. อัปโหลดไฟล์ขึ้น GitHub
git push -u origin main
```
