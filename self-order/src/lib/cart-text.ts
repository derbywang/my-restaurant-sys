import { t } from '../i18n'

/** 「3 items」/「1 item」(English has a singular); Japanese, Chinese and Korean write the same for every number. */
export function cartCountText(count: number): string {
  return t(count === 1 ? 'cart.item' : 'cart.items', { count })
}
