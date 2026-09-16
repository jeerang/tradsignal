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
confirmBars = input.int(3, "Bars Allowed Between Signal 1 and 2", minval=1, maxval=10, group=groupTrend)

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
boxExtendBars = input.int(20, "Entry/TP/SL Box Width (Bars)", minval=5, maxval=100, group=groupRisk)

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

buy1Signal = confirmedBar and sessionAllowed and strategy.position_size == 0 and trendUp and longConfirmation and trendStrengthOk
sell1Signal = confirmedBar and sessionAllowed and strategy.position_size == 0 and trendDown and shortConfirmation and trendStrengthOk

var int pendingDirection = 0
var int pendingBar = na
var float pendingEntry = na
var float pendingStop = na
var float pendingRisk = na

if buy1Signal
    pendingDirection := 1
    pendingBar := bar_index
    pendingEntry := close
    pendingStop := longStop
    pendingRisk := longRisk

if sell1Signal
    pendingDirection := -1
    pendingBar := bar_index
    pendingEntry := close
    pendingStop := shortStop
    pendingRisk := shortRisk

pendingIsFresh = pendingDirection != 0 and not na(pendingBar) and bar_index - pendingBar <= confirmBars
buy2Signal = confirmedBar and pendingIsFresh and pendingDirection == 1 and strategy.position_size == 0 and trendUp and close > pendingEntry and close > open and rsiValue >= minimumRsiLong and longRiskOk
sell2Signal = confirmedBar and pendingIsFresh and pendingDirection == -1 and strategy.position_size == 0 and trendDown and close < pendingEntry and close < open and rsiValue <= maximumRsiShort and shortRiskOk

if not pendingIsFresh
    pendingDirection := 0
    pendingBar := na
    pendingEntry := na
    pendingStop := na
    pendingRisk := na

var float entryPrice = na
var float stopPrice = na
var float riskDistance = na
var float target1 = na
var float target2 = na
var float target3 = na
var float entryAtr = na
var int tradeDirection = 0
var bool tp1Reached = false
var box riskBox = na
var box rewardBox = na
var label entryLabel = na
var label stopLabel = na
var label targetLabel = na

if buy2Signal
    entryPrice := close
    stopPrice := math.min(pendingStop, close - atrValue * minimumStopAtr)
    riskDistance := entryPrice - stopPrice
    target1 := entryPrice + riskDistance * tp1R
    target2 := entryPrice + riskDistance * tp2R
    target3 := entryPrice + riskDistance * tp3R
    entryAtr := atrValue
    tradeDirection := 1
    tp1Reached := false
    strategy.entry("BUY", strategy.long)
    box.delete(riskBox)
    box.delete(rewardBox)
    label.delete(entryLabel)
    label.delete(stopLabel)
    label.delete(targetLabel)
    riskBox := box.new(bar_index, entryPrice, bar_index + boxExtendBars, stopPrice, bgcolor=color.new(color.red, 86), border_color=color.new(color.red, 35))
    rewardBox := box.new(bar_index, target3, bar_index + boxExtendBars, entryPrice, bgcolor=color.new(color.green, 88), border_color=color.new(color.green, 35))
    entryLabel := label.new(bar_index + boxExtendBars, entryPrice, "Entry " + str.tostring(entryPrice, "#.##"), style=label.style_label_left, color=color.yellow, textcolor=color.black)
    stopLabel := label.new(bar_index + boxExtendBars, stopPrice, "SL " + str.tostring(stopPrice, "#.##"), style=label.style_label_left, color=color.red, textcolor=color.white)
    targetLabel := label.new(bar_index + boxExtendBars, target3, "TP3 " + str.tostring(target3, "#.##"), style=label.style_label_left, color=color.green, textcolor=color.white)
    pendingDirection := 0
    pendingBar := na

if sell2Signal
    entryPrice := close
    stopPrice := math.max(pendingStop, close + atrValue * minimumStopAtr)
    riskDistance := stopPrice - entryPrice
    target1 := entryPrice - riskDistance * tp1R
    target2 := entryPrice - riskDistance * tp2R
    target3 := entryPrice - riskDistance * tp3R
    entryAtr := atrValue
    tradeDirection := -1
    tp1Reached := false
    strategy.entry("SELL", strategy.short)
    box.delete(riskBox)
    box.delete(rewardBox)
    label.delete(entryLabel)
    label.delete(stopLabel)
    label.delete(targetLabel)
    riskBox := box.new(bar_index, stopPrice, bar_index + boxExtendBars, entryPrice, bgcolor=color.new(color.red, 86), border_color=color.new(color.red, 35))
    rewardBox := box.new(bar_index, entryPrice, bar_index + boxExtendBars, target3, bgcolor=color.new(color.green, 88), border_color=color.new(color.green, 35))
    entryLabel := label.new(bar_index + boxExtendBars, entryPrice, "Entry " + str.tostring(entryPrice, "#.##"), style=label.style_label_left, color=color.yellow, textcolor=color.black)
    stopLabel := label.new(bar_index + boxExtendBars, stopPrice, "SL " + str.tostring(stopPrice, "#.##"), style=label.style_label_left, color=color.red, textcolor=color.white)
    targetLabel := label.new(bar_index + boxExtendBars, target3, "TP3 " + str.tostring(target3, "#.##"), style=label.style_label_left, color=color.green, textcolor=color.white)
    pendingDirection := 0
    pendingBar := na

if strategy.position_size > 0 and tradeDirection == 1
    if high >= target1
        tp1Reached := true
    if useTrailing and tp1Reached
        stopPrice := math.max(stopPrice, high - entryAtr * trailingAtr)
    box.set_bottom(riskBox, stopPrice)
    box.set_right(riskBox, bar_index + boxExtendBars)
    box.set_right(rewardBox, bar_index + boxExtendBars)
    label.set_xy(stopLabel, bar_index + boxExtendBars, stopPrice)
    label.set_text(stopLabel, "SL " + str.tostring(stopPrice, "#.##"))
    strategy.exit("BUY-TP1", "BUY", limit=target1, stop=stopPrice, qty_percent=33)
    strategy.exit("BUY-TP2", "BUY", limit=target2, stop=stopPrice, qty_percent=33)
    strategy.exit("BUY-TP3", "BUY", limit=target3, stop=stopPrice, qty_percent=34)

if strategy.position_size < 0 and tradeDirection == -1
    if low <= target1
        tp1Reached := true
    if useTrailing and tp1Reached
        stopPrice := math.min(stopPrice, low + entryAtr * trailingAtr)
    box.set_top(riskBox, stopPrice)
    box.set_right(riskBox, bar_index + boxExtendBars)
    box.set_right(rewardBox, bar_index + boxExtendBars)
    label.set_xy(stopLabel, bar_index + boxExtendBars, stopPrice)
    label.set_text(stopLabel, "SL " + str.tostring(stopPrice, "#.##"))
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
plotshape(buy1Signal, title="BUY 1", style=shape.labelup, location=location.belowbar, color=color.new(color.green, 45), text="BUY 1", textcolor=color.white, size=size.tiny)
plotshape(sell1Signal, title="SELL 1", style=shape.labeldown, location=location.abovebar, color=color.new(color.red, 45), text="SELL 1", textcolor=color.white, size=size.tiny)
plotshape(buy2Signal, title="BUY 2", style=shape.labelup, location=location.belowbar, color=color.green, text="BUY 2", textcolor=color.white, size=size.small)
plotshape(sell2Signal, title="SELL 2", style=shape.labeldown, location=location.abovebar, color=color.red, text="SELL 2", textcolor=color.white, size=size.small)

alertBuy = '{"action":"BUY","symbol":"' + syminfo.ticker + '","timeframe":"' + timeframe.period + '","entry":' + str.tostring(entryPrice, "#.##") + ',"sl":' + str.tostring(stopPrice, "#.##") + ',"tp1":' + str.tostring(target1, "#.##") + ',"tp2":' + str.tostring(target2, "#.##") + ',"tp3":' + str.tostring(target3, "#.##") + ',"rsi":' + str.tostring(rsiValue, "#.#") + ',"atr":' + str.tostring(atrValue, "#.##") + '}'
alertSell = '{"action":"SELL","symbol":"' + syminfo.ticker + '","timeframe":"' + timeframe.period + '","entry":' + str.tostring(entryPrice, "#.##") + ',"sl":' + str.tostring(stopPrice, "#.##") + ',"tp1":' + str.tostring(target1, "#.##") + ',"tp2":' + str.tostring(target2, "#.##") + ',"tp3":' + str.tostring(target3, "#.##") + ',"rsi":' + str.tostring(rsiValue, "#.#") + ',"atr":' + str.tostring(atrValue, "#.##") + '}'
if buy2Signal
    alert(alertBuy, alert.freq_once_per_bar_close)
if sell2Signal
    alert(alertSell, alert.freq_once_per_bar_close)

alertcondition(buy1Signal, "BUY 1 watch", "BUY 1 watch signal: wait for BUY 2 confirmation")
alertcondition(sell1Signal, "SELL 1 watch", "SELL 1 watch signal: wait for SELL 2 confirmation")
alertcondition(buy2Signal, "BUY 2 confirmed", "BUY 2 confirmed: use the dynamic JSON alert for Entry/SL/TP levels")
alertcondition(sell2Signal, "SELL 2 confirmed", "SELL 2 confirmed: use the dynamic JSON alert for Entry/SL/TP levels")
