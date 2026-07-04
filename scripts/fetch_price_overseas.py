"""
해외종목(미국 상장) 현재가를 yfinance로 가져와 price.json에 병합한다.
scripts/fetch_price.py(네이버, 국내종목)를 먼저 실행해 기본 price.json을 만든 뒤
이 스크립트를 실행해서 해외종목 데이터를 같은 파일에 합치는 순서로 사용한다.
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
        data = {"updated_at": "", "stocks": {}}

    data.setdefault("stocks", {})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for code, yf_ticker in TICKERS.items():
        try:
            result = fetch_one(yf_ticker)
        except Exception as e:
            print(f"[경고] {code}({yf_ticker}) 조회 실패: {e}")
            continue
        data["stocks"][code] = {**data["stocks"].get(code, {}), **result, "currency": "USD"}

    data["updated_at"] = now

    with open(PRICE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
