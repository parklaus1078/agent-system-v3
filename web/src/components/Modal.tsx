import { useEffect, type ReactNode } from 'react';
import './Modal.css';

/** Centered dialog over a dimmed backdrop. Esc / backdrop click closes — unless
 *  `dismissable` is false (e.g. while a request is in flight), so the user can't
 *  accidentally close it mid-plan and re-trigger a duplicate request. */
export function Modal({
  onClose,
  dismissable = true,
  children,
}: {
  onClose: () => void;
  dismissable?: boolean;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && dismissable) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, dismissable]);

  return (
    <div className="modal-backdrop" onMouseDown={dismissable ? onClose : undefined}>
      <div className="modal" role="dialog" aria-modal="true" onMouseDown={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}
