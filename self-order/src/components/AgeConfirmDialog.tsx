import { t } from '../i18n'
import type { MenuItem } from '../lib/api'

interface AgeConfirmDialogProps {
  item: MenuItem | null
  onAnswer: (yes: boolean) => void | Promise<void>
}

/** 「20歳以上ですか？」 for alcohol: 「はい」 puts the dish in the cart, 「いいえ」 does not. Asked once per session. */
function AgeConfirmDialog({ item, onAnswer }: AgeConfirmDialogProps) {
  if (!item) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6" role="dialog" aria-modal="true">
      <div className="w-full max-w-sm rounded-xl bg-background p-5 shadow-lg">
        <p className="text-sm text-muted-foreground">{item.item_name}</p>
        <h2 className="mt-1 text-lg font-semibold">{t('age.question')}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t('age.note')}</p>
        <div className="mt-5 flex gap-3">
          <button onClick={() => onAnswer(false)} className="flex-1 rounded-md border py-3 font-medium">
            {t('age.no')}
          </button>
          <button onClick={() => onAnswer(true)} className="flex-1 rounded-md bg-primary py-3 font-medium text-primary-foreground">
            {t('age.yes')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default AgeConfirmDialog
