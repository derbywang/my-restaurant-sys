// The words of the kitchen screen in ja / zh / ko / en (docs/design/i18n-design.md 4.5).
// Dish names are not translated: they are the standard names on the ticket. Terms follow
// chapter 12 of the design (厨房伝票, テーブル, キッチン, 担当 ...). `en` is the fallback.
// Pure functions only (the tests run them in node); the current language is in ./language.js.

export const LANGUAGES = ["ja", "zh", "ko", "en"];
export const DEFAULT_LANGUAGE = "ja";

const LOCALES = { ja: "ja-JP", zh: "zh-CN", ko: "ko-KR", en: "en-US" };

export const MESSAGES = {
  ja: {
    "app.title": "キッチンディスプレイ",
    "auth.not_permitted": "権限がありません",
    "auth.login_required": "このページを表示するにはログインしてください。",
    "auth.login": "ログイン",
    "auth.username": "ユーザー名:",
    "auth.password": "パスワード:",
    "auth.sign_in": "ログイン",
    "kot.no_active_orders": "{production} の注文はありません",
    "kot.table": "テーブル",
    "kot.takeaway": "持ち帰り",
    "kot.order": "注文",
    "kot.aggregator": "配達プラットフォーム",
    "kot.aggregator_id": "配達プラットフォームID",
    "kot.confirm": "確認",
    "kot.serve": "提供",
    "kot.duplicate": "重複した厨房伝票（担当に確認してください）",
    "kot.old_qty": "[変更前 {qty}]",
    "kot.audio_disabled": "音声通知がオフです。画面のどこかをタップすると有効になります。",
    "kot.order_delayed": "注文が遅れています",
    "kot.invoice": "伝票",
    "kot.order_no": "注文番号",
    "kot.time": "時刻",
    "kot.table_unknown": "テーブル／持ち帰りの情報がありません",
    "kot.not_available": "なし",
    "kot.type.Cancelled": "取消",
    "kot.type.Partially cancelled": "一部取消",
    "kot.type.Order Modified": "注文変更",
    "status.online": "オンラインになりました",
    "status.offline": "オフラインです",
    "header.switch_dashboard": "ダッシュボードに切り替え",
    "header.logout": "ログアウト",
    "header.user": "ユーザー",
    "production.unit": "キッチン",
    "production.active": "対応中",
    "production.served": "提供済み",
    "production.total": "合計",
    "production.click_to_view": "タップして厨房伝票を表示",
    "production.loading": "キッチンの状況を読み込み中…",
  },
  zh: {
    "app.title": "厨房显示屏",
    "auth.not_permitted": "没有权限",
    "auth.login_required": "请登录后查看此页面。",
    "auth.login": "登录",
    "auth.username": "用户名:",
    "auth.password": "密码:",
    "auth.sign_in": "登录",
    "kot.no_active_orders": "{production} 没有进行中的订单",
    "kot.table": "桌台",
    "kot.takeaway": "外带",
    "kot.order": "订单",
    "kot.aggregator": "外卖平台",
    "kot.aggregator_id": "外卖平台编号",
    "kot.confirm": "确认",
    "kot.serve": "出餐",
    "kot.duplicate": "重复的厨房单（请向服务员确认）",
    "kot.old_qty": "[原数量 {qty}]",
    "kot.audio_disabled": "语音提示已关闭。点击屏幕任意位置即可开启。",
    "kot.order_delayed": "订单已延误",
    "kot.invoice": "账单",
    "kot.order_no": "订单号",
    "kot.time": "时间",
    "kot.table_unknown": "没有桌台／外带信息",
    "kot.not_available": "无",
    "kot.type.Cancelled": "已取消",
    "kot.type.Partially cancelled": "部分取消",
    "kot.type.Order Modified": "订单已修改",
    "status.online": "已联网",
    "status.offline": "已断网",
    "header.switch_dashboard": "切换到看板",
    "header.logout": "退出登录",
    "header.user": "用户",
    "production.unit": "出品厨房",
    "production.active": "进行中",
    "production.served": "已出餐",
    "production.total": "合计",
    "production.click_to_view": "点击查看厨房单",
    "production.loading": "正在加载厨房状况…",
  },
  ko: {
    "app.title": "주방 디스플레이",
    "auth.not_permitted": "권한이 없습니다",
    "auth.login_required": "이 페이지를 보려면 로그인하세요.",
    "auth.login": "로그인",
    "auth.username": "사용자 이름:",
    "auth.password": "비밀번호:",
    "auth.sign_in": "로그인",
    "kot.no_active_orders": "{production}에 진행 중인 주문이 없습니다",
    "kot.table": "테이블",
    "kot.takeaway": "포장",
    "kot.order": "주문",
    "kot.aggregator": "배달 플랫폼",
    "kot.aggregator_id": "배달 플랫폼 ID",
    "kot.confirm": "확인",
    "kot.serve": "제공",
    "kot.duplicate": "중복된 주방 전표 (담당자에게 확인하세요)",
    "kot.old_qty": "[변경 전 {qty}]",
    "kot.audio_disabled": "소리 알림이 꺼져 있습니다. 화면을 아무 곳이나 누르면 켜집니다.",
    "kot.order_delayed": "주문이 지연되고 있습니다",
    "kot.invoice": "전표",
    "kot.order_no": "주문 번호",
    "kot.time": "시각",
    "kot.table_unknown": "테이블／포장 정보가 없습니다",
    "kot.not_available": "없음",
    "kot.type.Cancelled": "취소",
    "kot.type.Partially cancelled": "일부 취소",
    "kot.type.Order Modified": "주문 변경",
    "status.online": "온라인 상태입니다",
    "status.offline": "오프라인 상태입니다",
    "header.switch_dashboard": "대시보드로 전환",
    "header.logout": "로그아웃",
    "header.user": "사용자",
    "production.unit": "주방",
    "production.active": "진행 중",
    "production.served": "제공 완료",
    "production.total": "합계",
    "production.click_to_view": "눌러서 주방 전표 보기",
    "production.loading": "주방 현황을 불러오는 중…",
  },
  en: {
    "app.title": "Kitchen Display",
    "auth.not_permitted": "Not Permitted",
    "auth.login_required": "Log in to access this page.",
    "auth.login": "Login",
    "auth.username": "Username:",
    "auth.password": "Password:",
    "auth.sign_in": "Sign in",
    "kot.no_active_orders": "No active orders for {production}",
    "kot.table": "Table",
    "kot.takeaway": "Takeaway",
    "kot.order": "Order",
    "kot.aggregator": "Aggregator",
    "kot.aggregator_id": "Aggregator ID",
    "kot.confirm": "Confirm",
    "kot.serve": "Serve",
    "kot.duplicate": "Duplicate KOT (check with the captain)",
    "kot.old_qty": "[Old Qty = {qty}]",
    "kot.audio_disabled": "Audio notifications disabled. Click anywhere to enable.",
    "kot.order_delayed": "Order Delayed",
    "kot.invoice": "Invoice",
    "kot.order_no": "Order #",
    "kot.time": "Time",
    "kot.table_unknown": "Table/Takeaway info unavailable",
    "kot.not_available": "N/A",
    "kot.type.Cancelled": "Cancelled",
    "kot.type.Partially cancelled": "Partially cancelled",
    "kot.type.Order Modified": "Order Modified",
    "status.online": "You are online",
    "status.offline": "You are offline",
    "header.switch_dashboard": "Switch to Dashboard",
    "header.logout": "Logout",
    "header.user": "User",
    "production.unit": "Production Unit",
    "production.active": "Active",
    "production.served": "Served",
    "production.total": "Total",
    "production.click_to_view": "Click to view KOTs",
    "production.loading": "Loading Production Dashboard...",
  },
};

/** The language of the screen for a language code of the user (zh-TW -> zh); anything else is Japanese. */
export function normalizeLanguage(code) {
  const base = String(code || "").split("-")[0];
  return LANGUAGES.includes(base) ? base : DEFAULT_LANGUAGE;
}

/** The locale the clock is written in. */
export function localeOf(lang) {
  return LOCALES[normalizeLanguage(lang)];
}

/** The text in the language, else in English; undefined when nobody has it. */
function find(lang, key) {
  return MESSAGES[lang]?.[key] ?? MESSAGES.en[key];
}

export function hasMessage(lang, key) {
  return find(lang, key) !== undefined;
}

/** The text of `key` in `lang` (else English, else the key itself), with `{name}` filled in from `params`. */
export function translate(lang, key, params = {}) {
  const text = find(lang, key) ?? key;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in params ? String(params[name]) : whole));
}
