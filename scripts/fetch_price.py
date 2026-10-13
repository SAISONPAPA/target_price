"""
국내 종목 + 국내 지수(KOSPI/KOSDAQ) 현재가를 가져와 price.json에 병합한다.

1순위: 네이버 금융 크롤링 (API 키/계좌 불필요, 페이지 구조가 바뀌거나 차단되면 실패 가능)
2순위: Yahoo Finance(yfinance) 폴백 — 네이버가 막히거나 깨져도 가격이 멈추지 않도록 함
       (국내 종목은 005930.KS / 코스닥은 .KQ 형태, 지수는 ^KS11 / ^KQ11)

어느 쪽으로 가져왔는지는 각 항목의 "src" 필드에 기록되고,
국내 데이터의 마지막 성공 시각은 최상위 "domestic_updated_at"에 기록된다.
(updated_at은 해외 스크립트도 갱신하므로, 국내 데이터가 멈췄는지는 domestic_updated_at으로 확인)
"""

import json
import datetime
import requests
from bs4 import BeautifulSoup

# 여러 종목을 관리하고 싶으면 이 리스트에 추가하면 됨
# (해외주식/해외ETF는 scripts/fetch_price_overseas.py에서 따로 처리)
STOCKS = [
    {"code": "000660", "name": "SK하이닉스"},
    {"code": "003230", "name": "삼양식품"},
    {"code": "010120", "name": "LS ELECTRIC"},
    {"code": "071050", "name": "한국금융지주"},
    {"code": "316140", "name": "우리금융지주"},
    {"code": "005930", "name": "삼성전자"},
    {"code": "086450", "name": "동국제약"},
    {"code": "483650", "name": "달바글로벌"},
    {"code": "003490", "name": "대한항공"},
    {"code": "016360", "name": "삼성증권"},
    {"code": "360750", "name": "TIGER 미국S&P500"},
    {"code": "418660", "name": "TIGER 미국나스닥100레버리지"},
    {"code": "133690", "name": "TIGER 미국나스닥100"},
]

# 국내 지수: label -> (네이버 지수 코드, yahoo 티커)
INDEX_CODES = {
    "KOSPI": ("KOSPI", "^KS11"),
    "KOSDAQ": ("KOSDAQ", "^KQ11"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PRICE_JSON = "price.json"


# ---------------------------------------------------------------- Naver
def _parse_today_block(soup: BeautifulSoup):
    """p.no_today / p.no_exday 구조(네이버 공통 컴포넌트)를 파싱해서
    (price, change, change_rate) 튜플로 반환한다."""
    today = soup.select_one("p.no_today")
    if today is None:
        raise RuntimeError("가격 영역(p.no_today)을 찾지 못함 — 페이지 구조 변경 또는 차단 가능성")

    price = float(today.select_one("span.blind").text.replace(",", ""))

    exday = soup.select_one("p.no_exday")
    blinds = exday.select("span.blind") if exday else []
    change = float(blinds[0].text.replace(",", "")) if len(blinds) > 0 else 0.0
    change_rate = float(blinds[1].text.replace(",", "")) if len(blinds) > 1 else 0.0

    em = today.select_one("em")
    classes = (em.get("class") or []) if em else []
    if "no_down" in classes:
        change = -abs(change)
        change_rate = -abs(change_rate)
    else:
        change = abs(change)
        change_rate = abs(change_rate)

    return price, change, change_rate


def fetch_stock_naver(code: str) -> dict:
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    price, change, change_rate = _parse_today_block(soup)
    return {
        "price": int(price),
        "change": int(change),
        "change_rate": change_rate,
    }


def fetch_index_naver(index_code: str) -> dict:
    """코스피/코스닥 등 지수 조회.
    실시간 지수 페이지(sise_index.naver)는 DOM 구조가 자주 바뀌어서,
    더 안정적인 일별시세 테이블(sise_index_day.naver)의 최신 행을 읽는 방식으로 처리한다.
    테이블 컬럼 순서: 날짜, 종가, 전일비, 등락률, 거래량, 거래대금
    """
    url = f"https://finance.naver.com/sise/sise_index_day.naver?code={index_code}"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.find("table", class_="type_1")
    if table is None:
        raise RuntimeError(f"[{index_code}] 지수 테이블(table.type_1)을 찾지 못함 — 페이지 구조 변경 또는 차단 가능성")

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) != 6:
            continue  # 헤더/빈 행 등은 건너뜀

        price = float(cols[1].get_text(strip=True).replace(",", ""))
        diff = float(cols[2].get_text(strip=True).replace(",", "") or 0)
        rate = float(cols[3].get_text(strip=True).replace("%", "").replace(",", "") or 0)

        # 상승/하락 아이콘으로 부호 판별 (전일비/등락률 칸에 이미지로 표시됨)
        img = cols[2].find("img")
        is_down = False
        if img:
            alt = img.get("alt", "")
            src = img.get("src", "")
            if "하락" in alt or "dn" in src or "down" in src:
                is_down = True

        if is_down:
            diff, rate = -abs(diff), -abs(rate)
        else:
            diff, rate = abs(diff), abs(rate)

        return {"price": price, "change": diff, "change_rate": rate}

    raise RuntimeError(f"[{index_code}] 데이터 행을 찾지 못함")


# ---------------------------------------------------------------- Yahoo (fallback)
def _yahoo_quote(ticker: str) -> dict:
    import yfinance as yf  # 워크플로우에서 이미 설치됨 (해외 스크립트와 동일)

    info = yf.Ticker(ticker).fast_info
    price = float(info["last_price"])
    prev_close = float(info["previous_close"])
    if not (price > 0 and prev_close > 0):
        raise RuntimeError(f"{ticker}: 유효하지 않은 시세 (price={price}, prev={prev_close})")
    change = price - prev_close
    change_rate = (change / prev_close) * 100
    return {"price": price, "change": change, "change_rate": round(change_rate, 2)}


def fetch_stock_yahoo(code: str) -> dict:
    """코스피(.KS) → 코스닥(.KQ) 순서로 시도"""
    last_err = None
    for suffix in (".KS", ".KQ"):
        try:
            q = _yahoo_quote(code + suffix)
            return {
                "price": int(round(q["price"])),
                "change": int(round(q["change"])),
                "change_rate": q["change_rate"],
            }
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"yahoo 조회 실패({code}): {last_err}")


def fetch_index_yahoo(ticker: str) -> dict:
    q = _yahoo_quote(ticker)
    return {
        "price": round(q["price"], 2),
        "change": round(q["change"], 2),
        "change_rate": q["change_rate"],
    }


# ---------------------------------------------------------------- main
def main():
    try:
        with open(PRICE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    data.setdefault("stocks", {})
    data.setdefault("indices", {})

    ok_naver = ok_yahoo = failed = 0

    for stock in STOCKS:
        code, name = stock["code"], stock["name"]
        result, src = None, None

        try:
            result, src = fetch_stock_naver(code), "naver"
            ok_naver += 1
        except Exception as e:  # noqa: BLE001
            print(f"[경고] 네이버 {code}({name}) 실패: {type(e).__name__}: {e}")
            try:
                result, src = fetch_stock_yahoo(code), "yahoo"
                ok_yahoo += 1
                print(f"[폴백] {code}({name}) → Yahoo 사용")
            except Exception as e2:  # noqa: BLE001
                failed += 1
                print(f"[경고] Yahoo {code}({name}) 도 실패: {type(e2).__name__}: {e2}")
                continue

        data["stocks"][code] = {"name": name, **result, "src": src}

    for label, (naver_code, yahoo_ticker) in INDEX_CODES.items():
        result, src = None, None
        try:
            result, src = fetch_index_naver(naver_code), "naver"
        except Exception as e:  # noqa: BLE001
            print(f"[경고] 네이버 지수 {label} 실패: {type(e).__name__}: {e}")
            try:
                result, src = fetch_index_yahoo(yahoo_ticker), "yahoo"
                print(f"[폴백] 지수 {label} → Yahoo 사용")
            except Exception as e2:  # noqa: BLE001
                print(f"[경고] Yahoo 지수 {label} 도 실패: {type(e2).__name__}: {e2}")
                continue
        data["indices"][label] = {**result, "src": src}

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["updated_at"] = now
    if ok_naver + ok_yahoo > 0:
        data["domestic_updated_at"] = now

    with open(PRICE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[요약] 국내종목 성공: 네이버 {ok_naver} / 야후 {ok_yahoo} / 실패 {failed} (총 {len(STOCKS)})")


if __name__ == "__main__":
    main()
