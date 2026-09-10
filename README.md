# 📈 XAUUSD Buy/Sell Signal Generator (`main.py`)

ระบบวิเคราะห์และส่งสัญญาณซื้อขาย (Buy/Sell Signal) สำหรับราคาทองคำ **XAUUSD (Gold)** แบบ **Lightweight (LIGHT)** พัฒนาด้วย Python

---

## 🌟 คุณสมบัติเด่น (Features)
- 🚀 **Lightweight & Fast**: ทำงานรวดเร็ว ไม่ซับซ้อน ใช้ Resource น้อย
- 📊 **Technical Indicators**:
  - **EMA Crossover**: Exponential Moving Average 9 & 21 สัญญาณจุดตัดแนวโน้ม
  - **RSI (Relative Strength Index)**: วัดสภาวะ Overbought (ซื้อมากเกินไป) / Oversold (ขายมากเกินไป)
  - **ATR (Average True Range)**: คำนวณจุดตัดขาดทุน (Stop Loss) และทำกำไร (Take Profit) ตามความผันผวนของตลาด
- 🔔 **Signal Output**: แสดงผลสัญญาณชัดเจน (`BUY`, `SELL`, `HOLD`) พร้อมเหตุผลประกอบ
- 🛡️ **Environment Safety**: รองรับไฟล์ `.env` สำหรับซ่อน API Keys / Tokens

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)
```
signalxau/
├── main.py              # โค้ดหลักในการดึงราคา คำนวณ และแจ้งสัญญาณ
├── requirements.txt      # รายชื่อ Python package ที่จำเป็น
├── .env.example          # แม่แบบคอนฟิกและคีย์ต่างๆ
├── .gitignore            # กำหนดไฟล์ที่ไม่ต้อง push ขึ้น Git
├── README.md             # คู่มือการใช้งานโปรเจกต์ (ภาษาไทย)
└── read.md               # สำเนาคู่มือการพัฒนาและการ Push ขึ้น GitHub
```

---

## 🛠️ การติดตั้งและการใช้งาน (Installation & Usage)

### 1. ติดตั้ง Package ที่จำเป็น
เปิด Terminal / Command Prompt ในโฟลเดอร์โปรเจกต์ แล้วพิมพ์:
```bash
pip install -r requirements.txt
```

### 2. ตั้งค่าไฟล์สภาพแวดล้อม (Optional)
ก๊อปปี้ไฟล์ `.env.example` เป็น `.env` เพื่อปรับแต่งค่าต่างๆ (ถ้าต้องการ):
```bash
cp .env.example .env
```

### 3. รันโปรแกรมเพื่อรับสัญญาณ
```bash
python main.py
```

---

## 🚀 ขั้นตอนการ Push ขึ้น GitHub (Git Commands Workflow)

เมื่อพัฒนาและทดสอบโค้ดในเครื่องเรียบร้อยแล้ว ทำการ Push ขึ้น GitHub ตามขั้นตอนต่อไปนี้:

### 1. สร้างไฟล์ `.gitignore` (เพื่อป้องกันข้อมูลสำคัญ เช่น API Key / รหัสผ่าน รั่วไหล)
```bash
echo "__pycache__/" > .gitignore
echo "*.env" >> .gitignore
```

### 2. เริ่มต้นระบบ Git ในโฟลเดอร์
```bash
git init
```

### 3. เพิ่มไฟล์ทั้งหมดเข้าสู่ Staging
```bash
git add .
```

### 4. บันทึก Commit แรก
```bash
git commit -m "Initial commit: add main.py"
```

### 5. ตั้งชื่อ branch หลักเป็น main
```bash
git branch -M main
```

### 6. ผูกโฟลเดอร์ในเครื่องกับ GitHub Repository URL
```bash
git remote add origin https://github.com/jeerang/tradsignal
```

### 7. อัปโหลดไฟล์ขึ้น GitHub
```bash
git push -u origin main
```

---

## 📝 ข้อตกลงความเสี่ยง (Disclaimer)
สัญญาณที่สร้างขึ้นโดยโปรแกรมนี้ใช้สำหรับ **การศึกษาและการวิเคราะห์เชิงเทคนิคเบื้องต้นเท่านั้น** ไม่ใช่คำแนะนำทางการเงิน ผู้ใช้ควรบริหารความเสี่ยง (Risk Management) ในการเทรดด้วยตนเองเสมอ
