// Firebase 초기화. 브라우저에서만 부른다.
//
// 애널리틱스는 두 가지 이유로 동적 import 로 미룬다.
//   1. firebase/analytics 는 measurement 스크립트를 끌고 오느라 덩치가 크다.
//      첫 화면 렌더를 막지 않게 한다.
//   2. isSupported() 가 false 인 환경(쿠키 차단, 일부 인앱 브라우저, WebView)이 있다.
//      지원 여부를 확인한 뒤에만 붙인다.
import { FIREBASE } from "../site.js";

// apiKey 가 비어 있으면 Firebase 를 아예 쓰지 않는다는 뜻이다.
export const enabled = Boolean(FIREBASE.apiKey);

let appPromise = null;

/** FirebaseApp 을 한 번만 만들어 재사용한다. 꺼져 있으면 null. */
export function getApp() {
  if (!enabled) return null;
  if (!appPromise) {
    appPromise = import("firebase/app").then(({ initializeApp }) =>
      initializeApp(FIREBASE),
    );
  }
  return appPromise;
}

let analyticsPromise = null;

/** Analytics 인스턴스. 미지원 환경이거나 꺼져 있으면 null 로 resolve 된다. */
export function getAnalytics() {
  if (!enabled || !FIREBASE.measurementId) return Promise.resolve(null);
  if (!analyticsPromise) {
    analyticsPromise = (async () => {
      const mod = await import("firebase/analytics");
      if (!(await mod.isSupported())) return null;
      return mod.getAnalytics(await getApp());
    })().catch(() => null); // 애널리틱스가 죽어도 사이트는 돌아가야 한다
  }
  return analyticsPromise;
}

/**
 * 이벤트 하나 기록. 실패해도 조용히 넘어간다.
 * 예) track("item_converted", { lines: 42 })
 */
export async function track(name, params) {
  const analytics = await getAnalytics();
  if (!analytics) return;
  const { logEvent } = await import("firebase/analytics");
  logEvent(analytics, name, params);
}
