"""
재점검 신호용 일별 종가 이력(history.json)을 만든다.

- 대상: hypotheses.json에 있는 종목 + 각 종목의 벤치마크(KOSPI=^KS11, SPX=^GSPC)
- yfinance로 최근 3개월 일봉을 받아 최근 40거래일만 저장한다(매 실행마다 새로 받아 덮어씀 → 누락·중복 없음)
- 종목별로 벤치마크 대비 상대수익률을 계산해 rel에 저장한다.
    daily : 오늘 등락률 − 벤치마크 오늘 등락률 (%p)
    d20   : 최근 20거래일 수익률 − 벤치마크 같은 기간 수익률 (%p)
"""

import json
import datetime
import yfinance as yf

HYP_JSON = "hypotheses.json"
OUT_JSON = "history.json"
KEEP = 40
WINDOW = 20
BENCH = {"KOSPI": "^KS11", "SPX": "^GSPC"}


def closes(ticker: str) -> list:
    df = yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError("빈 데이터")
    out = []
    for idx, row in df.iterrows():
        c = row.get("Close")
        if c is None or c != c:  # NaN
            continue
        out.append([idx.strftime("%Y-%m-%d"), round(float(c), 2)])
    return out[-KEEP:]


def domestic(code: str) -> list:
    last = None
    for sfx in (".KS", ".KQ"):
        try:
            return closes(code + sfx)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"{code}: {last}")


def rel(stock: list, bench: list) -> dict:
    """같은 날짜만 맞춰서 상대수익률 계산"""
    bmap = dict(bench)
    pairs = [(d, c, bmap[d]) for d, c in stock if d in bmap]
    if len(pairs) < 2:
        return {}
    out = {"asof": pairs[-1][0]}
    s1, b1 = pairs[-1][1], pairs[-1][2]
    s0, b0 = pairs[-2][1], pairs[-2][2]
    out["daily"] = round(((s1 / s0) - (b1 / b0)) * 100, 2)
    if len(pairs) > WINDOW:
        d0, sw, bw = pairs[-1 - WINDOW]
        out["from"] = d0
        out["ret20"] = round((s1 / sw - 1) * 100, 2)
        out["bench20"] = round((b1 / bw - 1) * 100, 2)
        out["d20"] = round(out["ret20"] - out["bench20"], 2)
    return out


def main():
    with open(HYP_JSON, encoding="utf-8") as f:
        hyp = json.load(f)

    series, rels = {}, {}
    for label, t in BENCH.items():
        try:
            series[label] = closes(t)
        except Exception as e:  # noqa: BLE001
            print(f"[경고] 지수 {label} 실패: {e}")

    for s in hyp.get("stocks", []):
        code = s["code"]
        try:
            series[code] = closes(code) if s.get("currency") == "USD" else domestic(code)
        except Exception as e:  # noqa: BLE001
            print(f"[경고] {code} 실패: {e}")
            continue
        b = s.get("benchmark") or ("SPX" if s.get("currency") == "USD" else "KOSPI")
        if b in series:
            r = rel(series[code], series[b])
            if r:
                r["benchmark"] = b
                rels[code] = r

    out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window": WINDOW,
        "note": "daily=오늘 등락률-벤치마크(%p), d20=최근 20거래일 수익률-벤치마크(%p). 종가는 Yahoo Finance 일봉.",
        "rel": rels,
        "series": series,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(rels, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
