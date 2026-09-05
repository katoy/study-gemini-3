import { describe, expect, it, vi } from 'vitest';
import { WebSocket } from 'ws';
import {
  broadcast,
  clients,
  handleWsConnection,
  mockGeminiStream,
  streamGeminiResponse,
} from '../../server';

describe('WebSocket handling for Sketch', () => {
  it('handleWsConnection でクライアントが Set に追加され、close で削除される', () => {
    let closeListener: (() => void) | undefined;
    const fakeWs = {
      on: vi.fn((event: string, listener: () => void) => {
        if (event === 'close') closeListener = listener;
      }),
    } as unknown as WebSocket;

    expect(clients.has(fakeWs)).toBe(false);
    handleWsConnection(fakeWs);
    expect(clients.has(fakeWs)).toBe(true);

    closeListener?.();
    expect(clients.has(fakeWs)).toBe(false);
  });

  it('broadcast は OPEN なクライアントにのみ JSON 文字列を送信する', () => {
    const sentOpen: string[] = [];
    const openWs = {
      readyState: WebSocket.OPEN,
      send: vi.fn((msg: string) => sentOpen.push(msg)),
    } as unknown as WebSocket;

    const closedWs = {
      readyState: WebSocket.CLOSED,
      send: vi.fn(),
    } as unknown as WebSocket;

    clients.add(openWs);
    clients.add(closedWs);

    try {
      broadcast({ type: 'SKETCH_UPDATE', elements: [{ id: 'box1' }] });
      expect(sentOpen).toHaveLength(1);
      expect(JSON.parse(sentOpen[0])).toEqual({
        type: 'SKETCH_UPDATE',
        elements: [{ id: 'box1' }],
      });
      expect(closedWs.send).not.toHaveBeenCalled();
    } finally {
      clients.delete(openWs);
      clients.delete(closedWs);
    }
  });
});

describe('streamGeminiResponse for Sketch', () => {
  it('MOCK_GEMINI=1 の場合は実APIを呼ばず mockGeminiStream の内容を流す', async () => {
    const originalEnv = process.env.MOCK_GEMINI;
    process.env.MOCK_GEMINI = '1';

    try {
      const realCaller = vi.fn();
      const chunks: any[] = [];
      for await (const chunk of streamGeminiResponse('test-model', [], {}, realCaller as any)) {
        chunks.push(chunk);
      }

      expect(realCaller).not.toHaveBeenCalled();
      expect(chunks).toHaveLength(4);
      expect(chunks[0].candidates[0].content.parts[0].text).toContain('Sketch');
    } finally {
      process.env.MOCK_GEMINI = originalEnv;
    }
  });

  it('MOCK_GEMINI!=1 の場合は realCall を呼び出しチャンクを順次 yield する', async () => {
    const originalEnv = process.env.MOCK_GEMINI;
    delete process.env.MOCK_GEMINI;

    try {
      const fakeChunks = [{ chunkIndex: 1 }, { chunkIndex: 2 }];
      const realCaller = vi.fn().mockResolvedValue({
        async *[Symbol.asyncIterator]() {
          for (const c of fakeChunks) {
            yield c;
          }
        },
      });

      const chunks: any[] = [];
      for await (const chunk of streamGeminiResponse('gemini-2.5-flash', [{ text: 'hi' }], { temp: 0 }, realCaller as any)) {
        chunks.push(chunk);
      }

      expect(realCaller).toHaveBeenCalledTimes(1);
      expect(chunks).toEqual(fakeChunks);
    } finally {
      process.env.MOCK_GEMINI = originalEnv;
    }
  });
});
