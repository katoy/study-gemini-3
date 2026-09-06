import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { promises as dnsPromises } from 'dns';
import { fetchImageAsInlineData, createChatHandler, isSafeExternalUrl, isHostnameResolutionSafe } from '../../server';

// dns.lookup を実際に呼ばず、ドメイン名の解決結果を単体テストから制御できるようにする
vi.mock('dns', () => ({
  promises: {
    lookup: vi.fn(),
  },
}));

describe('server.ts helper functions and handlers', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    // プレーンな vi.fn() は vi.restoreAllMocks()（下記 afterEach）では呼び出し履歴がクリアされないため、
    // 各テスト開始時に明示的にリセットし、パブリックIPを返すデフォルト実装を再設定しておく
    vi.mocked(dnsPromises.lookup).mockReset().mockResolvedValue([{ address: '93.184.216.34', family: 4 }]);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('content-type が image/* の画像を正しく inlineData に変換する', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'image/png; charset=utf-8' },
      arrayBuffer: async () => Buffer.from('png-data'),
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/test.png');
    expect(res).toBeTruthy();
    expect(res?.inlineData.mimeType).toBe('image/png');
    expect(res?.inlineData.data).toBe(Buffer.from('png-data').toString('base64'));
  });

  it('content-type が非画像で URL 拡張子 (.webp, .png, .jpg, .jpeg, .svg) から推測する', async () => {
    const urls = [
      { url: 'https://example.com/pic.webp', expected: 'image/webp' },
      { url: 'https://example.com/pic.png', expected: 'image/png' },
      { url: 'https://example.com/pic.jpg', expected: 'image/jpeg' },
      { url: 'https://example.com/pic.jpeg', expected: 'image/jpeg' },
      { url: 'https://example.com/pic.svg', expected: 'image/svg+xml' },
    ];

    for (const item of urls) {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: { get: () => 'application/octet-stream' },
        arrayBuffer: async () => Buffer.from('img-data'),
      } as any);

      const res = await fetchImageAsInlineData(item.url);
      expect(res?.inlineData.mimeType).toBe(item.expected);
    }
  });

  it('非画像URL (HTMLや不明な拡張子) の場合は null を返す', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => 'text/html' },
      arrayBuffer: async () => Buffer.from('html'),
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/page.html');
    expect(res).toBeNull();
  });

  it('HTTPレスポンスが ok でない場合は null を返す', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/notfound.png');
    expect(res).toBeNull();
  });

  it('fetch がエラーまたはタイムアウトで abort された場合は null を返す', async () => {
    global.fetch = vi.fn().mockImplementation((_, init: any) => {
      return new Promise((__, reject) => {
        if (init?.signal) {
          init.signal.addEventListener('abort', () => reject(new Error('Aborted')));
        }
      });
    });

    const res = await fetchImageAsInlineData('https://example.com/timeout.png', 10);
    expect(res).toBeNull();
  });

  it('GEMINI_MODELS 環境変数が設定されている場合のフォールバックモデル読み込み', async () => {
    const origModels = process.env.GEMINI_MODELS;
    const origKey = process.env.GEMINI_API_KEY;
    try {
      process.env.GEMINI_MODELS = ' custom-model-1, custom-model-2 ';
      process.env.GEMINI_API_KEY = 'test-key';

      let calledModel = '';
      const dummyStream = vi.fn().mockImplementation((modelName: string) => {
        calledModel = modelName;
        return (async function* () {
          yield { candidates: [{ content: { parts: [{ text: 'response' }] } }] };
        })();
      });

      const handler = createChatHandler(dummyStream as any);
      const req = {
        body: { message: 'hello' }
      } as any;
      let jsonResponse: any = null;
      const res = {
        status: vi.fn().mockReturnThis(),
        json: (data: any) => { jsonResponse = data; }
      } as any;

      await handler(req, res);
      expect(calledModel).toBe('custom-model-1');
      expect(jsonResponse.reply).toBe('response');
    } finally {
      if (origModels !== undefined) process.env.GEMINI_MODELS = origModels;
      else delete process.env.GEMINI_MODELS;
      if (origKey !== undefined) process.env.GEMINI_API_KEY = origKey;
      else delete process.env.GEMINI_API_KEY;
    }
  });

  it('ユーザーメッセージに画像URLが含まれる場合に自動で inlineData を取得してモデルに渡す', async () => {
    const origKey = process.env.GEMINI_API_KEY;
    try {
      process.env.GEMINI_API_KEY = 'test-key';

      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: { get: () => 'image/png' },
        arrayBuffer: async () => Buffer.from('img-bytes'),
      } as any);

      let passedContents: any[] = [];
      const dummyStream = vi.fn().mockImplementation((_model: string, contents: any[]) => {
        passedContents = contents;
        return (async function* () {
          yield { candidates: [{ content: { parts: [{ text: 'image analyzed' }] } }] };
        })();
      });

      const handler = createChatHandler(dummyStream as any);
      const req = {
        body: { message: '図を見てください: https://example.com/diag.png' }
      } as any;
      let jsonResponse: any = null;
      const res = {
        status: vi.fn().mockReturnThis(),
        json: (data: any) => { jsonResponse = data; }
      } as any;

      await handler(req, res);
      expect(jsonResponse.reply).toBe('image analyzed');
      const lastUserContent = passedContents.find((c) => c.role === 'user');
      expect(lastUserContent.parts.length).toBe(2);
      expect(lastUserContent.parts[1].inlineData.mimeType).toBe('image/png');
    } finally {
      if (origKey !== undefined) process.env.GEMINI_API_KEY = origKey;
      else delete process.env.GEMINI_API_KEY;
    }
  });

  it('headers.get("content-type") が null の場合でも拡張子から画像形式を判定する', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => null },
      arrayBuffer: async () => Buffer.from('img-bytes'),
    } as any);

    const res = await fetchImageAsInlineData('https://example.com/pic.png');
    expect(res?.inlineData.mimeType).toBe('image/png');
  });

  it('message が空文字列の場合および Quota exceeded エラーのリトライを処理する', async () => {
    const origKey = process.env.GEMINI_API_KEY;
    try {
      process.env.GEMINI_API_KEY = 'test-key';
      let attempts = 0;
      const dummyStream = vi.fn().mockImplementation(() => {
        attempts++;
        if (attempts === 1) {
          return (async function* () {
            yield (null as any);
            throw new Error('Quota exceeded');
          })();
        }
        return (async function* () {
          yield { candidates: [{ content: { parts: [{ text: 'retry success' }] } }] };
        })();
      });

      const handler = createChatHandler(dummyStream as any);
      const req = { body: { message: '' } } as any;
      let jsonResponse: any = null;
      const res = {
        status: vi.fn().mockReturnThis(),
        json: (data: any) => { jsonResponse = data; }
      } as any;

      await handler(req, res);
      expect(jsonResponse.reply).toBe('retry success');
    } finally {
      if (origKey !== undefined) process.env.GEMINI_API_KEY = origKey;
      else delete process.env.GEMINI_API_KEY;
    }
  });

  describe('isSafeExternalUrl', () => {
    it('正常なパブリックURLを許可する', () => {
      expect(isSafeExternalUrl('https://example.com/image.png')).toBe(true);
      expect(isSafeExternalUrl('http://cdn.excalidraw.com/test.jpg')).toBe(true);
      expect(isSafeExternalUrl('https://8.8.8.8/pic.png')).toBe(true);
    });

    it('http/https 以外のスキームを拒否する', () => {
      expect(isSafeExternalUrl('ftp://example.com/image.png')).toBe(false);
      expect(isSafeExternalUrl('file:///etc/passwd')).toBe(false);
      expect(isSafeExternalUrl('javascript:alert(1)')).toBe(false);
      expect(isSafeExternalUrl('not-a-valid-url')).toBe(false);
    });

    it('ローカルホストドメインを拒否する', () => {
      expect(isSafeExternalUrl('http://localhost/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://app.localhost/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://test.local/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://backend.internal/test.png')).toBe(false);
    });

    it('プライベートIPv4およびリンクローカルを拒否する', () => {
      expect(isSafeExternalUrl('http://127.0.0.1/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://10.0.0.1/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://172.16.0.1/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://172.31.255.255/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://192.168.1.1/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://169.254.169.254/latest/meta-data/')).toBe(false);
      expect(isSafeExternalUrl('http://0.0.0.0/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://999.999.999.999/test.png')).toBe(false);
    });

    it('IPv6 ループバックやプライベートレンジを拒否する', () => {
      expect(isSafeExternalUrl('http://[::1]/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://[fe80::1]/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://[fc00::1]/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://[fd00::1]/test.png')).toBe(false);
    });

    it('IPv4写像IPv6アドレス (::ffff:127.0.0.1 等) を再帰的に検証して拒否する', () => {
      expect(isSafeExternalUrl('http://[::ffff:127.0.0.1]/test.png')).toBe(false);
      expect(isSafeExternalUrl('http://[::ffff:8.8.8.8]/test.png')).toBe(true);
    });

    it('fetchImageAsInlineData で SSRF ブロック時に null を返す', async () => {
      const res = await fetchImageAsInlineData('http://127.0.0.1:8080/secret.png');
      expect(res).toBeNull();
    });
  });

  describe('isHostnameResolutionSafe（DNSリバインディング対策）', () => {
    it('ドメイン名がパブリックIPに解決される場合は許可する', async () => {
      vi.mocked(dnsPromises.lookup).mockResolvedValue([{ address: '93.184.216.34', family: 4 }]);
      expect(await isHostnameResolutionSafe('https://example.com/image.png')).toBe(true);
    });

    it('ドメイン名がプライベート/内部IPに解決される場合は拒否する', async () => {
      vi.mocked(dnsPromises.lookup).mockResolvedValue([{ address: '169.254.169.254', family: 4 }]);
      expect(await isHostnameResolutionSafe('https://attacker-controlled.example/meta.png')).toBe(false);
    });

    it('IPリテラルのURLはDNS解決を行わずに許可する', async () => {
      expect(await isHostnameResolutionSafe('https://8.8.8.8/pic.png')).toBe(true);
      expect(dnsPromises.lookup).not.toHaveBeenCalled();
    });

    it('DNS解決に失敗した場合は拒否する', async () => {
      vi.mocked(dnsPromises.lookup).mockRejectedValue(new Error('ENOTFOUND'));
      expect(await isHostnameResolutionSafe('https://not-exist.example/pic.png')).toBe(false);
    });

    it('DNS解決結果が空配列の場合は拒否する', async () => {
      vi.mocked(dnsPromises.lookup).mockResolvedValue([]);
      expect(await isHostnameResolutionSafe('https://no-address.example/pic.png')).toBe(false);
    });

    it('fetchImageAsInlineData はドメイン名が内部IPに解決される場合 null を返す', async () => {
      vi.mocked(dnsPromises.lookup).mockResolvedValue([{ address: '10.0.0.5', family: 4 }]);
      const res = await fetchImageAsInlineData('https://attacker-controlled.example/meta.png');
      expect(res).toBeNull();
    });
  });

  describe('fetchImageAsInlineData のリダイレクト処理', () => {
    it('安全なURLへのリダイレクトは検証の上で追従する', async () => {
      global.fetch = vi.fn()
        .mockResolvedValueOnce({
          status: 302,
          ok: false,
          headers: { get: (k: string) => (k === 'location' ? 'https://cdn.example.com/final.png' : null) },
        } as any)
        .mockResolvedValueOnce({
          status: 200,
          ok: true,
          headers: { get: () => 'image/png' },
          arrayBuffer: async () => Buffer.from('redirected-data'),
        } as any);

      const res = await fetchImageAsInlineData('https://example.com/redirect.png');
      expect(res?.inlineData.data).toBe(Buffer.from('redirected-data').toString('base64'));
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    it('プライベートIPへのリダイレクトはブロックする', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        status: 302,
        ok: false,
        headers: { get: (k: string) => (k === 'location' ? 'http://169.254.169.254/latest/meta-data/' : null) },
      } as any);

      const res = await fetchImageAsInlineData('https://example.com/redirect.png');
      expect(res).toBeNull();
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it('Locationヘッダのないリダイレクトは null を返す', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        status: 302,
        ok: false,
        headers: { get: () => null },
      } as any);

      const res = await fetchImageAsInlineData('https://example.com/redirect.png');
      expect(res).toBeNull();
    });

    it('リダイレクトが上限回数を超えた場合は null を返す', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        status: 302,
        ok: false,
        headers: { get: (k: string) => (k === 'location' ? 'https://example.com/loop.png' : null) },
      } as any);

      const res = await fetchImageAsInlineData('https://example.com/loop.png');
      expect(res).toBeNull();
    });
  });
});
