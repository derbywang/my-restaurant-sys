import { Volume2, VolumeX } from 'lucide-react';
import { cn } from '@ury/ui';
import { t } from '../i18n';
import { useServiceRequestStore } from '../store/service-request-store';

/**
 * The switch of the sound of the 「お会計」 calls, always in sight: in the top bar of the register and of the captain's
 * screens (the same switch as the speaker button of the banner). A speaker, not a bell: the bell on a table card means the
 * call itself. Turning the sound on rings once.
 */
const SoundToggle: React.FC<{ className?: string }> = ({ className }) => {
  const muted = useServiceRequestStore((state) => state.muted);
  const toggleMuted = useServiceRequestStore((state) => state.toggleMuted);
  const label = muted ? t('service_request.unmute') : t('service_request.mute');

  return (
    <button
      type="button"
      data-testid="sound-toggle"
      onClick={toggleMuted}
      title={label}
      aria-label={label}
      aria-pressed={muted}
      className={cn('shrink-0 rounded p-2 text-gray-700 hover:bg-gray-100', muted && 'text-gray-400', className)}
    >
      {muted ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
    </button>
  );
};

export default SoundToggle;
