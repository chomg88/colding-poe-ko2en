# 배포

Cloudflare Pages 로 나간다. 프로덕션은 <https://colding.xyz>.

## 한눈에

```bash
# 개발 중 — main 에 밀면 미리보기 배포
git push origin main

# 릴리스 — main 에서 잘라 밀면 프로덕션 배포
git checkout -b release/v0.0.2 main
git push -u origin release/v0.0.2

# 내용 변경 없이 다시 배포
gh workflow run deploy.yml --ref release/v0.0.2

# 로컬에서 직접 (인증 필요)
cd web && npm run deploy
```

## 구조

빌드가 둘이다. **Python 은 데이터, Astro 는 사이트**를 만든다.

```
Data/Translate/ko-KR/*.csv        109MB   한글 POB 에서 복사 (git 제외)
        │  python3 tools/build_data.py
        ▼
web/public/data/dict-*.json.gz    4.7MB   내용 해시가 박힌 사전 (git 포함)
        │  cd web && npm run build
        ▼
web/dist/                                 정적 사이트 → Cloudflare Pages
```

**사전은 반드시 커밋해야 한다.** CI 빌드 환경에는 109MB CSV 가 없어서 다시 만들 수
없다. CSV 가 갱신될 때만 로컬에서 만들어 커밋한다. 그래서 CI 에는 Python 이 필요 없고
Node 만 돈다.

## 브랜치 모델

| 푸시한 브랜치 | 배포 |
|---|---|
| `release/**` | 프로덕션 — colding.xyz |
| `main` | 미리보기 — 임시 주소 |

릴리스 브랜치는 `main` 에서 잘라 그대로 두고 **자기 커밋을 쌓지 않는다.** 쌓으면
`main` 과 갈라져 다음 릴리스에서 fast-forward 가 막힌다. 고칠 것이 있으면 `main` 에서
고치고 새 릴리스 브랜치를 자른다.

## 최초 설정

한 번만 하면 되는 것들이다. 이미 되어 있다.

**저장소 시크릿 두 개**

```bash
gh secret set CLOUDFLARE_API_TOKEN     # Cloudflare Pages: Edit 권한 토큰
gh secret set CLOUDFLARE_ACCOUNT_ID    # 대시보드 우측의 Account ID
```

토큰은 Cloudflare → My Profile → API Tokens → Create Token → **Cloudflare Pages: Edit**
템플릿으로 만든다.

**Cloudflare 프로덕션 브랜치 = `release`**

Workers & Pages → colding-poe → Settings → Builds & deployments → Production branch.

`release/v0.0.1` 이 아니라 **`release`** 다. Cloudflare 의 이 설정은 이름 하나만 받고
패턴을 못 쓴다. 버전 붙은 이름을 그대로 넣으면 올릴 때마다 대시보드를 고쳐야 한다.
그래서 워크플로가 배포할 때 넘기는 이름을 `release` 로 고정한다 — `release/**` 어느
브랜치에서 밀든 프로덕션이 되고 설정은 건드릴 일이 없다.

대신 대시보드에서 어느 브랜치였는지 안 보이므로, 커밋 메시지에 실제 브랜치와 SHA 를
실어 보낸다.

**커스텀 도메인** — Custom domains 에서 `colding.xyz` 추가. Cloudflare 에서 산
도메인이면 DNS 가 자동으로 잡힌다.

## 애드센스

신청과 승인은 시점이 다르고, 사이트에 넣어야 할 값도 다르다. `site.js` 의
`adsenseClient` 하나로 두 단계를 나눠 둔다.

**1단계 — 신청.** 애드센스에 사이트를 등록하면 심사 전에 `ca-pub-...` 을 먼저 준다.
이 값을 `site.js` 의 `adsenseClient` 에 넣고 릴리스하면 `<head>` 에 사이트 확인
메타 태그와 로더 스크립트가 나간다. 심사는 이 둘 중 하나만 잡히면 통과한다.
`AdSlot` 은 슬롯 ID 가 따로 있어야 켜지므로 **광고는 아직 한 칸도 나가지 않는다.**
이게 정상이다 — 심사 중에 빈 광고 자리가 보이지 않는다.

```js
// web/src/site.js
adsenseClient: "ca-pub-0000000000000000",
```

**2단계 — 승인.** 승인되면 두 가지를 채운다.

```bash
# 1. ads.txt — 애드센스가 알려주는 한 줄로 통째로 교체 (주석 줄은 지운다)
#    google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0
web/public/ads.txt

# 2. 광고 단위를 만들고 받은 슬롯 ID 를 <AdSlot slot="..." /> 에 채운다
grep -rn 'AdSlot slot' web/src/pages
```

슬롯이 들어가는 자리는 지금 랜딩 두 곳, 도구 목록, 가이드 목록, 가이드 본문이다.
`slot` 이 빈 문자열인 동안에는 아무것도 렌더링되지 않는다.

**심사 전 확인.** 거절 사유의 대부분은 광고 코드가 아니라 사이트 쪽이다.

- `/privacy/` — 제3자 쿠키·맞춤 광고 해제 안내가 들어 있어야 한다. 이미 있다.
- `/about/` — 사이트가 뭔지, 누가 만드는지, 문의는 어디로 하는지. 푸터에서 닿는다.
  메일을 공개하려면 `site.js` 의 `contactEmail` 을 채운다. 비어 있으면 GitHub 이슈만 안내한다.
- 콘텐츠 분량 — 도구 페이지만으로는 "가치 있는 콘텐츠 부족" 으로 잘린다.
  가이드가 최소 몇 편은 살아 있어야 한다.
- `robots.txt` 와 사이트맵이 크롤링을 막고 있지 않은지. `/robots.txt` 는 전면 허용이다.

## Firebase

방문 통계용이다. 콘솔 프로젝트는 `colding-poe`, 측정 ID 는 `G-ZLS9XJS77G`.

설정값은 `site.js` 의 `FIREBASE` 에 그대로 박혀 있다. `apiKey` 를 포함해 전부
클라이언트 번들에 나가는 공개 값이다 — 이건 비밀이 아니라 프로젝트 식별자고,
Firebase 도 그렇게 쓰라고 준다. 실제 접근 제어는 콘솔의 **승인된 도메인**과
보안 규칙에서 한다. 애널리틱스만 쓰는 지금은 승인된 도메인만 맞으면 된다.

```js
// web/src/site.js — 끄려면 apiKey 를 비운다
FIREBASE = { apiKey: "...", measurementId: "G-ZLS9XJS77G", ... }
```

`apiKey` 나 `measurementId` 가 비어 있으면 `Analytics.astro` 가 스크립트를 아예
내보내지 않는다. 애드센스와 같은 방식이다.

**로딩 방식.** `firebase/analytics` 는 gzip 14KB 쯤 되고 googletagmanager 스크립트를
따로 끌고 온다. 그래서 `src/lib/firebase.js` 에서 동적 import 로 미룬다. 첫 화면
렌더를 막지 않고, `isSupported()` 가 false 인 환경(쿠키 차단, 일부 인앱 브라우저)에서는
그냥 조용히 아무것도 하지 않는다. 실패해도 사이트는 그대로 돈다.

**페이지뷰**는 GA4 가 알아서 보낸다. MPA 라 페이지마다 새로 로드되므로 라우팅 훅이 없다.

**직접 이벤트를 보내려면** `track()` 을 쓴다. 미지원 환경이면 알아서 무시된다.

```js
import { track } from "../lib/firebase.js";
track("item_converted", { lines: 42 });
```

아이템 텍스트처럼 사용자가 입력한 내용은 절대 파라미터에 싣지 않는다.
`/privacy/` 에 "입력 내용은 통계로 전송되지 않는다" 고 적어 뒀다.

**확인.** 릴리스 후 Firebase 콘솔 → Analytics → DebugView 나 실시간 보고서에 찍히는지
본다. 로컬 `npm run dev` 에서도 나가므로, 개발 트래픽을 섞기 싫으면 브라우저 확장이나
`apiKey` 를 잠깐 비워서 막는다.

## 리그 갱신

한글 POB 사전이 바뀌었을 때.

```bash
# 1. 새 CSV 를 저장소 루트 Data/ 로 복사 (git 제외 대상)
# 2. 사전 다시 생성
python3 tools/build_data.py

# 3. 사이트 빌드해서 확인
cd web && npm run build && npm run dev

# 4. 커밋 — 사전 파일명이 바뀌므로 반드시 같이 올라간다
git add -A && git commit -m "3.30 사전 갱신"
git push origin main
```

`Data/` 를 다른 곳에 두었으면 `KO2EN_DATA` 환경변수나 `--data` 로 경로를 넘긴다.
CSV 를 하나도 못 찾으면 빌드가 멈춘다 — 예전에는 조용히 빈 사전을 만들어 결과물을
망가뜨렸다.

## 서판 시세

`/tools/tablet/` 은 다른 도구와 달리 **값이 사이트 밖에서 온다.** 빌드에 들어가는 건
카탈로그(무엇을 물어볼지)뿐이고, 시세는 운영자 PC 의 수집기가 모아 이 저장소의
`data` 브랜치에 올린다.

```
tools/tablet_catalog.py  ──→  web/public/data/tablet-catalog-*.json.gz   (git 포함, 시즌마다)
                                      │ 같은 파일을 읽는다
tools/tablet_prices.py (운영자 맥, launchd 로 상시)
        │ 30분마다, 값이 바뀌었으면
        ▼
data 브랜치 tablet-prices.json  ──→  raw.githubusercontent.com  ──→  페이지가 직접 읽는다
```

**왜 사이트가 직접 모으지 못하나.** 카카오 거래 API 는 다른 출처에서 부를 수 없다(CORS).
그리고 IP 마다 한도가 걸려 있어 한 바퀴에 여섯 시간이 필요하다 — 방문자 브라우저나
CI 에서 할 수 있는 일이 아니다. 로그인은 필요 없다(2026-09-14 확인). 한도는 응답 헤더에
그대로 온다.

```
검색 5:10:60, 15:60:300, 30:300:1800, 600:21600:3600      ← 제일 빡빡하다
상세 12:4:10, 16:12:300, 50:300:300, 1000:21600:1800
환전 5:15:60, 10:90:300, 30:300:1800
```

"600:21600:3600" 은 21600초(6시간)에 600건까지, 넘으면 3600초 차단. 키 하나에 검색 1 +
상세 1 이고 한 바퀴가 481키라, 45초에 하나씩(6시간 480키) 돈다. 수집기가 헤더의 잔량을
보고 스스로 늦추고, 그래도 막히면(429) 시키는 만큼 쉰다.

**왜 data 브랜치인가.** 시세 파일(~100KB)을 `main` 에 커밋하면 30분마다 기록이 쌓이고
미리보기 배포까지 돈다. `data` 는 배포 워크플로 트리거(`main`, `release/**`)에 안 걸리고,
수집기가 부모 없는 커밋 하나를 계속 강제 푸시하므로 기록도 쌓이지 않는다.
**`data` 브랜치에 사람이 커밋하지 않는다** — 다음 게시가 덮어쓴다.

**멈추면.** 운영자 PC 가 꺼지면 값이 멈춘다. 페이지는 파일 안의 `updatedAt`(가장 최근에
본 구간의 시각)이 `site.js` 의 `TABLET.warnHours`(3시간)를 넘으면 노란 경고,
`badHours`(24시간)를 넘으면 빨간 경고를 띄운다. 리그가 카탈로그와 다르면 그것도 경고한다.

**수집기 돌리기**

```bash
python3 tools/tablet_prices.py --once --no-push --limit 5   # 시험 — 안 올리고 다섯 키만
python3 tools/tablet_prices.py                              # 계속 돌면서 30분마다 게시

# 맥에서 상시로 (로그인할 때 뜨고, 죽으면 다시 뜬다)
cp tools/xyz.colding.tablet-collector.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/xyz.colding.tablet-collector.plist
launchctl print gui/$(id -u)/xyz.colding.tablet-collector | head    # 상태
tail -f .cache/tablet/collector.log                                 # 하는 일
launchctl bootout gui/$(id -u)/xyz.colding.tablet-collector         # 내리기
```

**수집기는 한 대만 돈다.** 게시가 부모 없는 강제 푸시라, 두 대가 돌면 서로 덮어쓰고
값이 왔다 갔다 한다. 기계를 옮길 때는 새 기계를 `--no-push` 로 채운 뒤 옛 기계를 내린다.

진행 상태는 `.cache/tablet/prices-state.json` 에 쌓인다(git 제외). 이 파일이 없으면
`data` 브랜치에 올라가 있는 값을 씨앗으로 받아 이어서 돈다 — 새 기계에서 처음 돌려도
한 바퀴(여섯 시간) 동안 페이지가 '대기' 로 비지 않는다. 리그나 카탈로그가 바뀌었으면
씨앗을 버리고 처음부터 모은다.

**시즌이 바뀌면**

```bash
# 1. 카탈로그 다시 생성 — 새 리그 id 는 거래소 /api/trade2/data/leagues 에서
python3 tools/tablet_catalog.py --refresh --league "새 리그 id"
#    [못 맞춤] 줄이 나오면 tools/tablet_catalog.py 의 OVERRIDES 에 stat id 를 적고 다시

# 2. 커밋하고 평소처럼 릴리스 — 카탈로그 파일명이 바뀌므로 반드시 같이 올라간다
git add -A && git commit -m "서판 카탈로그 — 새 리그"
```

수집기는 리그를 카탈로그에서 읽으므로 따로 고칠 곳이 없다. 카탈로그가 바뀌면 모아 둔
값을 버리고 처음부터 다시 모은다.

**시세 파일 모양** — `b` 의 키는 카탈로그 `mods[].keys` 와 같다.

```json
{"schema":1, "league":"Forbidden Rites", "catalog":"tablet-catalog-….json.gz",
 "publishedAt":1757700000, "updatedAt":1757699000,
 "rates":{"divine":400,"chaos":50}, "progress":{"rep":[120,254],"deep":[10,40]},
 "deepMin":30, "sample":10,
 "b":{"<옵션id>:<최소수치>":[시각, 매물 수, 값 낸 수, 최저, 중앙값, 검색id, "오류"]}}
```

`검색id` 는 거래소가 돌려준 그대로다 — 페이지가 거래소 링크로 쓴다. 마지막 `오류` 는
그 키를 못 봤을 때만 붙는다.

**무엇을 물어보나.** 616키를 다 돌면 여섯 시간에 안 들어와서 두 단계로 나눈다.
옵션마다 가장 낮은 수치 하나씩(대표, 254키)을 먼저 채우고, 대표 중앙값이 `deepMin`
(30엑잘) 이상인 비싼 옵션만 나머지 수치까지 본다(정밀, ~227키). 매물 열 건의 최저와
중앙값을 싣는다.

**값을 엑잘로 맞추는 법.** 매물 값표는 엑잘·디바인·카오스·바알 등 제각각이다. 환전소
(`/api/trade2/exchange`)에서 디바인·카오스 값만 받아 환산하고, 나머지 화폐로 걸린
매물은 세지 않는다(몇 건을 세었는지가 `값 낸 수`). 바알 같은 화폐는 엑잘 환전 시장이
얇아 '1개 500엑잘' 같은 허수 호가가 섞이는데, 그걸로 환산하면 표가 통째로 망가진다.

## 함정

실제로 겪고 고친 것들이다. 다시 밟지 않도록 적어 둔다.

### `paths` 필터를 쓰면 릴리스가 안 걸린다

워크플로에 `on.push.paths` 를 두면, `main` 과 같은 커밋에서 릴리스 브랜치를 잘랐을 때
**워크플로가 아예 돌지 않는다.** 푸시된 새 커밋이 없어 변경 파일 비교가 성립하지
않기 때문이다. 릴리스 브랜치를 자르는 행위 자체가 배포 트리거이므로 필터를 두면
안 된다. 빌드가 1분이라 아끼는 이득도 작다.

### `_headers` 규칙은 전부 이어붙는다

Cloudflare Pages 는 매칭되는 규칙을 하나만 고르지 않고 **전부 적용한다.**
`/data/*` 는 `/*` 에도 걸리므로 그냥 두면 이렇게 나간다.

```
cache-control: public, max-age=31536000, immutable, public, max-age=600
```

`max-age` 가 둘이라 브라우저가 어느 쪽을 택할지 불분명하고, 600 을 택하면 해시
파일명으로 만든 영구 캐시가 무의미해진다. `! 헤더명` 으로 앞서 붙은 값을 지우고
다시 넣어야 한다. `tools/build_data.py` 가 그렇게 생성한다.

### `.gitignore` 의 `Data/` 가 `web/public/data/` 를 삼킨다

macOS 는 파일명 대소문자를 구분하지 않아 `Data/` 패턴이 `data/` 에도 걸린다.
사전이 통째로 커밋에서 빠지고, CI 에는 CSV 가 없으니 배포된 사이트에서 도구가 죽는다.
루트 기준 `/Data/` 로 고정해 뒀다.

### 사전 해시는 압축 결과가 아니라 JSON 원문에서 뽑는다

Python 3.11+ 의 `gzip.compress(mtime=0)` 은 내부적으로 `zlib.compress(wbits=31)` 로
우회하는데, gzip 헤더의 OS 바이트를 zlib 빌드가 정한다. 압축본을 해시하면 **내용이
같아도 기계가 바뀌면 파일명이 바뀐다.** 캐시가 무의미하게 깨지고 저장소에 4.7MB
블롭이 매번 쌓인다.

### macOS 파일명은 NFD 다

한글 파일명을 코드에서 비교할 때 NFC 로 정규화하지 않으면 매칭되지 않는다.
`tools/` 의 파일 목록 처리에 `unicodedata.normalize("NFC", ...)` 가 들어 있는 이유다.

### 내용 변경 없이 재배포할 때 빈 커밋을 쓰지 않는다

릴리스 브랜치가 `main` 과 갈라져 다음 fast-forward 가 막힌다. 대신 수동 실행을 쓴다.

```bash
gh workflow run deploy.yml --ref release/v0.0.1
```

## 배포 전 검증

워크플로가 배포 직전에 **사전 참조 검증**을 돌린다. 페이지가 가리키는
`dict-*.json.gz` 가 실제로 출력에 있는지 확인하는 단계다.

사전을 다시 만들고 커밋하지 않으면 해시가 어긋나 도구가 죽는데 **빌드 자체는
성공한다.** 이 단계가 없으면 배포된 뒤에야 드러난다.

## 문제 해결

| 증상 | 원인 |
|---|---|
| 워크플로가 아예 안 돈다 | 브랜치가 `main` 또는 `release/**` 인지 확인. 그 외 브랜치는 트리거되지 않는다 |
| `The Pages project does not exist` | 첫 배포다. 워크플로가 자동으로 만든다 — 실패했다면 토큰 권한(Pages: Edit)을 확인 |
| `CLOUDFLARE_API_TOKEN` 없다는 오류 | 저장소 시크릿 미설정 |
| 사전 참조 검증 실패 | `python3 tools/build_data.py` 결과를 커밋하지 않았다 |
| 배포는 됐는데 colding.xyz 가 안 바뀐다 | Cloudflare 프로덕션 브랜치가 `release` 인지 확인. 아니면 미리보기로 나간다 |
| 사전을 매번 다시 받는다 | `_headers` 의 `! Cache-Control` 이 빠졌는지 확인 |
| 로컬 `npm run deploy` 가 인증 오류 | `npx wrangler login` 또는 `CLOUDFLARE_API_TOKEN` 설정 |

## 로컬 배포

CI 없이 직접 올릴 때.

```bash
cd web
npx wrangler login     # 최초 1회. 브라우저가 열린다
npm run deploy         # 빌드 + 프로덕션 배포
npm run deploy:pre     # 미리보기 배포
npm run cf:whoami      # 인증 상태 확인
```

설정은 `web/wrangler.toml` — 프로젝트명 `colding-poe`, 출력 `dist`.
