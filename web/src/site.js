// 사이트 전역 설정. 도메인을 사거나 이름을 바꿀 때 여기만 고치면 된다.
export const SITE = {
  name: "POE 툴박스",
  tagline: "Path of Exile 한국 유저를 위한 도구 모음",
  origin: "https://colding.xyz",
  // 애드센스. 신청 단계에서 발급받는 ca-pub-... 을 넣는다.
  // 이 값만 넣으면 로더 스크립트와 사이트 확인 메타 태그가 켜지고 (심사에 필요),
  // 광고 자체는 AdSlot 에 슬롯 ID 를 채우기 전까지 나가지 않는다. 비어 있으면 전부 꺼진다.
  adsenseClient: "",
  // 문의용 메일. 비어 있으면 소개 페이지에 GitHub 이슈만 안내한다.
  contactEmail: "",
  // 검색엔진 소유확인 메타 태그. 비어 있는 항목은 렌더링하지 않는다.
  // 공개돼도 되는 값이다 — HTML 에 박히는 것이 목적이다.
  verification: {
    naver: "279e9b466ae6b858d67b15b9ffe85f1a5500be45",
    // colding.xyz 는 DNS TXT 레코드로 확인돼 있다. 메타 태그는 필요 없다.
    google: "",
  },
};

// Firebase. 콘솔의 "웹 앱" 설정에 나오는 값 그대로다.
// 전부 클라이언트 번들에 박히는 공개 값이다 — apiKey 도 비밀이 아니라 프로젝트 식별자다.
// 접근 제어는 Firebase 콘솔의 보안 규칙과 승인된 도메인에서 한다.
// apiKey 를 비워두면 Firebase 초기화 자체를 건너뛴다.
export const FIREBASE = {
  apiKey: "AIzaSyBdkgrthsbBExUe1CbGypgThIqFsd3Dn0s",
  authDomain: "colding-poe.firebaseapp.com",
  projectId: "colding-poe",
  storageBucket: "colding-poe.firebasestorage.app",
  messagingSenderId: "884278995501",
  appId: "1:884278995501:web:79b331ab0ab7b9b67aa6a4",
  measurementId: "G-ZLS9XJS77G",
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
