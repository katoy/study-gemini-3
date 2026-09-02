import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { WebSocket } from 'ws';
import { broadcast, clients, handleWsConnection, mockGeminiStream, streamGeminiResponse } from '../../server';

async function drain(gen: AsyncGenerator<any>) {
  const out: any[] = [];
  for await (const chunk of gen) out.push(chunk);
  return out;
}

describe('mockGeminiStream', () => {
  it('テキスト1件と draw_dsl の functionCall を2件返す', async () => {
    const chunks = await drain(mockGeminiStream());
    expect(chunks).toHaveLength(3);
    expect(chunks[0].candidates[0].content.parts[0].text).toBeTypeOf('string');
    expect(chunks[1].candidates[0].content.parts[0].functionCall.id).toBe('mock-fc-1');
    expect(chunks[2].candidates[0].content.parts[0].functionCall.id).toBe('mock-fc-2');
  });
});

describe('streamGeminiResponse', () => {
  const original = process.env.MOCK_GEMINI;
  afterEach(() => {
    if (original === undefined) delete process.env.MOCK_GEMINI;
    else process.env.MOCK_GEMINI = original;
  });

  it('MOCK_GEMINI=1 のときは mockGeminiStream を使う（実APIは呼ばない）', async () => {
    process.env.MOCK_GEMINI = '1';
    let realCallInvoked = false;
    const chunks = await drain(
      streamGeminiResponse('gemini-x', [], {}, async () => {
        realCallInvoked = true;
        throw new Error('should not be called');
      })
    );
    expect(realCallInvoked).toBe(false);
    expect(chunks).toHaveLength(3);
  });

  it('MOCK_GEMINI が無効なら注入した realCall を使う', async () => {
    delete process.env.MOCK_GEMINI;
    const fakeChunks = [{ candidates: [{ content: { parts: [{ text: 'real' }] } }] }];
    const realCall = async (modelName: string) => {
      expect(modelName).toBe('gemini-x');
      return (async function* () {
        for (const c of fakeChunks) yield c;
      })();
    };
    const chunks = await drain(streamGeminiResponse('gemini-x', [], {}, realCall));
    expect(chunks).toEqual(fakeChunks);
  });
});

describe('broadcast / handleWsConnection', () => {
  beforeEach(() => {
    clients.clear();
  });

  it('OPEN状態のクライアントにはメッセージを送信する', () => {
    const sent: string[] = [];
    const fakeClient: any = { readyState: WebSocket.OPEN, send: (msg: string) => sent.push(msg) };
    clients.add(fakeClient);
    broadcast({ type: 'EXCALIDRAW_UPDATE', elements: [] });
    expect(sent).toHaveLength(1);
    expect(JSON.parse(sent[0])).toEqual({ type: 'EXCALIDRAW_UPDATE', elements: [] });
  });

  it('OPEN以外の状態のクライアントには送信しない', () => {
    const sent: string[] = [];
    const fakeClient: any = { readyState: WebSocket.CLOSED, send: (msg: string) => sent.push(msg) };
    clients.add(fakeClient);
    broadcast({ type: 'EXCALIDRAW_UPDATE', elements: [] });
    expect(sent).toHaveLength(0);
  });

  it('接続すると clients に追加され、close で削除される', () => {
    const closeCallbacks: Array<() => void> = [];
    const fakeWs: any = {
      readyState: WebSocket.OPEN,
      on: (event: string, cb: () => void) => {
        if (event === 'close') closeCallbacks.push(cb);
      },
    };
    handleWsConnection(fakeWs);
    expect(clients.has(fakeWs)).toBe(true);

    closeCallbacks.forEach((cb) => cb());
    expect(clients.has(fakeWs)).toBe(false);
  });
});
