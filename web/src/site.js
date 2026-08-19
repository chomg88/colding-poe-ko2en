// 사이트 전역 설정. 도메인을 사거나 이름을 바꿀 때 여기만 고치면 된다.
export const SITE = {
  name: "POE 툴박스",
  tagline: "Path of Exile 한국 유저를 위한 도구 모음",
  // 도메인 확정 전 임시값. Cloudflare Pages 연결 후 실제 도메인으로 교체.
  origin: "https://example.com",
  // 애드센스 승인 후 ca-pub-... 을 넣으면 광고 슬롯이 켜진다. 비어 있으면 꺼진다.
  adsenseClient: "",
};

// 도구 목록. 새 도구를 추가하면 랜딩 카드와 네비게이션에 자동 반영된다.
export const TOOLS = [
  {
    slug: "ko2en",
    href: "/tools/ko2en/",
    name: "아이템 역번역기",
    blurb: "한글 클라이언트에서 복사한 아이템을 영문 Path of Building 이 읽는 형태로 되돌립니다.",
    tags: ["번역", "POB"],
    ready: true,
  },
];
