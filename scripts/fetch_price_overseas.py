"""
해외종목(미국 상장) + 미국 3대 지수(S&P500/NASDAQ/DOW) 현재가를
yfinance로 가져와 price.json에 병합한다.
scripts/fetch_price.py(네이버, 국내종목/지수)와 순서 상관없이 실행 가능 —
서로 읽고(load) 병합(merge)한 뒤 저장(save)하는 방식이라 덮어쓰지 않는다.
"""

import json
import datetime
import yfinance as yf

# STOCKS(index.html)의 code -> yfinance 티커 매핑
# BRK.B처럼 코드에 점(.)이 들어간 종목은 yfinance에서 하이픈(-)으로 표기해야 함
TICKERS = {
    "GOOGL": "GOOGL",
    "UBER": "UBER",
    "MSFT": "MSFT",
    "BRK.B": "BRK-B",
    "XOM": "XOM",
    "DRAM": "DRAM",
}

# 미국 3대 지수
INDEX_TICKERS = {
    "SPX": "^GSPC",     # S&P 500
    "NASDAQ": "^IXIC",  # 나스닥 종합지수
    "DJI": "^DJI",      # 다우존스 산업평균
}

PRICE_JSON = "price.json"


def fetch_one(yf_ticker: str) -> dict:
    ticker = yf.Ticker(yf_ticker)
    info = ticker.fast_info
    price = float(info["last_price"])
    prev_close = float(info["previous_close"])
    change = price - prev_close
    change_rate = (change / prev_close) * 100 if prev_close else 0.0
    return {
        "price": round(price, 2),
        "change": round(change, 2),
        "change_rate": round(change_rate, 2),
    }


def main():
    try:
        with open(PRICE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    data.setdefault("stocks", {})
    data.setdefault("indices", {})

    for code, yf_ticker in TICKERS.items():
        try:
            result = fetch_one(yf_ticker)
        except Exception as e:
            print(f"[경고] {code}({yf_ticker}) 조회 실패: {e}")
            continue
        data["stocks"][code] = {**data["stocks"].get(code, {}), **result, "currency": "USD"}

    for label, yf_ticker in INDEX_TICKERS.items():
        try:
            result = fetch_one(yf_ticker)
        except Exception as e:
            print(f"[경고] 지수 {label}({yf_ticker}) 조회 실패: {e}")
            continue
        data["indices"][label] = result

    data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(PRICE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
