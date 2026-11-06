// The red notice at the top of the page ("通信できませんでした…"). A failure shows it; the next request that
// succeeds takes it away (the problem is over, the page works again); the guest can also close it.

export type NoticeAction = { type: 'fail'; text: string } | { type: 'ok' } | { type: 'dismiss' }

export function noticeReducer(current: string | null, action: NoticeAction): string | null {
  switch (action.type) {
    case 'fail':
      return action.text
    case 'ok':
    case 'dismiss':
      return null
    default:
      return current
  }
}
