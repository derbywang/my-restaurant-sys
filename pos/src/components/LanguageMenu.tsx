import { LanguageMenu as UiLanguageMenu } from '@ury/ui';
import { MENU_LANGUAGES, setStaffLanguage } from '@ury/core';
import { t, getActiveLanguage } from '../i18n';

interface LanguageMenuProps {
  /** Render the list in the normal flow (for use inside another menu) instead of a floating panel. */
  inline?: boolean;
}

/** Staff language switcher: saves User.language and reloads (see `setStaffLanguage`). */
const LanguageMenu = ({ inline = false }: LanguageMenuProps) => (
  <UiLanguageMenu
    languages={MENU_LANGUAGES}
    activeLanguage={getActiveLanguage()}
    label={t('language.label')}
    errorMessage={t('language.change_failed')}
    onSelect={setStaffLanguage}
    inline={inline}
  />
);

export default LanguageMenu;
