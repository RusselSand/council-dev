import { useEffect, useId, useRef, type MouseEvent, type ReactNode, type SyntheticEvent } from 'react';
import { IconButton } from '../IconButton';
import styles from './Dialog.module.css';

interface DialogProps {
  title: string;
  /** Подпись кнопки «×» для экранных читалок: «Закрыть». */
  closeLabel: string;
  /** Закрыть окно: «×», клик мимо окна, Esc. */
  onClose: () => void;
  /** Кнопки внизу справа. */
  actions: ReactNode;
  children: ReactNode;
}

/**
 * Окно поверх страницы: страница под ним затемнена и размыта. Вверху — заголовок и «×», внизу справа — кнопки.
 * Закрывается «×», кликом мимо окна и Esc. Показано, пока стоит в дереве.
 */
export function Dialog({ title, closeLabel, onClose, actions, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  // Esc: окно закрывает тот, кто его показал, — убирает из дерева.
  const cancel = (event: SyntheticEvent) => {
    event.preventDefault();
    onClose();
  };
  // Клик мимо окна попадает в сам <dialog> — он растянут на всю страницу. Нажали в окне, а отпустили мимо (выделяли
  // текст в поле) — это не клик мимо окна.
  const pressedOutside = useRef(false);
  const press = (event: MouseEvent) => {
    pressedOutside.current = event.target === event.currentTarget;
  };
  const clickOutside = (event: MouseEvent) => {
    if (pressedOutside.current && event.target === event.currentTarget) onClose();
  };

  return (
    <dialog
      ref={ref}
      className={styles.overlay}
      aria-labelledby={titleId}
      onCancel={cancel}
      onMouseDown={press}
      onClick={clickOutside}
    >
      <div className={styles.panel}>
        <div className={styles.head}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          <IconButton label={closeLabel} onClick={onClose}>
            ×
          </IconButton>
        </div>
        {children}
        <div className={styles.actions}>{actions}</div>
      </div>
    </dialog>
  );
}
