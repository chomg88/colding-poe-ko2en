// 사이트 전역 설정. 도메인을 사거나 이름을 바꿀 때 여기만 고치면 된다.
export const SITE = {
  name: "POE 툴박스",
  tagline: "Path of Exile 한국 유저를 위한 도구 모음",
  origin: "https://colding.xyz",
  // 애드센스 승인 후 ca-pub-... 을 넣으면 광고 슬롯이 켜진다. 비어 있으면 꺼진다.
  adsenseClient: "",
  // 검색엔진 소유확인 메타 태그. 비어 있는 항목은 렌더링하지 않는다.
  // 공개돼도 되는 값이다 — HTML 에 박히는 것이 목적이다.
  verification: {
    naver: "279e9b466ae6b858d67b15b9ffe85f1a5500be45",
    google: "",
  },
};

// 도구 목록. 새 도구를 추가하면 랜딩 카드와 네비게이션에 자동 반영된다.
// 상단 탭바. 도구가 늘어나면 여기에 추가한다.
export const TABS = [
  { href: "/", label: "아이템 변환기" },
  { href: "/tools/", label: "도구" },
  { href: "/guides/", label: "가이드" },
];

export const TOOLS = [
  {
    slug: "ko2en",
    href: "/",
    name: "아이템 변환기",
    blurb: "한글 클라이언트에서 복사한 아이템을 영문 Path of Building 형식으로 바꿉니다.",
    tags: ["번역", "POB"],
    ready: true,
  },
];
