"""
자산배분 시뮬레이션용 일봉 데이터 (수동 실행, 결과는 워크플로 아티팩트로만 남김)
- ^NDX: 가격지수(고점·낙폭 판단용)
- QQQ, SPY, SCHD, BRK-B: 배당 재투자 반영 종가(auto_adjust) — 매매·평가용
"""
import json
import yfinance as yf

OUT = {}
for t, adj in [("^NDX", False), ("QQQ", True), ("SPY", True), ("SCHD", True), ("BRK-B", True)]:
    df = yf.Ticker(t).history(period="max", interval="1d", auto_adjust=adj)
    s = df["Close"].dropna()
    OUT[t] = [[d.strftime("%Y-%m-%d"), round(float(v), 4)] for d, v in s.items()]
    print(t, len(OUT[t]), OUT[t][0], OUT[t][-1])
with open("sim_prices.json", "w") as f:
    json.dump(OUT, f)
