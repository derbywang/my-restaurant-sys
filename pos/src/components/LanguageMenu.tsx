import { useEffect, useRef, useState } from 'react';
import { Check, Globe } from 'lucide-react';
import { Button, cn, showToast } from '@ury/ui';
import { call } from '@ury/core';
import { t, getActiveLanguage } from '../i18n';
import { MENU_LANGUAGES } from '../i18n/config';

interface LanguageMenuProps {
  /** Render the language list in the normal flow (for use inside another menu) instead of a floating panel. */
  inline?: boolean;
}

/**
 * Staff language switcher. The choice is saved on the logged-in user's
 * User.language (so it applies to /app, /ury and /pos alike) and the page is
 * reloaded to pick it up from `frappe.boot.lang`.
 */
const LanguageMenu = ({ inline = false }: LanguageMenuProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const activeLanguage = getActiveLanguage();

  useEffect(() => {
    if (!isOpen || inline) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, inline]);

  const handleSelect = async (code: string) => {
    if (isSaving) return;
    if (code === activeLanguage) {
      setIsOpen(false);
      return;
    }
    setIsSaving(true);
    try {
      await call.post('ury.ury.api.language.set_staff_language', { lang: code });
      window.location.reload();
    } catch (error) {
      console.error('Failed to change language:', error);
      showToast.error(t('language.change_failed'));
      setIsSaving(false);
    }
  };

  const options = (
    <ul role="listbox" aria-label={t('language.label')}>
      {Object.entries(MENU_LANGUAGES).map(([code, label]) => (
        <li key={code} role="option" aria-selected={code === activeLanguage}>
          <Button
            variant="ghost"
            className={cn(
              'flex h-auto w-full justify-between rounded-none px-4 py-2.5 text-sm font-normal text-gray-700 hover:bg-gray-100',
              inline && 'ps-11'
            )}
            onClick={() => handleSelect(code)}
            disabled={isSaving}
            lang={code}
          >
            {label}
            {code === activeLanguage && <Check className="h-4 w-4 shrink-0" />}
          </Button>
        </li>
      ))}
    </ul>
  );

  if (inline) {
    return (
      <div>
        <Button
          variant="ghost"
          className="flex justify-start items-center w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors"
          onClick={() => setIsOpen(!isOpen)}
          aria-expanded={isOpen}
        >
          <Globe className="w-4 h-4 me-3" />
          {t('language.label')}
        </Button>
        {isOpen && options}
      </div>
    );
  }

  return (
    <div className="relative shrink-0" ref={menuRef}>
      <Button
        variant="ghost"
        size="icon"
        className="h-9 w-9 shrink-0 text-gray-600 hover:text-gray-900"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={t('language.label')}
        aria-expanded={isOpen}
      >
        <Globe className="h-5 w-5" />
      </Button>
      {isOpen && (
        <div className="absolute end-0 top-full z-50 mt-1 w-44 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
          {options}
        </div>
      )}
    </div>
  );
};

export default LanguageMenu;
