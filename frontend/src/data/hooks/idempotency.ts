/** Ключ одного нового объекта — для заголовка Idempotency-Key: 32 случайные шестнадцатеричные цифры. */
export const newKey = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
