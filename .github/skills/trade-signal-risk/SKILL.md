---
name: trade-signal-risk
description: 'Use when developing, reviewing, or changing XAU/USD trade-signal logic involving support, resistance, entry confirmation, Stop Loss, Take Profit, ATR, Risk:Reward, position sizing, breakout, or trailing stops.'
argument-hint: 'Describe the signal or risk-management behavior to implement or review.'
user-invocable: true
---

# XAU/USD Trade Signal Risk Skill

ใช้เป็นมาตรฐานในการพัฒนาระบบส่งสัญญาณ XAU/USD เท่านั้น ไม่ใช่คำแนะนำการลงทุน และไม่ควรตีความว่าแนวรับ แนวต้าน หรือ indicator ใดรับประกันผลลัพธ์

## When to Use

- เพิ่มหรือแก้ logic หาแนวรับและแนวต้าน
- ตรวจสัญญาณ BUY/SELL, breakout และ false breakout
- ออกแบบหรือ review ค่า Stop Loss (SL), Take Profit (TP) และ trailing stop
- ตรวจ Risk:Reward, ความเสี่ยงต่อออเดอร์ และ position size
- ตรวจข้อความสัญญาณก่อนส่งเข้า LINE หรือช่องทางแจ้งเตือนอื่น

## Core Principles

1. มอง support/resistance เป็นโซนราคา ไม่ใช่เลขจุดเดียว
2. ให้คะแนนโซนจากการตอบสนองซ้ำ จุดกลับตัวล่าสุด และบริบท timeframe ใหญ่กว่า
3. การแตะโซนเพียงอย่างเดียวไม่ใช่เหตุผลพอสำหรับการส่งสัญญาณ ต้องมี confirmation เช่น แท่งกลับตัว, การปิดแท่งกลับเข้าโซน, trend indicator หรือ momentum
4. แยกสองกรณีให้ชัด:
   - Rejection: ราคาแตะโซนแล้วปิดกลับเข้า range เดิม
   - Breakout: ราคาปิดพ้นโซนอย่างชัดเจน และควรรอการยืนยันหรือ retest เพื่อลด false breakout
5. ระวังข่าวเศรษฐกิจและช่วง volatility สูง อย่าส่งสัญญาณที่มี SL แคบผิดปกติเมื่อเทียบกับ ATR

## Finding Support and Resistance

ใช้ข้อมูลจากหลาย timeframe โดยเริ่มจากภาพใหญ่แล้วค่อยลง timeframe ทำสัญญาณ:

1. หา swing high และ swing low ที่ราคาเคยกลับตัวหลายครั้ง
2. รวมระดับที่อยู่ใกล้กันเป็นโซน โดยความกว้างต้องสัมพันธ์กับ volatility ของ XAU/USD
3. เพิ่มน้ำหนักให้ระดับที่มีการตอบสนองหลายครั้งและยังไม่ถูกทะลุอย่างมีนัยสำคัญ
4. ตรวจ pivot หรือ high/low ของวันก่อนเป็นระดับประกอบ ไม่ใช้แทนการยืนยันจาก price action
5. ใช้ HMA/EMA เพื่อดูทิศทางหลัก และ RSI เพื่อดู momentum เป็นตัวกรอง ไม่ใช้ indicator เดี่ยวตัดสินใจ
6. ห้ามเข้าเพียงเพราะราคาชนโซน ให้รอแท่งที่ปิดแล้วเพื่อป้องกันสัญญาณระหว่างแท่ง

## Stop Loss Rules

- BUY: วาง SL ใต้ support zone หรือใต้ swing low ที่เป็นเหตุผลของการเข้า
- SELL: วาง SL เหนือ resistance zone หรือเหนือ swing high ที่เป็นเหตุผลของการเข้า
- เผื่อ buffer นอกโซนตาม spread และ volatility เพื่อหลีกเลี่ยงการโดน sweep ระยะสั้น
- ใช้ ATR เป็นตัวตรวจความสมเหตุสมผล เช่น SL distance ต้องไม่แคบกว่าค่าขั้นต่ำที่กำหนดจาก ATR(14)
- ห้ามขยับ SL ให้ไกลขึ้นเพื่อหวังให้ราคาเด้งกลับ และห้ามถัวเฉลี่ยขาดทุนโดยไม่มีแผนที่อนุมัติไว้
- หากไม่มีข้อมูลเพียงพอสำหรับกำหนด SL ที่สมเหตุสมผล ให้ส่ง `HOLD` หรือไม่ส่งสัญญาณ

รูปแบบคำนวณที่ใช้ได้:

```text
BUY SL = min(support_zone_low, recent_swing_low) - buffer
SELL SL = max(resistance_zone_high, recent_swing_high) + buffer
buffer = max(spread_buffer, ATR(14) * buffer_atr_fraction)
```

## Take Profit and Risk:Reward

คำนวณ TP จากระยะความเสี่ยงจริง ไม่ใช่กำหนดตัวเลขตายตัว:

```text
BUY risk = entry - stop_loss
BUY TP(n) = entry + risk * reward_multiple(n)

SELL risk = stop_loss - entry
SELL TP(n) = entry - risk * reward_multiple(n)
R:R = reward_distance / risk_distance
```

- ค่าเริ่มต้นที่ควรทดสอบคือ R:R อย่างน้อย 1:2 แต่ต้องไม่วาง TP ชนแนวต้าน/แนวรับใกล้เกินไป
- ถ้า target ที่อิงโซนใกล้ที่สุดให้ R:R ไม่ผ่านเกณฑ์ ให้ `HOLD` หรือรอ setup ใหม่
- การแบ่ง TP ทำได้ เช่น TP1 ที่ 2R และปล่อยส่วนที่เหลือไป TP2/TP3 แต่ต้องประกาศสัดส่วนให้ชัด
- เมื่อถึง TP1 ให้พิจารณาปิดบางส่วนและเลื่อน SL เป็น breakeven เฉพาะเมื่อกติกาของกลยุทธ์ระบุไว้
- Trailing stop เหมาะกับ trend ที่ชัดเจน ไม่เหมาะกับตลาด sideways ที่มี pullback ถี่
- เมื่อใช้ trailing stop ให้เลื่อน SL ไปทางลดความเสี่ยงเท่านั้น ห้ามเลื่อนย้อนกลับ

## Position Size and Risk Guardrails

ถ้าระบบมีข้อมูล account balance และ contract value ให้คำนวณขนาด position ก่อนส่งสัญญาณ:

```text
risk_amount = account_equity * risk_percent
position_size = risk_amount / (stop_distance * value_per_price_unit)
```

- ตั้ง default risk ต่อสัญญาณให้ต่ำและปรับได้จาก environment/config ไม่ฝังตัวเลขลับใน source
- จำกัดความเสี่ยงรวมของสัญญาณที่ active พร้อมกัน และหยุดส่งเมื่อเกิน daily loss limit
- ถ้าไม่มีข้อมูล balance, contract size, spread หรือ slippage ให้รายงานระยะราคาและ R:R เท่านั้น ห้ามอ้างว่าเป็น lot size ที่ปลอดภัย
- ห้ามส่งสัญญาณที่ไม่มี entry, SL, TP, direction, timeframe และเหตุผลประกอบครบ

## Signal Gate

ก่อนส่ง BUY/SELL ต้องผ่านทุกข้อ:

1. มี direction และ timeframe ชัดเจน
2. มีโซน support/resistance ที่เป็นเหตุผลของ setup
3. มี confirmation จากแท่งที่ปิดแล้ว
4. SL อยู่ฝั่งถูกต้องและอยู่นอกโซนพร้อม buffer
5. TP คำนวณจาก risk distance และผ่าน R:R ขั้นต่ำ
6. ไม่มีความเสี่ยงจากข้อมูล stale, ค่า indicator เป็น NaN หรือแท่งข้อมูลไม่ครบ
7. ผ่านตัวกรองเวลาข่าว/ตลาดและกติกา session ของระบบ
8. ข้อความแจ้งเตือนระบุว่าเป็นสัญญาณเพื่อการศึกษา ไม่ใช่การรับประกันผลกำไร

ถ้าไม่ผ่านข้อใดข้อหนึ่ง ให้ส่ง `HOLD` พร้อมเหตุผลที่ตรวจสอบได้แทนการเดาค่า SL/TP

## Implementation and Test Checklist

- ทดสอบ BUY และ SELL แยกกัน รวมกรณี SL/TP กลับด้าน
- ทดสอบราคาแตะโซน, ปิดทะลุ, false breakout และ retest
- ทดสอบ ATR/RSI/HMA ที่มีค่า NaN และข้อมูลน้อยกว่าจำนวน period
- ทดสอบ trailing stop ว่าไม่เคยขยับเพิ่มความเสี่ยง
- ทดสอบ R:R เมื่อ entry อยู่ใกล้ support/resistance จน target ใช้ไม่ได้
- ทดสอบไม่มี API key, API timeout และข้อมูลราคาผิดรูปแบบ
- ทดสอบข้อความ LINE โดยไม่เปิดเผย token และไม่ส่งคำสั่งซื้อขายจริงจาก unit test

## Sources

- YLG Bullion, แนวรับ แนวต้าน คืออะไร? วิธีหาจุดเข้า-ออกสำหรับเทรดทองแบบแม่นยำ: https://www.ylgbullion.co.th/updates/analyst-research/1590/support-resistance-gold-trading
- Exness Help, การตั้งค่า Stop Loss (SL) และ Take Profit (TP): https://get.exness.help/hc/th/articles/360017263680-%E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B8%95%E0%B8%B1%E0%B8%87%E0%B8%84%E0%B8%B2-Stop-Loss-SL-%E0%B9%81%E0%B8%A5%E0%B8%B0-Take-Profit-TP
- Uhas, วิธีการตั้ง SL และ TP ก่อนเทรด Forex: https://uhas.com/setting-sl-and-tp-forex/

หมายเหตุ: ณ วันที่ศึกษา หน้า Exness redirect ไปหน้า login จึงใช้เป็นแหล่งอ้างอิงหัวข้อเท่านั้น และไม่บันทึกรายละเอียดที่ไม่สามารถตรวจเนื้อหาหน้าเดิมได้

## Current Project Development State

ข้อมูลส่วนนี้เป็นสถานะอ้างอิงสำหรับการพัฒนาต่อของ `tradsignal` และห้ามเก็บค่า secret จริงไว้ใน skill

### Runtime and Deployment

- แอปหลักอยู่ใน `main.py` เป็น FastAPI และ deploy บน Render ที่ `https://tradsignal.onrender.com`
- health check: `GET /healthz`
- LINE webhook: `POST /webhook`
- `GET /webhook` ใช้ตรวจข้อมูล endpoint ใน browser ได้ แต่ไม่ใช่การทดสอบ event จริง
- ใช้ `python-dotenv` โหลด config จาก environment; Render ต้องตั้ง `TWELVE_DATA_API_KEY`, `LINE_ACCESS_TOKEN` หรือ `LINE_CHANNEL_ACCESS_TOKEN`, และ `RENDER_EXTERNAL_URL`
- ห้ามใส่ API key หรือ LINE token ลง Git, skill, log หรือข้อความตอบผู้ใช้

### LINE Commands

- `ping`, `ทดสอบ`, `ทดสอบระบบ`: ตรวจเส้นทาง webhook และตอบ `pong`
- `ราคา`: ดึงราคาปัจจุบันจาก Twelve Data
- `วิเคราะห์`, `วิเคราะห์ราคา`, `วิเคราะห์เทรนด์`, `analyze`: วิเคราะห์ trend และแสดง Entry, BUY/SELL/HOLD, SL, TP1, TP2, TP3, RSI, ATR และโซน support/resistance
- `ตรวจสอบ`, `สถานะ`, `ตรวจสถานะ`, `เช็ค`, `check`: แสดงสถานะระบบและข้อมูลตลาด
- `เปิด scalping`, `เปิดโหมด scalping`, `scalping on`: เปิดโหมด 1m และให้ scheduler ตรวจทุกนาที
- `ปิด scalping`, `ปิดโหมด scalping`, `scalping off`: ปิดโหมด 1m และกลับไป timeframe ปกติ 5m/15m
- เมื่อ Twelve Data ใช้งานไม่ได้ command ตลาดต้องตอบ fallback ที่อธิบายปัญหา ไม่ปล่อยให้ LINE เงียบ

### Signal Implementation

- `get_current_session_tf()` คืน `1min/1m` เมื่อ `SCALPING_MODE=True`; เมื่อปิดใช้ `5min/5m` ก่อนเที่ยงไทย และ `15min/15m` หลังเที่ยง
- `analyze_market()` ใช้แท่งปิดล่าสุด, HMA(20), RSI(14), ATR(14) และเรียก `calculate_trade_levels()` ผ่าน risk gate
- `calculate_trade_levels()` ใช้ support/resistance ล่าสุดกับ ATR buffer, คำนวณ risk จริง และสร้าง TP ที่ 2R, 3.5R, 5R
- ถ้าข้อมูลไม่พอ, indicator เป็น NaN หรือพื้นที่ถึงโซนเป้าหมายไม่ผ่าน R:R 1:2 ให้ตอบ `HOLD`
- scheduler เรียก `check_signal()` ทุกนาที; ฟังก์ชันจะกรองเหลือรอบ 15 นาทีเมื่อปิด scalping
- ระบบหยุดสแกนหลัง 19:00 ตามเวลาไทย เป็นกติกาความปลอดภัยเดิม ต้องทบทวนก่อนเปลี่ยน

### TradingView Pine Strategy

- ไฟล์อ้างอิงอยู่ที่ `pinescript.md` และต้องมี strategy เพียงชุดเดียว ไม่วาง indicator เก่าต่อท้าย
- ใช้ Pine Script v6 และ `strategy()` เพื่อ backtest ไม่ใช้ `indicator()` สำหรับ logic ส่งสัญญาณหลัก
- สัญญาณต้องผ่าน `barstate.isconfirmed`, HMA direction, RSI, DI/ADX และ session Bangkok ก่อนเข้า
- Support/resistance ใช้ `ta.pivotlow()`/`ta.pivothigh()` ที่ยืนยันแล้วเท่านั้น เพื่อลด lookahead และ repaint
- Entry ใช้ close crossover/crossunder พร้อมแท่งยืนยัน ไม่ใช้ค่าระหว่างแท่ง
- SL ใช้โซน pivot + ATR buffer และบังคับ minimum stop distance; TP คำนวณจาก risk จริงที่ 2R/3.5R/5R
- ถ้าโซนเป้าหมายถัดไปให้ R:R ต่ำกว่า 1:2 จะไม่เปิด position
- Trailing stop เริ่มหลัง TP1 และเลื่อนได้เฉพาะทางลดความเสี่ยง
- Alert ใช้ dynamic JSON จาก `alert()` โดยมี action, symbol, timeframe, entry, sl, tp1, tp2, tp3, RSI และ ATR
- ก่อนนำไปใช้จริงต้องเปิดใน TradingView, ตรวจ Strategy Tester และสร้าง alert แบบ `Any alert() function call`; ห้ามถือว่า backtest รับประกันผลจริง

### Known Follow-up Work

1. เพิ่ม unit tests ถาวรสำหรับ `analyze_market()`, BUY/SELL level calculation และ command parser
2. เพิ่มการตรวจ webhook signature ของ LINE ก่อนประมวลผล event
3. เพิ่มข่าวเศรษฐกิจ, spread และ slippage filter ก่อนส่งสัญญาณจริง
4. เพิ่ม position sizing จาก account equity เมื่อมี contract specification ที่เชื่อถือได้
5. แยกสถานะ scalping และ trade state ออกจาก global memory หาก Render ใช้หลาย instance หรือ restart บ่อย
6. ตรวจ Render Logs เมื่อ LINE เงียบ: `LINE Command Received`, `LINE Reply Sent`, `LINE Reply Error`, `Analysis Command Error`

### Validation Commands

```powershell
\.\.venv\Scripts\python.exe -m py_compile main.py
Invoke-WebRequest -Uri "https://tradsignal.onrender.com/healthz"
Invoke-WebRequest -Uri "https://tradsignal.onrender.com/webhook" -Method POST -ContentType "application/json" -Body '{"events":[]}'
```

การทดสอบ `ping` หรือ `analyze` ผ่าน LINE ต้องทดสอบ event จริงหลัง Render deploy commit ล่าสุด และต้องไม่ส่ง token ผ่าน command line หรือแชต