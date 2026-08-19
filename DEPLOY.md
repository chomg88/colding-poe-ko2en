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
