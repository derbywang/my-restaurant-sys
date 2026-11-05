import { t } from '../i18n'
import { NOTE_MAX_LENGTH } from '../lib/cart'

interface CartNoteProps {
  itemName: string
  value: string
  onChange: (value: string) => void
}

/** The note for the kitchen of one dish in the cart ("no wasabi"); shown where the restaurant takes notes. */
function CartNote({ itemName, value, onChange }: CartNoteProps) {
  return (
    <input
      type="text"
      value={value}
      maxLength={NOTE_MAX_LENGTH}
      onChange={(event) => onChange(event.target.value)}
      placeholder={t('cart.note_placeholder')}
      aria-label={`${t('cart.note_label')}: ${itemName}`}
      title={t('cart.note_hint')}
      className="mt-1 w-full rounded-md border px-2 py-1 text-xs"
    />
  )
}

export default CartNote
