import { formatCurrency } from '@ury/core'
import { useState } from 'react'
import { t } from '../i18n'
import type { CartEntry } from '../lib/cart'
import CartNote from './CartNote'

interface CartLineRowProps {
  entry: CartEntry
  notesEnabled: boolean
  onIncrement: (key: string) => void
  onDecrement: (key: string) => void
  onNote: (key: string, note: string) => void
  /** Tailwind classes of the − and + buttons (the layouts differ in size). */
  buttonClassName: string
}

/**
 * A line of the cart: the dish (the grade chosen) with the toppings under it, how many, and the note. The toppings
 * are as many as the dish, so there is one pair of buttons for the whole line.
 */
function CartLineRow({ entry, notesEnabled, onIncrement, onDecrement, onNote, buttonClassName }: CartLineRowProps) {
  // the note box is folded until the guest asks for it (a box under every line made the cart as high as the menu); a note
  // that is already written stays in view
  const [noteOpen, setNoteOpen] = useState(false)
  return (
    <li>
      <div className="flex items-center justify-between gap-2">
        <span className="flex-1">{entry.item.item_name}</span>
        <span className="flex items-center gap-2">
          <button onClick={() => onDecrement(entry.key)} className={buttonClassName} aria-label={`Remove one ${entry.item.item_name}`}>
            −
          </button>
          <span className="w-4 text-center">{entry.qty}</span>
          <button onClick={() => onIncrement(entry.key)} className={buttonClassName} aria-label={`Add one more ${entry.item.item_name}`}>
            +
          </button>
        </span>
      </div>
      {entry.addons.length > 0 && (
        <ul className="ml-3 mt-0.5 space-y-0.5 text-xs text-muted-foreground">
          {entry.addons.map((a) => (
            <li key={a.item} className="flex justify-between gap-2">
              <span>{t('cart.addon_line', { label: a.label })}</span>
              <span className="tabular-nums">＋{formatCurrency(a.price_incl_tax)}</span>
            </li>
          ))}
        </ul>
      )}
      {notesEnabled && (noteOpen || entry.note !== '') && (
        <CartNote itemName={entry.item.item_name} value={entry.note} onChange={(value) => onNote(entry.key, value)} />
      )}
      {notesEnabled && !noteOpen && entry.note === '' && (
        <button type="button" onClick={() => setNoteOpen(true)} className="mt-0.5 text-xs text-primary underline">
          {t('cart.note_add')}
        </button>
      )}
    </li>
  )
}

export default CartLineRow
