import express from 'express';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { WebSocketServer, WebSocket } from 'ws';
import { GoogleGenAI } from '@google/genai';
import { parseDSLToElements, getThinkingConfigFor } from './dsl';

export function extractImageSources(text: string): Array<{ type: 'url' | 'file'; path: string }> {
  if (!text) return [];
  const results: Array<{ type: 'url' | 'file'; path: string }> = [];

  // 1. Web URL 抽出
  const urlRegex = /(https?:\/\/[^\s<>"'{}|\\^`]+)/gi;
  const urlMatches = text.match(urlRegex) || [];
  for (const url of urlMatches) {
    const cleanUrl = url.split('?')[0].toLowerCase();
    if (/\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(cleanUrl) || cleanUrl.includes('image')) {
      results.push({ type: 'url', path: url });
    }
  }

  // 2. ローカル絶対パス抽出 (例: /Users/.../スクリーンショット.png や C:\...)
  const extRegex = /\.(png|jpe?g|webp|gif|bmp|svg)\b/gi;
  let match: RegExpExecArray | null;
  while ((match = extRegex.exec(text)) !== null) {
    const endIdx = match.index + match[0].length;
    // 先頭方向へスラッシュまたは行頭まで遡って探索
    const sub = text.substring(0, endIdx);
    const slashIdx = sub.search(/(?:\/|[a-zA-Z]:\\)/);
    if (slashIdx !== -1) {
      const candidate = sub.substring(slashIdx).trim();
      if (fs.existsSync(candidate)) {
        results.push({ type: 'file', path: candidate });
      }
    }
  }

  return results;
}

export async function loadImageAsBase64(source: { type: 'url' | 'file'; path: string }, timeoutMs = 8000): Promise<{ data: string; mimeType: string } | null> {
  try {
    if (source.type === 'file') {
      const ext = path.extname(source.path).toLowerCase();
      let mimeType = 'image/jpeg';
      if (ext === '.webp') mimeType = 'image/webp';
      else if (ext === '.png') mimeType = 'image/png';
      else if (ext === '.gif') mimeType = 'image/gif';
      else if (ext === '.svg') mimeType = 'image/svg+xml';

      const buffer = await fs.promises.readFile(source.path);
      return { data: buffer.toString('base64'), mimeType };
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const response = await fetch(source.path, {
      signal: controller.signal,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
      }
    });
    clearTimeout(timer);

    if (!response.ok) {
      console.warn(`[ImageFetch] HTTP error ${response.status} for ${source.path}`);
      return null;
    }

    const contentType = response.headers.get('content-type') || '';
    let mimeType = contentType.split(';')[0].trim().toLowerCase();
    if (!mimeType || mimeType === 'application/octet-stream') {
      const lower = source.path.split('?')[0].toLowerCase();
      if (lower.endsWith('.webp')) mimeType = 'image/webp';
      else if (lower.endsWith('.png')) mimeType = 'image/png';
      else if (lower.endsWith('.gif')) mimeType = 'image/gif';
      else if (lower.endsWith('.svg')) mimeType = 'image/svg+xml';
      else mimeType = 'image/jpeg';
    }

    if (!mimeType.startsWith('image/')) {
      console.warn(`[ImageFetch] Response is not an image (${contentType}) for ${source.path}`);
      return null;
    }

    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    return { data: buffer.toString('base64'), mimeType };
  } catch (err: any) {
    console.warn(`[ImageFetch] Error loading image from ${source.path}:`, err?.message || err);
    return null;
  }
}

export const app = express();
app.use(express.json());

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/api/ws' });

// Setup Gemini Client
const apiKey = process.env.GEMINI_API_KEY;
if (!apiKey) {
  console.warn("⚠️ Warning: GEMINI_API_KEY environment variable is not set.");
}

export const ai = new GoogleGenAI({ apiKey: apiKey || 'dummy-key' });

// Store connected clients
export const clients = new Set<WebSocket>();

export function handleWsConnection(ws: WebSocket) {
  clients.add(ws);
  console.log('Client connected to WebSocket (Sketch)');

  ws.on('close', () => {
    clients.delete(ws);
    console.log('Client disconnected from WebSocket (Sketch)');
  });
}

wss.on('connection', handleWsConnection);

export function broadcast(data: any) {
  const message = JSON.stringify(data);
  for (const client of clients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  }
}

// Sketch & Sketch-mcp 互換ツールスキーマ定義
export const sketchTools = [
  {
    functionDeclarations: [
      {
        name: 'draw_dsl',
        description: 'Creates or updates the Sketch diagram canvas using compact programmable DSL commands array. Supports shapes, connectors, labels, artboards, groups, macros (DEF/CALL), loops (REPEAT, GRID), variables (LET), and relative positioning (BELOW, RIGHT_OF).',
        parameters: {
          type: 'OBJECT',
          properties: {
            commands: {
              type: 'ARRAY',
              description: 'List of DSL strings in drawing order. Commands include: "ARTBOARD|id|x|y|w|h|color|name", "GROUP|id|x|y|w|h|name|childIds", "RECT|id|x|y|w|h|color|label|angle|options", "OVAL|id|x|y|w|h|color|label|angle|options", "DIAMOND|id|x|y|w|h|color|label|angle|options", "TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label", "POLYGON|id|x1,y1|x2,y2|x3,y3...|color|label", "LINE|id|fromX,fromY|toX,toY|color|label", "ARROW|id|fromIdOrX,Y|toIdOrX,Y|color|label", "TEXT|id|x|y|fontSize|color|text", "DEL|id1,id2", "LET var = expr", "DEF Name(...) ... END", "CALL Name(...)", "REPEAT count AS $i ... END", "GRID rows, cols AS $r, $c AT x, y SIZE w, h ... END". Relative coords: BELOW(id, gap), RIGHT_OF(id, gap).',
              items: { type: 'STRING' }
            }
          },
          required: ['commands']
        }
      },
      {
        name: 'create_view',
        description: 'Creates or updates Sketch canvas directly with standard element objects.',
        parameters: {
          type: 'OBJECT',
          properties: {
            elements: {
              type: 'ARRAY',
              items: { type: 'OBJECT' }
            }
          },
          required: ['elements']
        }
      },
      {
        name: 'run_sketch_code',
        description: 'Executes Sketch JavaScript API / Sketch-mcp code to manipulate Sketch artboards, layers, and symbols.',
        parameters: {
          type: 'OBJECT',
          properties: {
            code: {
              type: 'STRING',
              description: 'JavaScript code snippet using Sketch API (e.g., sketch.getSelectedDocument()).'
            }
          },
          required: ['code']
        }
      }
    ]
  }
];

type RealGeminiCaller = (modelName: string, contents: any, config: any) => Promise<AsyncIterable<any>>;
const defaultRealCall: RealGeminiCaller = (modelName, contents, config) =>
  ai.models.generateContentStream({ model: modelName, contents, config });

export async function* streamGeminiResponse(
  modelName: string,
  contents: any,
  config: any,
  realCall: RealGeminiCaller = defaultRealCall
): AsyncGenerator<any> {
  if (process.env.MOCK_GEMINI === '1') {
    yield* mockGeminiStream();
    return;
  }
  const responseStream = await realCall(modelName, contents, config);
  for await (const chunk of responseStream) {
    yield chunk;
  }
}

export async function* mockGeminiStream(): AsyncGenerator<any> {
  yield {
    candidates: [{ content: { parts: [{ text: 'モック応答: Sketch フローチャートを描画します。' }] } }]
  };
  // ステップ1: Start 要素
  yield {
    candidates: [{
      content: {
        parts: [{
          functionCall: {
            id: 'mock-fc-1',
            name: 'draw_dsl',
            args: { commands: ['RECT|box1|100|100|140|70|blue|Start'] }
          }
        }]
      }
    }]
  };
  // ステップ2: End 要素
  yield {
    candidates: [{
      content: {
        parts: [{
          functionCall: {
            id: 'mock-fc-2',
            name: 'draw_dsl',
            args: { commands: ['RECT|box2|300|100|140|70|green|End'] }
          }
        }]
      }
    }]
  };
  // ステップ3: Arrow 要素
  yield {
    candidates: [{
      content: {
        parts: [{
          functionCall: {
            id: 'mock-fc-3',
            name: 'draw_dsl',
            args: { commands: ['ARROW|arr1|box1|box2|dark|next'] }
          }
        }]
      }
    }]
  };
}

const SYSTEM_INSTRUCTION_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), 'SYSTEM_INSTRUCTION.md');
export const SYSTEM_INSTRUCTION = fs.readFileSync(SYSTEM_INSTRUCTION_PATH, 'utf-8');


export function createChatHandler(streamFn: typeof streamGeminiResponse = streamGeminiResponse) {
  return async (req: express.Request, res: express.Response) => {
    const { message, history, currentElements } = req.body;

    if (!process.env.GEMINI_API_KEY && process.env.MOCK_GEMINI !== '1') {
      return res.status(400).json({
        error: 'GEMINI_API_KEY environment variable is missing on server.'
      });
    }

    const t0 = Date.now();
    console.log('⏱️ T0 request received (Sketch)');
    let firstFunctionCallLogged = false;
    let firstBroadcastLogged = false;
    const sharedElementMap = new Map<string, any>();

    try {
      const recentHistory = (history || []).slice(-6);
      const formattedHistory = recentHistory.map((msg: any) => ({
        role: msg.role === 'user' ? 'user' : 'model',
        parts: [{ text: msg.content }]
      }));

      let promptText = message;
      if (currentElements && currentElements.length > 0) {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

        const summary = currentElements.map((el: any) => {
          const x = Number(el.x || 0);
          const y = Number(el.y || 0);
          const w = Number(el.width || 100);
          const h = Number(el.height || 50);

          if (x < minX) minX = x;
          if (y < minY) minY = y;
          if (x + w > maxX) maxX = x + w;
          if (y + h > maxY) maxY = y + h;

          return `- [${el.type} id=${el.id}] "${el.text || el.name || ''}" at (${Math.round(x)},${Math.round(y)}) size (${Math.round(w)}x${Math.round(h)})`;
        }).join('\n');

        const suggestedNextY = Math.round(maxY + 60);
        const suggestedNextX = Math.round(maxX + 80);

        promptText += `\n\n[Current Sketch Canvas Elements (Reuse IDs to update without duplicate overlay)]:\n${summary}\n\n` +
          `[Canvas Layout Bounds Guidance]:\n` +
          `- Current Bounds: X [${Math.round(minX)} to ${Math.round(maxX)}], Y [${Math.round(minY)} to ${Math.round(maxY)}]\n` +
          `- Suggested next position: BELOW (X=${Math.round(minX)}, Y=${suggestedNextY}) or RIGHT (X=${suggestedNextX}, Y=${Math.round(minY)})`;
      }

      const imageSources = extractImageSources(message);
      const imageParts: any[] = [];
      for (const source of imageSources) {
        console.log(`🖼️ Detected image input (${source.type}): ${source.path}, loading...`);
        const img = await loadImageAsBase64(source);
        if (img) {
          console.log(`✅ Image loaded successfully (${img.mimeType}, ${img.data.length} chars)`);
          imageParts.push({
            inlineData: {
              data: img.data,
              mimeType: img.mimeType
            }
          });
        }
      }

      const userParts: any[] = [{ text: promptText }, ...imageParts];

      const contents = [
        ...formattedHistory,
        { role: 'user', parts: userParts }
      ];

      const fallbackModels = process.env.GEMINI_MODELS
        ? process.env.GEMINI_MODELS.split(',').map((s) => s.trim()).filter(Boolean)
        : [
            'gemini-3.6-flash',
            'gemini-3.5-flash-lite',
            'gemini-3.1-flash-lite',
            'gemini-flash-latest',
            'gemini-3.8-flash',
            'gemini-3.7-flash',
            'gemini-3.5-flash'
          ];

      const callModelStreamWithRetry = async (modelName: string, retries = 2, delayMs = 1000): Promise<{ replyText: string; toolCallsExecuted: any[] }> => {
        for (let attempt = 1; attempt <= retries; attempt++) {
          try {
            console.log(`Streaming model: ${modelName} (attempt ${attempt}) ⏱️ T1 +${Date.now() - t0}ms`);
            const responseStream = streamFn(modelName, contents, {
              systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
              tools: sketchTools,
              thinkingConfig: getThinkingConfigFor(modelName),
            });

            let replyText = '';
            const toolCallsExecuted: any[] = [];
            const processedFunctionCallIds = new Set<string>();
            let anonymousCallCounter = 0;

            for await (const chunk of responseStream) {
              const candidates = chunk.candidates;
              if (!candidates || candidates.length === 0) continue;

              const parts = candidates[0].content?.parts || [];
              for (const part of parts) {
                if (part.text) {
                  replyText += part.text;
                }
                if (part.functionCall) {
                  const fc = part.functionCall;
                  console.log('Stream Function Call Chunk:', JSON.stringify(fc));

                  if (!firstFunctionCallLogged) {
                    firstFunctionCallLogged = true;
                    console.log(`⏱️ T2 first functionCall detected +${Date.now() - t0}ms`);
                  }

                  const fcId = fc.id || `anon_${anonymousCallCounter++}`;
                  if (processedFunctionCallIds.has(fcId)) {
                    continue;
                  }
                  processedFunctionCallIds.add(fcId);

                  let elementsToBroadcast: any[] = [];

                  if (fc.name === 'draw_dsl' && fc.args?.commands && Array.isArray(fc.args.commands)) {
                    elementsToBroadcast = parseDSLToElements(fc.args.commands as string[], sharedElementMap);
                  } else if (fc.name === 'create_view' && fc.args?.elements) {
                    elementsToBroadcast = fc.args.elements;
                  }

                  if (elementsToBroadcast.length > 0) {
                    if (!firstBroadcastLogged) {
                      firstBroadcastLogged = true;
                      console.log(`⏱️ T3 first broadcast +${Date.now() - t0}ms`);
                    }
                    console.log(`⚡ Stream Broadcasting ${elementsToBroadcast.length} elements for tool: ${fc.name}`);
                    broadcast({
                      type: 'SKETCH_UPDATE',
                      elements: elementsToBroadcast
                    });

                    toolCallsExecuted.push({
                      name: fc.name,
                      args: fc.args
                    });
                  }
                }
              }
            }

            return { replyText, toolCallsExecuted };
          } catch (err: any) {
            const is429 = err.status === 'RESOURCE_EXHAUSTED' || err.message?.includes('429') || err.message?.includes('Quota exceeded');
            if (is429 && attempt < retries) {
              console.warn(`Model ${modelName} hit rate limit (429). Retrying in ${delayMs / 1000}s... (attempt ${attempt}/${retries})`);
              await new Promise((resolve) => setTimeout(resolve, delayMs));
              continue;
            }
            throw err;
          }
        }
        throw new Error(`All retry attempts failed for ${modelName}`);
      };

      let result: { replyText: string; toolCallsExecuted: any[] } | null = null;
      let errors: string[] = [];

      for (const modelName of fallbackModels) {
        try {
          result = await callModelStreamWithRetry(modelName);
          /* v8 ignore next 3 */
          if (result) {
            console.log(`Successfully completed streaming content using model: ${modelName}`);
            break;
          }
        } catch (err: any) {
          console.warn(`Model ${modelName} stream failed:`, err.message);
          errors.push(`${modelName}: ${err.message}`);
        }
      }

      if (!result) {
        throw new Error(`全モデルの呼び出しに失敗しました:\n${errors.join('\n')}`);
      }

      return res.json({
        reply: result.replyText || '（Sketch 図形を作成・更新しました）',
        toolCalls: result.toolCallsExecuted
      });

    } catch (error: any) {
      console.error('Error generating streaming content:', error);
      return res.status(500).json({ error: error.message || 'Internal Server Error' });
    }
  };
}

// Sketch MCP Server (`http://localhost:31126/mcp`) への接続状態確認エンドポイント
export async function getSketchMcpStatus(_req: express.Request, res: express.Response) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1500);
    const resp = await fetch('http://localhost:31126/mcp', {
      signal: controller.signal
    }).catch(() => null);
    clearTimeout(timeoutId);

    if (resp && (resp.ok || resp.status === 405 || resp.status === 400 || resp.status === 200)) {
      return res.json({ connected: true, url: 'http://localhost:31126/mcp' });
    }
    return res.json({ connected: false, url: 'http://localhost:31126/mcp', message: 'Sketch MCP server not running on port 31126' });
  } catch {
    return res.json({ connected: false, url: 'http://localhost:31126/mcp' });
  }
}

app.get('/api/sketch-mcp/status', getSketchMcpStatus);

app.post('/api/chat', createChatHandler());

const PORT = Number(process.env.PORT || 3011);

const isMainModule = process.argv[1] === fileURLToPath(import.meta.url);
/* v8 ignore start */
if (isMainModule) {
  server.listen(PORT, () => {
    console.log(`🚀 Sketch API & WebSocket Server running on http://localhost:${PORT}`);
  });
}
/* v8 ignore stop */
