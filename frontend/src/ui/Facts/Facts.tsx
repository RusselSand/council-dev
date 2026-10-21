import { Fragment, type ReactNode } from 'react';
import styles from './Facts.module.css';

export interface Fact {
  /** Подпись слева; она же ключ строки — в одном списке подписи разные. */
  label: string;
  value: ReactNode;
}

/**
 * sm — теснее, подписи узкие, текст мягче: «почему» и «цена» на карточке варианта; md — просторнее, подписи шире:
 * решение (ADR) — «контекст», «решение», «почему», «последствия»; xs — мельче, подписи — номера моноширинным и тёмным:
 * решения, которые реализует итог, — «ADR-0046 — что меняет».
 */
export type FactsSize = 'xs' | 'sm' | 'md';

/** Строки «подпись — значение»: подписи мелко слева, значения справа. */
export function Facts({ facts, size = 'sm' }: { facts: Fact[]; size?: FactsSize }) {
  return (
    <dl className={`${styles.facts} ${styles[size]}`}>
      {facts.map((fact) => (
        <Fragment key={fact.label}>
          <dt className={styles.label}>{fact.label}</dt>
          <dd className={styles.value}>{fact.value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
