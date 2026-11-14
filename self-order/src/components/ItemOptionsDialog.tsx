import { useEffect, useState } from 'react'
import { formatCurrency } from '@ury/core'
import { t } from '../i18n'
import { getProduct, type Grade, type MenuItem, type OptionItem, type OrderingCapabilities, type ProductInfo } from '../lib/api'
import { NOTE_MAX_LENGTH } from '../lib/cart'
import { carryOverAddons, gradesOf, initialGrade, subtotal } from '../lib/options'

export interface ItemOptionsDialogProps {
  /** The card that was touched; null: the dialog is closed. */
  item: MenuItem | null
  session: string | undefined
  /** The language of the session: the names are asked again when it changes. */
  language: string
  capabilities: OrderingCapabilities | undefined
  onAdd: (card: MenuItem, grade: Grade, addons: OptionItem[], qty: number, note: string) => void
  onClose: () => void
}

type Status = 'loading' | 'ready' | 'failed'

/**
 * The dialog of a dish that has grades (「並・上・特上」) or toppings (「大盛り」): the grades are chosen one of, the
 * toppings are ticked, with the price of each with the tax; the quantity is the quantity of the dish and of every
 * topping. 「カートに入れる」 puts the combination in the cart (the cart asks the age first when it is alcohol).
 */
function ItemOptionsDialog({ item, session, language, capabilities, onAdd, onClose }: ItemOptionsDialogProps) {
  const [status, setStatus] = useState<Status>('loading')
  const [product, setProduct] = useState<ProductInfo | null>(null)
  const [gradeCode, setGradeCode] = useState('')
  const [ticked, setTicked] = useState<OptionItem[]>([])
  const [qty, setQty] = useState(1)
  const [note, setNote] = useState('')

  const code = item?.item
  useEffect(() => {
    if (!code || !session) return
    let current = true
    setStatus('loading')
    getProduct(session, code)
      .then((found) => {
        if (!current) return
        setProduct(found)
        setGradeCode(initialGrade(found, code).item_code)
        setTicked([])
        setStatus('ready')
      })
      .catch(() => current && setStatus('failed'))
    return () => {
      current = false
    }
  }, [code, session, language])

  // another dish: start again
  useEffect(() => {
    setQty(1)
    setNote('')
  }, [code])

  if (!item) return null

  const grades = product ? gradesOf(product) : []
  const grade = grades.find((g) => g.item_code === gradeCode) ?? grades[0]
  const total = grade ? subtotal(grade, ticked, qty) : 0

  function chooseGrade(next: Grade) {
    setTicked((current) => carryOverAddons(current, next.addons))
    setGradeCode(next.item_code)
  }

  function toggle(addon: OptionItem) {
    setTicked((current) =>
      current.some((a) => a.item_code === addon.item_code) ? current.filter((a) => a.item_code !== addon.item_code) : [...current, addon],
    )
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 sm:items-center" role="dialog" aria-modal="true">
      <div className="flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl bg-background shadow-lg sm:rounded-2xl">
        <div className="flex-1 overflow-y-auto p-5">
          {capabilities?.show_item_images && (product?.image ?? item.item_image) && (
            <img src={(product?.image ?? item.item_image) as string} alt={item.item_name} className="mb-3 h-40 w-full rounded-lg object-cover" />
          )}
          <h2 className="text-lg font-semibold">{product?.item_name ?? item.item_name}</h2>
          {product?.description && <p className="mt-1 text-sm text-muted-foreground">{product.description}</p>}

          {status === 'loading' && <p className="mt-6 text-center text-sm text-muted-foreground">{t('options.loading')}</p>}
          {status === 'failed' && <p className="mt-6 text-center text-sm text-destructive">{t('options.failed')}</p>}

          {status === 'ready' && grade && (
            <>
              {grades.length > 1 && (
                <fieldset className="mt-4">
                  <legend className="mb-2 text-sm font-medium text-muted-foreground">{t('options.grade_heading')}</legend>
                  <div className="space-y-2">
                    {grades.map((g) => (
                      <label key={g.item_code} className="flex cursor-pointer items-center justify-between rounded-lg border p-3 has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                        <span className="flex items-center gap-3">
                          <input type="radio" name="grade" checked={g.item_code === grade.item_code} onChange={() => chooseGrade(g)} className="h-5 w-5" />
                          <span>{g.item_name}</span>
                        </span>
                        <span className="tabular-nums">{formatCurrency(g.price_incl_tax)}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}

              {grade.addons.length > 0 && (
                <fieldset className="mt-4">
                  <legend className="mb-2 text-sm font-medium text-muted-foreground">{t('options.addon_heading')}</legend>
                  <div className="space-y-2">
                    {grade.addons.map((a) => (
                      <label key={a.item_code} className="flex cursor-pointer items-center justify-between rounded-lg border p-3 has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                        <span className="flex items-center gap-3">
                          <input
                            type="checkbox"
                            checked={ticked.some((x) => x.item_code === a.item_code)}
                            onChange={() => toggle(a)}
                            className="h-5 w-5"
                          />
                          <span>{a.label ?? a.item_name}</span>
                        </span>
                        <span className="tabular-nums">＋{formatCurrency(a.price_incl_tax)}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}

              <div className="mt-4 flex items-center justify-between">
                <span className="text-sm font-medium text-muted-foreground">{t('options.quantity')}</span>
                <span className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setQty((q) => Math.max(1, q - 1))}
                    className="h-10 w-10 rounded-full border text-lg leading-none"
                    aria-label={t('options.quantity_less')}
                  >
                    −
                  </button>
                  <span className="w-6 text-center text-lg tabular-nums">{qty}</span>
                  <button
                    type="button"
                    onClick={() => setQty((q) => Math.min(99, q + 1))}
                    className="h-10 w-10 rounded-full border text-lg leading-none"
                    aria-label={t('options.quantity_more')}
                  >
                    ＋
                  </button>
                </span>
              </div>

              {capabilities?.item_notes_enabled && (
                <input
                  type="text"
                  value={note}
                  maxLength={NOTE_MAX_LENGTH}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder={t('cart.note_placeholder')}
                  aria-label={t('cart.note_label')}
                  className="mt-4 w-full rounded-md border px-3 py-2 text-sm"
                />
              )}
            </>
          )}
        </div>

        <div className="border-t p-4">
          {status === 'ready' && (
            <div className="mb-3 flex items-center justify-between text-sm font-semibold">
              <span>{t('options.subtotal')}</span>
              <span className="tabular-nums">{formatCurrency(total)}</span>
            </div>
          )}
          <div className="flex gap-3">
            <button type="button" onClick={onClose} className="flex-1 rounded-md border py-3 font-medium">
              {t('options.close')}
            </button>
            <button
              type="button"
              disabled={status !== 'ready' || !grade}
              onClick={() => grade && onAdd(item, grade, ticked, qty, note)}
              className="flex-[2] rounded-md bg-primary py-3 font-medium text-primary-foreground disabled:opacity-50"
            >
              {t('options.add_to_cart')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ItemOptionsDialog
