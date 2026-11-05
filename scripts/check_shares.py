"""
TP 계산 전제 점검: 리포트가 쓴 주식수·자본으로 만든 BPS가 시장 데이터와 맞는지 확인한다.
(액면분할·무상증자·자사주 소각·우선주 누락처럼 주식수가 틀리면 적정주가 전체가 같은 배수로 틀어진다)

- 국내: 네이버 증권 종목 메인의 상장주식수, PBR, BPS
- 미국: Yahoo Finance(yfinance)의 sharesOutstanding, bookValue
- 결과는 로그로만 출력한다(파일 저장·커밋 없음).
"""
import re
import requests
from bs4 import BeautifulSoup

# 리포트(10/20 종합 리포트 등)에 적힌 값: 발행주식수, 자본총계, 기준
REPORT = {
    "071050": ("한국금융지주", 52_738_513, 12_099_491_000_000),
    "000660": ("SK하이닉스", 711_075_500, 120_666_751_000_000),
    "005930": ("삼성전자", 5_764_191_903, 436_320_337_000_000),
    "316140": ("우리금융지주", 728_035_737, 37_859_248_000_000),
    "483650": ("달바글로벌", 12_392_665, 198_554_792_679),
    "086450": ("동국제약", 45_110_727, 763_738_526_426),
    "010120": ("LS ELECTRIC", None, None),
}
US = {"UBER": ("UBER", 2_042_560_121, 27_041_000_000)}

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Referer": "https://finance.naver.com/"}


def num(s):
    s = re.sub(r"[^\d.\-]", "", s or "")
    return float(s) if s not in ("", "-", ".") else None


def naver(code):
    r = requests.get(f"https://finance.naver.com/item/main.naver?code={code}", headers=H, timeout=15)
    r.encoding = "euc-kr"
    soup = BeautifulSoup(r.text, "html.parser")
    out = {}
    for th in soup.select("table th"):
        t = th.get_text(" ", strip=True)
        td = th.find_next_sibling("td")
        if not td:
            continue
        v = td.get_text(" ", strip=True)
        if t.startswith("상장주식수"):
            out["listed"] = num(v)
        if "PBR" in t and "BPS" in t:
            parts = [num(x) for x in re.split(r"배|l|\|", v) if num(x) is not None]
            if len(parts) >= 2:
                out["pbr"], out["bps"] = parts[0], parts[1]
        if t.startswith("액면가"):
            out["par"] = v
    pr = soup.select_one("p.no_today .blind")
    out["price"] = num(pr.get_text()) if pr else None
    return out


def row(name, code, rs, req, mkt_sh, mkt_bps, price, note=""):
    rbps = req / rs if rs and req else None
    sh_gap = (rs / mkt_sh - 1) * 100 if rs and mkt_sh else None
    bps_gap = (rbps / mkt_bps - 1) * 100 if rbps and mkt_bps else None
    f = lambda v, d=0: "-" if v is None else f"{v:,.{d}f}"
    flag = ""
    if bps_gap is not None and abs(bps_gap) >= 15:
        flag = "⚠ BPS 차이 큼"
    if sh_gap is not None and abs(sh_gap) >= 15:
        flag = "⚠⚠ 주식수 차이 큼"
    print(f"{name}({code}) | 리포트주식수 {f(rs)} | 시장주식수 {f(mkt_sh)} ({f(sh_gap,1)}%) | 리포트BPS {f(rbps)} | 시장BPS {f(mkt_bps, 2 if mkt_bps and mkt_bps < 1000 else 0)} ({f(bps_gap,1)}%) | 현재가 {f(price, 2 if price and price < 1000 else 0)} {note} {flag}")


def main():
    print("== 국내 (네이버 증권) ==")
    for code, (name, rs, req) in REPORT.items():
        try:
            n = naver(code)
        except Exception as e:  # noqa: BLE001
            print(f"{name}({code}) 실패: {e}")
            continue
        row(name, code, rs, req, n.get("listed"), n.get("bps"), n.get("price"), f"| 액면가 {n.get('par')} | PBR {n.get('pbr')}")
    print("== 미국 (Yahoo) ==")
    try:
        import yfinance as yf
        for code, (name, rs, req) in US.items():
            i = yf.Ticker(code).info
            row(name, code, rs, req, i.get("sharesOutstanding"), i.get("bookValue"), i.get("currentPrice"), f"| P/B {i.get('priceToBook')}")
            print("  splits(최근):", list(yf.Ticker(code).splits.tail(3).items()))
    except Exception as e:  # noqa: BLE001
        print("UBER 실패:", e)
    print("== 최근 5년 액면분할/병합 (Yahoo splits) ==")
    try:
        import yfinance as yf
        for code in REPORT:
            for sfx in (".KS", ".KQ"):
                s = yf.Ticker(code + sfx).splits
                if s is not None and len(s):
                    print(code, [(d.strftime('%Y-%m-%d'), r) for d, r in s.items()][-3:])
                    break
            else:
                print(code, "분할 기록 없음")
    except Exception as e:  # noqa: BLE001
        print("splits 실패:", e)


if __name__ == "__main__":
    main()
