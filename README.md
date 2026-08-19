# POE 한글 아이템 역번역기

한글 클라이언트에서 복사한 Path of Exile 아이템 텍스트를 **영문 Path of Building 이 읽는 형태로 되돌립니다.**

👉 **https://colding.xyz**

게임에서 아이템을 `Ctrl+C` 한 뒤 붙여넣으면 영문이 나옵니다. 그대로 복사해 영문 POB 의 아이템 입력칸에 넣으면 됩니다.

거래소 복사본과 게임 클라이언트 복사본을 모두 받습니다. 게임에서 **고급 아이템 정보 표시**(기본 켜짐)로 딸려오는 값 범위·접사 이름·태그도 같이 옮깁니다.

```
아이템 종류: 방패              →  Item Class: Shields
아이템 희귀도: 희귀            →  Rarity: Rare
칠흑의 거대 방패               →  Ebony Tower Shield
막기 확률: 25%                →  Chance to Block: 25%
1초마다 생명력 30.8 재생        →  Regenerate 30.8 Life per second
26%의 확률로 원소 상태 이상 긴급회피 →  26% chance to Avoid Elemental Ailments
```

게임의 고급 아이템 정보도 그대로 따라갑니다.

```
퀄리티 (저항 속성 부여): +20% (augmented)
  →  Quality (Resistance Modifiers): +20% (augmented)
{ 접두어 속성 부여 "압도하는" (등급: 2) — 피해, 원소, 공격 }
  →  { Prefix Modifier "Overpowering" (Tier: 2) — Damage, Elemental, Attack }
공격 스킬의 원소 피해 38(37-42)% 증가
  →  38(37-42)% increased Elemental Damage with Attack Skills
심연 홈 1개 — 변경이 불가능한 값
  →  Has 1 Abyssal Socket — Unscalable Value
```

전부 브라우저 안에서 돌아갑니다. 서버로 아무것도 보내지 않습니다.

## 어떻게 동작하나

한글 POB 는 `EN,KO` 두 열짜리 CSV 사전으로 화면을 번역합니다. 이 도구는 그 사전을 뒤집어 씁니다.

매칭 규칙은 한글 POB 런처(PoeCharm3) 내부의 중문 역번역기와 같은 방식입니다.

```js
body(s) = s 에서 { } ( ) 숫자 . + - 를 전부 제거   // 인덱스 키
```

괄호는 원본 규칙에 없습니다. 고급 아이템 정보가 값 뒤에 범위를 붙이기 때문에
(`원소 피해 38(37-42)% 증가`) 인덱스 키에서 같이 지웁니다. 사전 쪽과 입력 쪽에
똑같이 적용되므로 매칭은 그대로 성립하고, 범위는 `{0}` 자리에 통째로 잡혀
영문에도 `38(37-42)` 로 그대로 실려 나갑니다. POB 는 이 범위를 읽어 모드 범위를 표시합니다.

숫자를 지운 "몸통"으로 후보를 찾고, 후보의 `{0}` 자리를 `(\S+)` 로 바꿔 매칭한 뒤, 뽑아낸 값을 영문 템플릿에 렌더링합니다. 아이템 텍스트는 `--------` 로 블록을 나눠 이름/속성/옵션을 구분해 처리합니다.

같은 한글이 여러 영문에 대응하는 경우(`부식성` = Corrosive / Caustic)는 노란색으로 표시하고, 눌러서 다른 후보로 교체할 수 있습니다.

## 사전

원본 CSV 는 109MB 인데, 그 대부분이 **아이템 이름 조합을 전개해둔 것**입니다. 이건 합성 규칙으로 대체했습니다.

```
초보자의 자수정 플라스크 - 풍부함  →  Amethyst Flask
```

`" - "` 뒤를 떼고 앞 단어를 하나씩 벗기며 베이스타입을 찾습니다. 접사 이름은 사라지지만 POB 는 아이템 이름이 아니라 아래 옵션 줄로 계산하므로 무관합니다.

결과적으로 전송량은 이렇습니다.

| 파일 | 크기 | 시점 |
|---|---|---|
| `index.html` | 21KB | 즉시 |
| `dict-core-*.json.gz` | 3.7MB | 로드 시 — 옵션·베이스타입·고유 |
| `dict-names-*.json.gz` | 1.0MB | 백그라운드 — 희귀 아이템 이름 |

파일명에 내용 해시가 있어 `immutable` 캐시가 걸립니다. 재방문 시 추가 전송이 없습니다.

## 구조

빌드가 둘로 나뉩니다. **Python 은 데이터, Astro 는 사이트**를 만듭니다.

```
Data/Translate/ko-KR/*.csv        109MB   한글 POB 에서 복사해 온 원본 (git 제외)
        │  python3 tools/build_data.py
        ▼
web/public/data/dict-*.json.gz    4.7MB   내용 해시가 박힌 사전 (git 포함)
        │  cd web && npm run build
        ▼
web/dist/                                 정적 사이트 → Cloudflare Pages
```

사전을 저장소에 넣어두는 이유는, 호스팅 빌드 환경에 109MB CSV 가 없기 때문입니다.
CSV 가 갱신될 때만 로컬에서 다시 만들어 커밋합니다.

```
tools/         ko2en.py  build_payload.py  build_data.py    데이터 파이프라인
web/src/
  lib/ko2en/   engine.js    역번역 엔진 (도구 간 공유)
               ui.js        도구 화면 조립
  layouts/     Base.astro   Prose.astro
  components/  Header  Footer  AdSlot
  pages/       index  tools/ko2en  guides  privacy
  site.js      사이트 이름 · 도메인 · 애드센스 ID · 도구 목록
```

새 도구는 `web/src/pages/tools/` 에 페이지를 만들고 `site.js` 의 `TOOLS` 에 한 줄
추가하면 됩니다. 랜딩 카드와 사이트맵에 자동 반영됩니다.

## 배포

Cloudflare Pages 에 wrangler 로 올린다.

```bash
cd web
npx wrangler login          # 최초 1회. 브라우저가 열린다
npm run deploy              # 빌드 + 배포
```

미리보기 배포는 `npm run deploy:pre` — 프로덕션 주소에 영향을 주지 않는다.

CI 나 비대화형 환경에서는 `wrangler login` 대신 API 토큰을 쓴다.
Cloudflare 대시보드에서 **Cloudflare Pages: Edit** 권한 토큰을 만들어:

```bash
export CLOUDFLARE_API_TOKEN=...
npm run deploy
```

설정은 `web/wrangler.toml` 에 있다 — 프로젝트명 `colding-poe`, 출력 `dist`.

### 자동 배포

`.github/workflows/deploy.yml` 이 빌드해서 올린다.

| 푸시한 브랜치 | 배포 |
|---|---|
| `release/**` | 프로덕션 (colding.xyz) |
| `main` | 미리보기 |

릴리스는 `main` 에서 `release/vX.Y.Z` 를 잘라 푸시한다.

```bash
git checkout -b release/v0.0.2 main
git push -u origin release/v0.0.2
```

Cloudflare 의 '프로덕션 브랜치' 설정은 이름 하나만 받고 패턴을 못 쓴다.
`release/v0.0.1` 을 그대로 넣으면 버전을 올릴 때마다 대시보드를 고쳐야 하므로,
워크플로가 배포 시 넘기는 이름을 `release` 로 고정한다. 그래서 Cloudflare 쪽
설정은 **프로덕션 브랜치 = `release`** 한 번이면 끝이다.

저장소 시크릿 두 개가 필요하다.

```bash
gh secret set CLOUDFLARE_API_TOKEN     # Cloudflare Pages: Edit 권한 토큰
gh secret set CLOUDFLARE_ACCOUNT_ID    # 대시보드 우측의 Account ID
```

프로덕션인지 미리보기인지는 워크플로가 아니라 Cloudflare 프로젝트의
**프로덕션 브랜치** 설정이 정한다. 워크플로는 브랜치 이름만 그대로 넘긴다.

배포 전에 **사전 참조 검증**을 돌린다. 페이지가 가리키는 `dict-*.json.gz` 가 실제로
출력에 있는지 확인하는 단계다. 사전을 다시 만들고 커밋하지 않으면 해시가 어긋나
도구가 죽는데, 빌드 자체는 성공하므로 이 단계가 없으면 배포된 뒤에야 드러난다.

## 다시 빌드하기

한글 POB 배포본의 `Data/Translate/ko-KR` 를 저장소 루트에 `Data/` 로 복사한 뒤
(git 에는 올라가지 않습니다):

```bash
python3 tools/build_data.py
cd web && npm run build
```

다른 위치에 두었으면 `KO2EN_DATA` 환경변수나 `--data` 로 넘기면 됩니다.
CSV 를 하나도 못 찾으면 빌드가 멈춥니다 — 예전에는 조용히 빈 사전을 만들어
결과물을 망가뜨렸습니다.

명령줄에서 바로 쓰고 싶다면:

```bash
python3 tools/ko2en.py item.txt
```

## 알려진 한계

- 프레임 문구 표(`아이템 종류:`, `타락됨`, `(내재)`, 아이템 종류 값)는 게임 클라이언트가 찍는 문구라 CSV 에 없습니다. `tools/page.tpl.html` 상단에 손으로 채워 넣은 표가 있고, 빠진 표기가 있으면 여기만 고치면 됩니다.
- 한글에서 구분이 사라지는 다대일 대응은 원리적으로 복원 불가능합니다. 해당 줄은 후보를 모두 보여줍니다.
- 원본 CSV 에 아예 빠진 항목이 있습니다 (`고유 적이 접근해 있는 동안, 주문 피해 {0}% 증가` 등). 통째로 못 찾은 줄은 `앞절, 뒷절` 로 나눠 각각 사전에 있을 때만 이어붙이고, 결과에 `이어붙임` 표시를 답니다.
- 원본 CSV 자체에 `증가/감소` 짝이 어긋난 항목이 일부 있습니다. 이 경우 역번역 결과가 한글 쪽을 따릅니다.
- `("심연 주얼"만 심연의 홈에 장착할 수 있습니다)` 처럼 통째로 괄호인 설명 줄은 POB 가 읽지 않는 문구라 결과에서 뺍니다.
- 고급 정보의 접사 태그(`피해`, `방어력` …)와 종류(`접두어 속성 부여` …)는 손표입니다. `tools/ko2en.py` 의 `ADV_TAG` / `ADV_KIND` 에 있습니다. 웹 배포본은 `tools/page.tpl.html` 에 같은 표가 한 벌 더 있으니 양쪽을 같이 고쳐야 합니다.
