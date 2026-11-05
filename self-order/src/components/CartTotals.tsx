import { formatCurrency } from '@ury/core'
import { t } from '../i18n'
import type { CartPreview } from '../lib/api'

/** The amount for the cart row: "合計（税込） ¥2,200"; three dots until the server has answered. */
export function cartTotalText(total: number | null, failed = false): string {
  if (failed) return `${t('cart.total_incl_tax')} —`
  return `${t('cart.total_incl_tax')} ${total === null ? '…' : formatCurrency(total)}`
}

interface CartTotalsProps {
  preview: CartPreview | null
  /** The server could not give the total: say so, do not leave the dots. */
  failed?: boolean
}

/** What the cart comes to, with the tax, as the server worked it out: what was ordered already, each rate's tax. */
function CartTotals({ preview, failed = false }: CartTotalsProps) {
  if (failed) return <p className="mb-2 text-xs text-destructive">{t('errors.total_failed')}</p>
  if (!preview) return null
  return (
    <div className="mb-2 space-y-0.5 text-xs text-muted-foreground">
      {preview.ordered_total > 0 && (
        <div className="flex justify-between">
          <span>{t('cart.ordered')}</span>
          <span className="tabular-nums">{formatCurrency(preview.ordered_total)}</span>
        </div>
      )}
      {preview.taxes.map((tax) => (
        <div key={tax.rate} className="flex justify-between">
          <span>{t('cart.tax_line', { rate: tax.rate, base: formatCurrency(tax.taxable_amount) })}</span>
          <span className="tabular-nums">{formatCurrency(tax.tax_amount)}</span>
        </div>
      ))}
    </div>
  )
}

export default CartTotals
