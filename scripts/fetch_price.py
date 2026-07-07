"""
네이버 금융 페이지를 크롤링해서 국내 종목 + 국내 지수(KOSPI/KOSDAQ) 현재가를
가져와 price.json에 병합한다.
API 키/계좌 없이 동작하지만, 네이버가 페이지 구조를 바꾸면 깨질 수 있다.
(참고: 비공식 방식이므로 너무 잦은 호출은 피할 것 — 이 repo는 10분 간격 사용중)
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
    {"code": "003490", "name": "대한항공"},
    {"code": "016360", "name": "삼성증권"},
    {"code": "360750", "name": "TIGER 미국S&P500"},
    {"code": "418660", "name": "TIGER 미국나스닥100레버리지"},
    {"code": "133690", "name": "TIGER 미국나스닥100"},
]

# 국내 지수 (코드는 네이버 지수 페이지 기준)
INDEX_CODES = {
    "KOSPI": "KOSPI",
    "KOSDAQ": "KOSDAQ",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

PRICE_JSON = "price.json"


def _parse_today_block(soup: BeautifulSoup):
    """p.no_today / p.no_exday 구조(네이버 공통 컴포넌트)를 파싱해서
    (price, change, change_rate) 튜플로 반환한다."""
    today = soup.select_one("p.no_today")
    if today is None:
        raise RuntimeError("가격 영역(p.no_today)을 찾지 못함 — 페이지 구조 변경 가능성")

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


def fetch_stock(code: str) -> dict:
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


def fetch_index(index_code: str) -> dict:
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
        raise RuntimeError(f"[{index_code}] 지수 테이블(table.type_1)을 찾지 못함 — 페이지 구조 변경 가능성")

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


def main():
    try:
        with open(PRICE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    data.setdefault("stocks", {})
    data.setdefault("indices", {})

    for stock in STOCKS:
        try:
            result = fetch_stock(stock["code"])
        except Exception as e:
            print(f"[경고] {stock['code']}({stock['name']}) 조회 실패: {e}")
            continue
        data["stocks"][stock["code"]] = {"name": stock["name"], **result}

    for label, index_code in INDEX_CODES.items():
        try:
            result = fetch_index(index_code)
        except Exception as e:
            print(f"[경고] 지수 {label} 조회 실패: {e}")
            continue
        data["indices"][label] = result

    data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with open(PRICE_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
