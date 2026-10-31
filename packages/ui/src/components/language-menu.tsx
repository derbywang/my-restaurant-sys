import { useEffect, useRef, useState } from 'react';
import { Check, Globe } from 'lucide-react';
import { Button } from './button';
import { showToast } from './toast';
import { cn } from '../lib/cn';

export interface LanguageMenuProps {
  /** Languages to offer, as { code: display name }, in display order. */
  languages: Record<string, string>;
  activeLanguage: string;
  /** Accessible name and trigger text for the menu ("Language"). */
  label: string;
  /** Toast shown when `onSelect` rejects. */
  errorMessage: string;
  /** Persist the choice; the app is expected to reload on success. */
  onSelect: (code: string) => Promise<void>;
  /** Render the list in the normal flow (for use inside another menu) instead of a floating panel. */
  inline?: boolean;
}

/**
 * Language switcher. Presentational only: it does not know how or where the
 * choice is saved (see `setStaffLanguage` in @ury/core), so @ury/ui stays
 * independent of @ury/core.
 */
export const LanguageMenu = ({
  languages,
  activeLanguage,
  label,
  errorMessage,
  onSelect,
  inline = false,
}: LanguageMenuProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

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
      await onSelect(code);
    } catch (error) {
      console.error('Failed to change language:', error);
      showToast.error(errorMessage);
      setIsSaving(false);
    }
  };

  const options = (
    <ul role="listbox" aria-label={label}>
      {Object.entries(languages).map(([code, name]) => (
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
            {name}
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
          {label}
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
        aria-label={label}
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
