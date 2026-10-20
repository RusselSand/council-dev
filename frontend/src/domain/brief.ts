/** Текст ввода совета: мысли человека в свободной форме, из которых совет нарезает фрагменты. */
export interface Brief {
  /** Как его написал человек; пустая строка — текста нет. */
  text: string;
}

/** Сколько слов в тексте — как в макете: куски текста между пробелами и переносами строк. */
export function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}
