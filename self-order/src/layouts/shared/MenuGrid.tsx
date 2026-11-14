import { formatCurrency } from '@ury/core'
import { t } from '../../i18n'
import type { MenuItem, OrderingCapabilities } from '../../lib/api'
import { cartCountFor, type Cart } from '../../lib/cart'
import { cardPrice } from '../../lib/options'

interface MenuGridProps {
  menu: MenuItem[]
  cart: Cart
  capabilities: OrderingCapabilities | undefined
  onAdd: (item: MenuItem) => void
  /** Tailwind grid classes (columns/gap) — differs between Tablet and Kiosk. */
  gridClassName: string
  /** Tailwind classes for each card — controls touch-target size. */
  cardClassName: string
  imageClassName?: string
}

/** The price on a card: 「¥1,100」, or 「¥1,100〜」 when the card stands for a group of grades. */
export function priceText(item: MenuItem): string {
  const { amount, from } = cardPrice(item)
  return from ? t('price.from', { price: formatCurrency(amount) }) : formatCurrency(amount)
}

/**
 * Category-free scrollable grid of menu items. Shared visual language
 * between TabletLayout and LandscapeKioskLayout — only the sizing classes
 * differ (larger cards, more columns on the kiosk).
 */
function MenuGrid({ menu, cart, capabilities, onAdd, gridClassName, cardClassName, imageClassName }: MenuGridProps) {
  return (
    <div className={gridClassName}>
      {menu.map((item) => (
        <button key={item.item} onClick={() => onAdd(item)} className={cardClassName}>
          {capabilities?.show_item_images && item.item_image && (
            <img
              src={item.item_image}
              alt={item.item_name}
              className={imageClassName ?? 'w-full object-cover'}
            />
          )}
          <div className="flex flex-1 flex-col gap-1 p-3">
            <div className="font-medium">{item.item_name}</div>
            <div className="text-muted-foreground tabular-nums">{priceText(item)}{t('price.incl_tax')}</div>
            {cartCountFor(cart, item.item) > 0 && (
              <div className="mt-1 text-sm font-semibold text-primary">{t('cart.in_cart', { count: cartCountFor(cart, item.item) })}</div>
            )}
          </div>
        </button>
      ))}
    </div>
  )
}

export default MenuGrid
