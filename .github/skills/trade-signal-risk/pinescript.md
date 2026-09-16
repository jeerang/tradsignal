//@version=6
strategy("TradeSignal XAUUSD - Confirmed Structure Risk", overlay=true, precision=2,
     pyramiding=0, process_orders_on_close=true, calc_on_order_fills=true,
     initial_capital=10000, default_qty_type=strategy.percent_of_equity,
     default_qty_value=1, commission_type=strategy.commission.percent,
     commission_value=0.02)

// Confirmed-bar strategy: no current-candle prediction and no future pivot use.
groupTrend = "Trend and Confirmation"
source = input.source(close, "Source", group=groupTrend)
baselineLength = input.int(20, "HMA Length", minval=2, group=groupTrend)
rsiLength = input.int(14, "RSI Length", minval=2, group=groupTrend)
adxLength = input.int(14, "ADX Length", minval=2, group=groupTrend)
minimumAdx = input.float(18.0, "Minimum ADX", minval=0, step=0.5, group=groupTrend)
minimumRsiLong = input.float(52.0, "Minimum RSI for BUY", minval=0, maxval=100, step=0.5, group=groupTrend)
maximumRsiShort = input.float(48.0, "Maximum RSI for SELL", minval=0, maxval=100, step=0.5, group=groupTrend)

groupStructure = "Support and Resistance Zones"
pivotLeft = input.int(3, "Pivot Left Bars", minval=1, group=groupStructure)
pivotRight = input.int(3, "Pivot Right Bars", minval=1, group=groupStructure)
zoneAtrWidth = input.float(0.25, "Zone Width (ATR)", minval=0.05, step=0.05, group=groupStructure)

groupRisk = "Risk Management"
atrLength = input.int(14, "ATR Length", minval=2, group=groupRisk)
stopBufferAtr = input.float(0.25, "SL Buffer (ATR)", minval=0.05, step=0.05, group=groupRisk)
minimumStopAtr = input.float(1.0, "Minimum SL Distance (ATR)", minval=0.25, step=0.25, group=groupRisk)
minimumRewardRisk = input.float(2.0, "Minimum R:R", minval=1.0, step=0.25, group=groupRisk)
tp1R = input.float(2.0, "TP1 (R)", minval=0.5, step=0.25, group=groupRisk)
tp2R = input.float(3.5, "TP2 (R)", minval=1.0, step=0.25, group=groupRisk)
tp3R = input.float(5.0, "TP3 (R)", minval=1.5, step=0.25, group=groupRisk)
useTrailing = input.bool(true, "Use Trailing Stop After TP1", group=groupRisk)
trailingAtr = input.float(1.0, "Trailing Distance (ATR)", minval=0.25, step=0.25, group=groupRisk)

groupSession = "Session Filter"
useSessionFilter = input.bool(true, "Use Bangkok Session Filter", group=groupSession)
sessionStart = input.int(7, "Start Hour (Bangkok)", minval=0, maxval=23, group=groupSession)
sessionEnd = input.int(19, "End Hour (Bangkok)", minval=1, maxval=24, group=groupSession)

baseline = ta.hma(source, baselineLength)
rsiValue = ta.rsi(source, rsiLength)
atrValue = ta.atr(atrLength)
[plusDi, minusDi, adxValue] = ta.dmi(adxLength, adxLength)
confirmedBar = barstate.isconfirmed
bangkokHour = hour(time, "Asia/Bangkok")
sessionAllowed = not useSessionFilter or (bangkokHour >= sessionStart and bangkokHour < sessionEnd)

confirmedPivotLow = ta.pivotlow(low, pivotLeft, pivotRight)
confirmedPivotHigh = ta.pivothigh(high, pivotLeft, pivotRight)
lastSupport = ta.valuewhen(not na(confirmedPivotLow), confirmedPivotLow, 0)
lastResistance = ta.valuewhen(not na(confirmedPivotHigh), confirmedPivotHigh, 0)
zoneBuffer = atrValue * math.max(zoneAtrWidth, stopBufferAtr)
supportZoneLow = lastSupport - zoneBuffer
resistanceZoneHigh = lastResistance + zoneBuffer

trendUp = close > baseline and baseline > baseline[1] and plusDi > minusDi
trendDown = close < baseline and baseline < baseline[1] and minusDi > plusDi
longConfirmation = ta.crossover(close, baseline) and close > open and rsiValue >= minimumRsiLong
shortConfirmation = ta.crossunder(close, baseline) and close < open and rsiValue <= maximumRsiShort
trendStrengthOk = adxValue >= minimumAdx

longStop = math.min(nz(supportZoneLow, close - atrValue * minimumStopAtr), close - atrValue * minimumStopAtr)
shortStop = math.max(nz(resistanceZoneHigh, close + atrValue * minimumStopAtr), close + atrValue * minimumStopAtr)
longRisk = close - longStop
shortRisk = shortStop - close
longTargetRoom = nz(lastResistance, close + longRisk * minimumRewardRisk) - close
shortTargetRoom = close - nz(lastSupport, close - shortRisk * minimumRewardRisk)
longRiskOk = longRisk >= atrValue * minimumStopAtr and longTargetRoom >= longRisk * minimumRewardRisk
shortRiskOk = shortRisk >= atrValue * minimumStopAtr and shortTargetRoom >= shortRisk * minimumRewardRisk

longSignal = confirmedBar and sessionAllowed and strategy.position_size == 0 and trendUp and longConfirmation and trendStrengthOk and longRiskOk
shortSignal = confirmedBar and sessionAllowed and strategy.position_size == 0 and trendDown and shortConfirmation and trendStrengthOk and shortRiskOk

var float entryPrice = na
var float stopPrice = na
var float riskDistance = na
var float target1 = na
var float target2 = na
var float target3 = na
var float entryAtr = na
var int tradeDirection = 0
var bool tp1Reached = false

if longSignal
    entryPrice := close
    stopPrice := longStop
    riskDistance := longRisk
    target1 := entryPrice + riskDistance * tp1R
    target2 := entryPrice + riskDistance * tp2R
    target3 := entryPrice + riskDistance * tp3R
    entryAtr := atrValue
    tradeDirection := 1
    tp1Reached := false
    strategy.entry("BUY", strategy.long)

if shortSignal
    entryPrice := close
    stopPrice := shortStop
    riskDistance := shortRisk
    target1 := entryPrice - riskDistance * tp1R
    target2 := entryPrice - riskDistance * tp2R
    target3 := entryPrice - riskDistance * tp3R
    entryAtr := atrValue
    tradeDirection := -1
    tp1Reached := false
    strategy.entry("SELL", strategy.short)

if strategy.position_size > 0 and tradeDirection == 1
    if high >= target1
        tp1Reached := true
    if useTrailing and tp1Reached
        stopPrice := math.max(stopPrice, high - entryAtr * trailingAtr)
    strategy.exit("BUY-TP1", "BUY", limit=target1, stop=stopPrice, qty_percent=33)
    strategy.exit("BUY-TP2", "BUY", limit=target2, stop=stopPrice, qty_percent=33)
    strategy.exit("BUY-TP3", "BUY", limit=target3, stop=stopPrice, qty_percent=34)

if strategy.position_size < 0 and tradeDirection == -1
    if low <= target1
        tp1Reached := true
    if useTrailing and tp1Reached
        stopPrice := math.min(stopPrice, low + entryAtr * trailingAtr)
    strategy.exit("SELL-TP1", "SELL", limit=target1, stop=stopPrice, qty_percent=33)
    strategy.exit("SELL-TP2", "SELL", limit=target2, stop=stopPrice, qty_percent=33)
    strategy.exit("SELL-TP3", "SELL", limit=target3, stop=stopPrice, qty_percent=34)

if strategy.position_size == 0 and strategy.position_size[1] != 0
    entryPrice := na
    stopPrice := na
    riskDistance := na
    target1 := na
    target2 := na
    target3 := na
    entryAtr := na
    tradeDirection := 0
    tp1Reached := false

plot(baseline, "HMA Baseline", color=trendUp ? color.green : trendDown ? color.red : color.gray, linewidth=2)
plot(lastSupport, "Confirmed Support", color=color.new(color.green, 35), style=plot.style_linebr)
plot(lastResistance, "Confirmed Resistance", color=color.new(color.red, 35), style=plot.style_linebr)
plot(stopPrice, "SL", color=color.red, style=plot.style_linebr, linewidth=2)
plot(target1, "TP1", color=color.teal, style=plot.style_linebr)
plot(target2, "TP2", color=color.aqua, style=plot.style_linebr)
plot(target3, "TP3", color=color.green, style=plot.style_linebr)
plotshape(longSignal, title="BUY", style=shape.labelup, location=location.belowbar, color=color.green, text="BUY", textcolor=color.white)
plotshape(shortSignal, title="SELL", style=shape.labeldown, location=location.abovebar, color=color.red, text="SELL", textcolor=color.white)

alertBuy = '{"action":"BUY","symbol":"' + syminfo.ticker + '","timeframe":"' + timeframe.period + '","entry":' + str.tostring(entryPrice, "#.##") + ',"sl":' + str.tostring(stopPrice, "#.##") + ',"tp1":' + str.tostring(target1, "#.##") + ',"tp2":' + str.tostring(target2, "#.##") + ',"tp3":' + str.tostring(target3, "#.##") + ',"rsi":' + str.tostring(rsiValue, "#.#") + ',"atr":' + str.tostring(atrValue, "#.##") + '}'
alertSell = '{"action":"SELL","symbol":"' + syminfo.ticker + '","timeframe":"' + timeframe.period + '","entry":' + str.tostring(entryPrice, "#.##") + ',"sl":' + str.tostring(stopPrice, "#.##") + ',"tp1":' + str.tostring(target1, "#.##") + ',"tp2":' + str.tostring(target2, "#.##") + ',"tp3":' + str.tostring(target3, "#.##") + ',"rsi":' + str.tostring(rsiValue, "#.#") + ',"atr":' + str.tostring(atrValue, "#.##") + '}'
if longSignal
    alert(alertBuy, alert.freq_once_per_bar_close)
if shortSignal
    alert(alertSell, alert.freq_once_per_bar_close)

alertcondition(longSignal, "BUY confirmed", "Confirmed BUY: use the dynamic JSON alert for Entry/SL/TP levels")
alertcondition(shortSignal, "SELL confirmed", "Confirmed SELL: use the dynamic JSON alert for Entry/SL/TP levels")
