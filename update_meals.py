"""
주간 식단표(meals.json) 갱신 스크립트
국가공무원인재개발원(NHI) "주간식단" 게시판에서 최신 PDF를 받아 파싱하거나,
사람이 직접 받아둔 PDF 파일을 파싱해 meals.json을 갱신합니다.

사용법:
    # 1) 자동: NHI 사이트에서 최신 주간식단 PDF를 받아서 갱신 시도
    python update_meals.py

    # 2) 수동: 직접 받아둔 PDF 파일로 갱신
    python update_meals.py --pdf "주간식단계획(6.8~6.12).pdf"

    # 3) 추출된 표만 확인하고 meals.json은 건드리지 않음 (구조 확인/디버그용)
    python update_meals.py --pdf "주간식단계획(6.8~6.12).pdf" --dry-run

주의:
    NHI 사이트는 자동 다운로드를 차단하는 경우가 많습니다(400 Bad Request).
    이 경우 --pdf 옵션으로 직접 받아둔 PDF를 넘겨 사용하세요.
    PDF의 표 형식이 예상과 다르면 --dry-run으로 추출된 표를 확인한 뒤
    parse_table_to_meals() 의 매칭 로직을 PDF 형식에 맞게 조정해야 합니다.
"""

import argparse
import json
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

MEALS_PATH = os.path.join(os.path.dirname(__file__), "meals.json")
LIST_URL = "https://www.nhi.go.kr/Introduce/introduce7/week/List.htm"
READ_URL = "https://www.nhi.go.kr/Introduce/introduce7/week/Read.htm"
DOWN_URL = "https://www.nhi.go.kr/cmm/fms/asaproFileDown.do"

MEAL_ROW_KEYWORDS = {
    "breakfast": ["조식", "아침"],
    "lunch": ["중식", "점심"],
    "dinner": ["석식", "저녁"],
}

# "6.8(월)" / "6/8 (월)" / "06.08" 등의 날짜 표기를 인식
DATE_HEADER_PATTERN = re.compile(r"(\d{1,2})\s*[./]\s*(\d{1,2})")


def load_meals():
    if not os.path.exists(MEALS_PATH):
        return {}
    with open(MEALS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_meals(meals):
    with open(MEALS_PATH, "w", encoding="utf-8") as f:
        json.dump(meals, f, ensure_ascii=False, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# 1) NHI 사이트에서 최신 주간식단 PDF 자동 다운로드 (best-effort)
# ---------------------------------------------------------------------------

def fetch_latest_pdf():
    """최신 '주간식단' 게시글의 PDF를 받아 (파일명, bytes)를 반환. 실패 시 예외 발생."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    })

    res = session.get(LIST_URL, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    ntt_id = None
    for a in soup.select("a[href*='fn_GoRead'], a[onclick*='fn_GoRead']"):
        onclick = a.get("href") or a.get("onclick") or ""
        m = re.search(r"fn_GoRead\('(\d+)'", onclick)
        if m:
            ntt_id = m.group(1)
            break
    if not ntt_id:
        raise RuntimeError("게시글 목록에서 최신 글의 ntt_id를 찾지 못했습니다.")

    read_res = session.get(READ_URL, params={"ntt_id": ntt_id},
                            headers={"Referer": LIST_URL}, timeout=15)
    read_res.raise_for_status()
    read_soup = BeautifulSoup(read_res.text, "html.parser")

    file_id = file_sn = None
    m = re.search(r"fn_egov_downFile\('([^']+)'\s*,\s*'(\d+)'\)", read_res.text)
    if m:
        file_id, file_sn = m.group(1), m.group(2)
    if not file_id:
        raise RuntimeError("게시글에서 첨부파일 ID를 찾지 못했습니다.")

    title_text = read_soup.get_text("\n", strip=True)
    filename_match = re.search(r"[^\s]+\.pdf", title_text)
    filename = filename_match.group(0) if filename_match else f"{ntt_id}.pdf"

    down_res = session.get(
        DOWN_URL,
        params={"atchFileId": file_id, "fileSn": file_sn, "browser": "chrome", "gubum": ""},
        headers={"Referer": f"{READ_URL}?ntt_id={ntt_id}"},
        timeout=20,
    )
    down_res.raise_for_status()
    if down_res.headers.get("Content-Type", "").startswith("text/html"):
        raise RuntimeError("첨부파일 다운로드가 차단되었습니다(HTML 응답). --pdf 옵션으로 수동 파싱하세요.")

    return filename, down_res.content


# ---------------------------------------------------------------------------
# 2) PDF 표 파싱 -> meals.json 형식
# ---------------------------------------------------------------------------

def extract_table(pdf_path):
    """PDF에서 가장 큰(셀 수가 많은) 표를 추출."""
    import pdfplumber

    best_table = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if best_table is None or len(table) * len(table[0]) > len(best_table) * len(best_table[0]):
                    best_table = table
    if not best_table:
        raise RuntimeError("PDF에서 표를 찾지 못했습니다.")
    return best_table


def parse_table_to_meals(table, year):
    """표(2차원 리스트)를 {YYYY-MM-DD: {breakfast, lunch, dinner}} 형태로 변환.

    실제 NHI 주간식단 PDF의 표 형식 (날짜가 행, 끼니가 열):
        헤더 행: ["2026", "아 침", "점 심", "저 녁"]
        이후 행: ["6/15\n(월)", "...아침메뉴...", "...점심메뉴...", "...저녁메뉴..."]
                 ["6/16\n(화)", ...]
                 ...

    PDF 형식이 다르면 이 함수를 PDF 구조에 맞게 수정하세요.
    """
    header = table[0]
    meal_cols = {}  # column index -> "breakfast" / "lunch" / "dinner"
    for idx, cell in enumerate(header):
        if not cell:
            continue
        cell_norm = cell.replace(" ", "").replace("\n", "")
        for key, keywords in MEAL_ROW_KEYWORDS.items():
            if any(kw.replace(" ", "") in cell_norm for kw in keywords):
                meal_cols[idx] = key
                break

    if not meal_cols:
        raise RuntimeError("표 헤더에서 아침/점심/저녁 열을 찾지 못했습니다. 표 형식을 확인하세요.")

    meals = {}
    for row in table[1:]:
        if not row or not row[0]:
            continue
        m = DATE_HEADER_PATTERN.search(row[0].replace("\n", " "))
        if not m:
            continue
        month, day = int(m.group(1)), int(m.group(2))
        try:
            date_obj = datetime(year, month, day).date()
        except ValueError:
            continue
        date_key = date_obj.strftime("%Y-%m-%d")

        for idx, meal_key in meal_cols.items():
            if idx >= len(row) or not row[idx]:
                continue
            cell_text = row[idx].strip()
            if "잔반" in cell_text or cell_text.startswith("※"):
                continue
            menu_text = re.sub(r"\n+", ", ", cell_text)
            menu_text = re.sub(r"\s{2,}", " ", menu_text)
            menu_text = re.sub(r",?\s*\(\d+\)\s*$", "", menu_text)  # 끝의 칼로리 표기 제거
            if not menu_text:
                continue
            meals.setdefault(date_key, {})[meal_key] = menu_text

    if not meals:
        raise RuntimeError("표에서 식단 데이터를 추출하지 못했습니다. 표 형식을 확인하세요.")

    return meals


def update_from_pdf(pdf_path, year=None):
    if year is None:
        year = datetime.now().year
    table = extract_table(pdf_path)
    new_meals = parse_table_to_meals(table, year)

    meals = load_meals()
    meals.update(new_meals)
    save_meals(meals)
    return new_meals


# ---------------------------------------------------------------------------
# 자동 갱신 (스케줄러 / /admin/update-meals 에서 호출)
# ---------------------------------------------------------------------------

def auto_update():
    filename, content = fetch_latest_pdf()
    tmp_path = os.path.join(os.path.dirname(__file__), f"_tmp_{filename}")
    with open(tmp_path, "wb") as f:
        f.write(content)
    try:
        return update_from_pdf(tmp_path)
    finally:
        os.remove(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="주간 식단표(meals.json) 갱신")
    parser.add_argument("--pdf", help="수동으로 받아둔 식단표 PDF 경로")
    parser.add_argument("--year", type=int, help="표 날짜에 적용할 연도 (기본: 올해)")
    parser.add_argument("--dry-run", action="store_true", help="meals.json을 수정하지 않고 추출 결과만 출력")
    args = parser.parse_args()

    if args.pdf:
        if args.dry_run:
            table = extract_table(args.pdf)
            print("=== 추출된 표 ===")
            for row in table:
                print(row)
            print()
            new_meals = parse_table_to_meals(table, args.year or datetime.now().year)
            print("=== 파싱 결과 ===")
            print(json.dumps(new_meals, ensure_ascii=False, indent=2))
        else:
            new_meals = update_from_pdf(args.pdf, args.year)
            print(f"meals.json 갱신 완료: {len(new_meals)}개 날짜")
            for date_key in sorted(new_meals):
                print(f"  - {date_key}")
    else:
        print("NHI 사이트에서 최신 식단 PDF 자동 다운로드 시도...")
        try:
            new_meals = auto_update()
            print(f"meals.json 갱신 완료: {len(new_meals)}개 날짜")
            for date_key in sorted(new_meals):
                print(f"  - {date_key}")
        except Exception as e:
            print(f"자동 다운로드 실패: {e}")
            print("PDF를 직접 받아서 `python update_meals.py --pdf <파일경로>` 로 실행하세요.")


if __name__ == "__main__":
    main()
