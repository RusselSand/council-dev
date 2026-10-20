import type { Model } from '../../domain/model';

/** Модели макета (prototype.js, MODELS): provider «codex/gpt-5.6-sol» — провайдер и модель у него. */
export const MODELS: Model[] = [
  { id: 'sol', provider: 'codex', model: 'gpt-5.6-sol', online: true },
  { id: 'fable', provider: 'claude', model: 'claude-fable-5-1', online: true },
  { id: 'opus', provider: 'claude', model: 'claude-opus-5-5', online: false },
];
