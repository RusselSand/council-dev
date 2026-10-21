import type { State } from '../../domain/council';
import type { Stream } from '../../domain/stream';
import { source } from '../config';
import { ApiError } from '../errors';
import { markStale, type StreamNotes } from './stale';
import { useMutation, type Mutation } from './useMutation';
import { useQuery, type Query } from './useQuery';
import { replaceStream } from './useStreams';

/**
 * Выгрузка потока в заметки — GET /api/councils/<id>/streams/<streamId>/notes: каталог, заметки и решения проекта,
 * статус которых она меняет. state — состояние шага «Документация» сейчас: оно сменилось (шаг начался, поток записали
 * в каталог) — выгрузка перезапрашивается, а до ответа её нет (data — undefined, loading). Перезапрашивается и после
 * «Записать в каталог».
 */
export function useStreamNotes(id: string, streamId: string, state: State): Query<StreamNotes> {
  const query = useQuery(
    async () => ({ council: id, stream: streamId, state, ...(await source.getNotes(id, streamId)) }),
    [id, streamId, state],
    'notes',
  );
  const { data, loading, error } = query;
  const fresh = data?.council === id && data.stream === streamId && data.state === state;
  return { ...query, data: fresh ? data : undefined, loading: loading || (!fresh && error === undefined) };
}

/**
 * Сервер не записал поток: шаг «Документация» ещё не начат (поток на экране устарел) или потока нет — потоки на экране
 * устарели: потока нет — экран потока уводит на другой.
 */
function staleOnRefused(error: unknown) {
  if (!(error instanceof ApiError)) return;
  if (['notes_not_ready', 'not_found'].includes(error.code)) markStale('streams');
  if (error.code === 'notes_not_ready') markStale('notes');
}

/**
 * «Записать в каталог» — POST /api/councils/<id>/streams/<streamId>/notes/approve; ответ — поток. Он сразу встаёт на
 * место прежнего; потоки, выгрузка и список советов перезапрашиваются.
 */
export function useApproveNotes(): Mutation<[id: string, streamId: string], Stream> {
  return useMutation(
    async (id: string, streamId: string) => {
      try {
        return await source.approveNotes(id, streamId);
      } catch (error) {
        staleOnRefused(error);
        throw error;
      }
    },
    (stream, id) => {
      markStale('streams', replaceStream(id, stream));
      markStale('notes');
      markStale('councils');
    },
  );
}
