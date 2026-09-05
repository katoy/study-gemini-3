import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import fs from 'fs';
import path from 'path';
import os from 'os';
import {
  loadImageAsBase64,
  streamGeminiResponse,
  mockGeminiStream,
  handleWsConnection,
  broadcast,
  clients,
  getSketchMcpStatus,
  ai
} from '../../server';

describe('server.ts helper functions and endpoints', () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sketch-test-'));
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
    vi.restoreAllMocks();
  });

  it('ローカルファイルの各拡張子 (.png, .webp, .gif, .svg, .jpg) を正しく Base64 読み込みする', async () => {
    const exts = [
      { ext: '.png', mime: 'image/png' },
      { ext: '.webp', mime: 'image/webp' },
      { ext: '.gif', mime: 'image/gif' },
      { ext: '.svg', mime: 'image/svg+xml' },
      { ext: '.jpg', mime: 'image/jpeg' },
    ];

    for (const { ext, mime } of exts) {
      const filePath = path.join(tempDir, `test${ext}`);
      fs.writeFileSync(filePath, 'dummy-image-data');
      const res = await loadImageAsBase64({ type: 'file', path: filePath });
      expect(res).toBeTruthy();
      expect(res?.mimeType).toBe(mime);
      expect(typeof res?.data).toBe('string');
    }
  });

  it('Web URL からの画像読み込み (正常系、404、非画像、例外) を正しく処理する', async () => {
    // 1. 正常系
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'image/png' },
      arrayBuffer: async () => Buffer.from('png-bytes'),
    } as any);

    const okRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/image.png' });
    expect(okRes?.mimeType).toBe('image/png');

    // 2. application/octet-stream からの拡張子フォールバック
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'application/octet-stream' },
      arrayBuffer: async () => Buffer.from('image-bytes'),
    } as any);
    const webpRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/image.webp' });
    expect(webpRes?.mimeType).toBe('image/webp');
    const gifRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/image.gif' });
    expect(gifRes?.mimeType).toBe('image/gif');
    const svgRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/image.svg' });
    expect(svgRes?.mimeType).toBe('image/svg+xml');
    const jpgRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/image.unknown' });
    expect(jpgRes?.mimeType).toBe('image/jpeg');

    // 3. HTTP 404
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    } as any);
    const notFoundRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/404.png' });
    expect(notFoundRes).toBeNull();

    // 4. 非画像 (text/html)
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'text/html' },
    } as any);
    const htmlRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/page.html' });
    expect(htmlRes).toBeNull();

    // 5. fetch 例外
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
    const errRes = await loadImageAsBase64({ type: 'url', path: 'https://example.com/error.png' });
    expect(errRes).toBeNull();

    global.fetch = originalFetch;
  });

  it('streamGeminiResponse で MOCK_GEMINI=1 の場合と通常呼び出しを処理する', async () => {
    const origMock = process.env.MOCK_GEMINI;

    // 1. MOCK_GEMINI=1
    process.env.MOCK_GEMINI = '1';
    const mockChunks: any[] = [];
    for await (const chunk of streamGeminiResponse('test-model', [], {})) {
      mockChunks.push(chunk);
    }
    expect(mockChunks.length).toBeGreaterThan(0);

    // 2. MOCK_GEMINI なし (realCall 引数指定)
    delete process.env.MOCK_GEMINI;
    async function* fakeRealCall() {
      yield { candidates: [{ content: { parts: [{ text: 'Real' }] } }] };
    }
    const realChunks: any[] = [];
    for await (const chunk of streamGeminiResponse('test-model', [], {}, () => Promise.resolve(fakeRealCall() as any))) {
      realChunks.push(chunk);
    }
    expect(realChunks).toHaveLength(1);

    // 3. defaultRealCall のテスト
    ai.models.generateContentStream = vi.fn().mockResolvedValue(fakeRealCall() as any);
    const defaultChunks: any[] = [];
    for await (const chunk of streamGeminiResponse('test-model', [], {})) {
      defaultChunks.push(chunk);
    }
    expect(defaultChunks).toHaveLength(1);

    process.env.MOCK_GEMINI = origMock;
  });

  it('mockGeminiStream が期待通りの3ステップのツール呼び出しを返す', async () => {
    const steps: any[] = [];
    for await (const chunk of mockGeminiStream()) {
      steps.push(chunk);
    }
    expect(steps).toHaveLength(4); // text + 3 tool calls
  });

  it('WebSocket 接続と切断、broadcast が正常に動作する', () => {
    let closeListener: (() => void) | null = null;
    const mockWs = {
      readyState: 1, // OPEN
      send: vi.fn(),
      on: vi.fn().mockImplementation((event, cb) => {
        if (event === 'close') closeListener = cb;
      }),
    } as any;

    handleWsConnection(mockWs);
    expect(clients.has(mockWs)).toBe(true);

    broadcast({ type: 'TEST', data: 123 });
    expect(mockWs.send).toHaveBeenCalled();

    // 切断
    if (closeListener) closeListener();
    expect(clients.has(mockWs)).toBe(false);
  });

  it('sketch-mcp/status エンドポイントのレスポンスをテストする', async () => {
    const originalFetch = global.fetch;

    // 1. 成功ケース
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
    } as any);

    let resData: any = null;
    const req = {} as any;
    const res = {
      json: (data: any) => {
        resData = data;
        return res;
      },
    } as any;

    // 直接実行
    await getSketchMcpStatus(req, res);
    expect(resData).toEqual({ connected: true, url: 'http://localhost:31126/mcp' });

    // 2. 失敗ケース (サーバー未起動)
    global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));
    await getSketchMcpStatus(req, res);
    expect(resData).toEqual({
      connected: false,
      url: 'http://localhost:31126/mcp',
      message: 'Sketch MCP server not running on port 31126'
    });

    // 3. catch ブロック (res.json で例外発生時)
    let throwOnce = true;
    const resThrow = {
      json: (data: any) => {
        if (throwOnce) {
          throwOnce = false;
          throw new Error('JSON error');
        }
        resData = data;
        return resThrow;
      }
    } as any;
    await getSketchMcpStatus(req, resThrow);
    expect(resData).toEqual({ connected: false, url: 'http://localhost:31126/mcp' });

    global.fetch = originalFetch;
  });
});
