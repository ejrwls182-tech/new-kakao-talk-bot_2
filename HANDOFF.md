# 신임관리자과정 웹앱 — 인수인계 문서 (새 노트북용)

이 문서 하나면 다른 노트북에서 그대로 이어서 작업할 수 있습니다.
**모든 코드는 이미 GitHub에 있고 Vercel에 자동 배포 중**이라, 새 노트북에서는 저장소만 받으면 됩니다.

---

## 1. 이게 뭔가요 (프로젝트 개요)

제71기 신임관리자과정 교육생용 **모바일 웹앱**입니다. 4개 탭:
- **강의** — 날짜별 강의 일정 + 오늘 마감 + 다가오는 마감(D-day)
- **식단** — 그날의 아침/점심/저녁 (하루/이번주 보기)
- **할일** — 이번 주 / 다음 주 제출·마감 일정
- **사다리** — 사다리타기 게임 (인원 2~20명, 당첨 수 설정, 리롤)

순수 정적 웹앱(서버 없음)이라 빠르고, 콜드스타트가 없습니다.

---

## 2. 어디에 있나요 (주소)

| 항목 | 주소 |
|---|---|
| 🌐 라이브 웹앱 | https://new-kakao-talk-bot-2.vercel.app |
| 📦 GitHub 저장소 | https://github.com/ejrwls182-tech/new-kakao-talk-bot_2 |
| ☁️ 배포 | Vercel (GitHub에 push하면 자동 재배포) |

- GitHub 계정: `ejrwls182-tech`
- Vercel: 같은 GitHub 계정으로 로그인

---

## 3. 파일 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 웹앱 전체 (HTML+CSS+JS 한 파일). 강의/식단/할일/사다리 모두 여기에 있음 |
| `schedule.json` | 날짜별 강의·일정 데이터 (2026-05-25 ~ 2026-09-11) |
| `meals.json` | 날짜별 아침/점심/저녁 식단 데이터 |
| `update_meals.py` | NHI 주간식단 PDF를 파싱해 `meals.json`을 갱신하는 스크립트 |
| `requirements.txt` | update_meals.py 실행에 필요한 파이썬 패키지 |
| `vercel.json` | Vercel 정적 배포 설정 |
| `app.py` | (구버전) Flask 서버 — 지금은 정적 배포라 **안 씀**. 무시해도 됨 |
| `README.md` | 원본 설명서 |

> 데이터 흐름: `index.html`이 브라우저에서 `schedule.json`·`meals.json`을 직접 읽어서 화면을 그립니다. "오늘 날짜"는 브라우저에서 한국시간으로 계산합니다.

---

## 4. 새 노트북 세팅 (3단계)

### (1) 필요한 것 설치
- **Git** (https://git-scm.com)
- **Python 3** (https://www.python.org) — 식단 PDF 갱신할 때만 필요
- (선택) **Claude Code** / Claude 데스크톱 앱

### (2) 저장소 받기
터미널에서:
```bash
git clone https://github.com/ejrwls182-tech/new-kakao-talk-bot_2.git
cd new-kakao-talk-bot_2
```

### (3) GitHub 푸시 권한 설정
새 노트북에서 `git push`를 하려면 인증이 필요합니다. 둘 중 하나:
- **방법 A (쉬움):** `gh` CLI 설치 후 `gh auth login` → 브라우저로 GitHub 로그인
- **방법 B:** GitHub에서 **Personal Access Token(PAT)** 발급
  - GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
  - 이 레포에 **Contents: Read and write** 권한
  - push할 때 비밀번호 대신 토큰 사용

> ⚠️ 이전 노트북에서 만든 토큰은 30일 후 만료됩니다. 새로 발급하는 게 안전합니다.

---

## 5. 매주 반복 작업 — 식단 업데이트 ⭐

NHI는 매주 월요일 오전 "주간식단" 게시판에 PDF로 식단을 올립니다.
(자동 다운로드는 사이트가 막아둬서 **PDF는 사람이 직접 받아야 합니다**.)

```bash
# 1) 처음 한 번: 파이썬 패키지 설치
pip install -r requirements.txt

# 2) NHI 홈페이지 → 주간식단 게시판에서 이번 주 PDF 다운로드
#    https://www.nhi.go.kr/Introduce/introduce7/week/List.htm

# 3) 받은 PDF로 meals.json 갱신
python update_meals.py --pdf "주간식단계획(6.15~6.19).pdf"

# (표 형식이 이상하면 먼저 확인)
python update_meals.py --pdf "주간식단계획(6.15~6.19).pdf" --dry-run

# 4) 변경사항 푸시 → Vercel이 자동 재배포
git add meals.json
git commit -m "식단 업데이트 (6.15~6.19)"
git push
```

> PDF 표 형식이 바뀌어 파싱이 깨지면 `update_meals.py`의 `parse_table_to_meals()` 함수를
> 실제 표 구조에 맞게 수정하면 됩니다. (현재는 "날짜=행, 아침/점심/저녁=열" 형식 기준)

---

## 6. 강의 일정 수정

`schedule.json`에서 해당 날짜 배열에 문자열을 추가/수정하고 push하면 됩니다.
- 날짜 형식: `"YYYY-MM-DD"`
- 마감 항목은 `[제출]`로 시작하고, 실제 마감일을 `6.21.(일) 23:59까지` 형태로 적으면
  웹앱이 그 날짜를 "오늘 마감"으로 정확히 인식합니다.

---

## 7. 배포 (자동)

따로 할 게 없습니다. **`git push` 하면 Vercel이 1~2분 내 자동 재배포**합니다.
배포 확인: https://new-kakao-talk-bot-2.vercel.app 새로고침.

---

## 8. 새 노트북의 Claude에게 붙여넣을 프롬프트

새 노트북에서 Claude(Claude Code)를 열고, 저장소 폴더에서 아래를 그대로 붙여넣으면
맥락을 빠르게 파악합니다:

```
이 폴더는 "제71기 신임관리자과정" 교육생용 정적 모바일 웹앱이야.
GitHub: https://github.com/ejrwls182-tech/new-kakao-talk-bot_2
배포: Vercel (https://new-kakao-talk-bot-2.vercel.app), git push하면 자동 재배포.

구성:
- index.html : 웹앱 전체(강의/식단/할일/사다리 탭). 브라우저에서 schedule.json, meals.json을 직접 읽음.
- schedule.json : 강의·일정 데이터
- meals.json : 식단 데이터
- update_meals.py : NHI 주간식단 PDF를 파싱해 meals.json 갱신 (pip install -r requirements.txt 후 python update_meals.py --pdf <파일>)
- app.py : 구버전 Flask 서버, 지금은 안 씀

자세한 인수인계는 HANDOFF.md 참고. 앞으로 매주 식단 PDF 받아서 meals.json 갱신 + push 하는 게 주 작업이야.
오늘 할 일을 말할게:
```

---

## 9. 체크리스트 (새 노트북에서 한 번만)

- [ ] Git 설치
- [ ] Python 3 설치 (식단 갱신용)
- [ ] `git clone` 으로 저장소 받기
- [ ] `git push` 인증 설정 (gh auth login 또는 PAT)
- [ ] `pip install -r requirements.txt`
- [ ] 테스트: `meals.json` 살짝 고치고 commit/push → Vercel 재배포 확인
