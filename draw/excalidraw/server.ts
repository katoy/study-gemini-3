import express from 'express';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { WebSocketServer, WebSocket } from 'ws';
import { GoogleGenAI } from '@google/genai';
import { parseDSLToElements, getThinkingConfigFor } from './dsl';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(express.json());

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/api/ws' });

// Setup Gemini Client
const apiKey = process.env.GEMINI_API_KEY;
if (!apiKey) {
  console.warn("⚠️ Warning: GEMINI_API_KEY environment variable is not set.");
}

const ai = new GoogleGenAI({ apiKey: apiKey || 'dummy-key' });

// Store connected clients
export const clients = new Set<WebSocket>();

// wss.on('connection') のハンドラ本体。単体テストから直接呼べるよう export している
export function handleWsConnection(ws: WebSocket) {
  clients.add(ws);
  console.log('Client connected to WebSocket');

  ws.on('close', () => {
    clients.delete(ws);
    console.log('Client disconnected from WebSocket');
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

// Simple & Robust DSL Tool schema definition for Gemini function calling
const excalidrawTools = [
  {
    functionDeclarations: [
      {
        name: 'draw_dsl',
        description: 'Creates or updates the diagram canvas using compact DSL commands array. When drawing, include ALL components (shapes, connectors, labels) ordered logically (foundations -> connections -> details). Supports loops, components, auto-layout, and Excalidraw MCP operations.',
        parameters: {
          type: 'OBJECT',
          properties: {
            commands: {
              type: 'ARRAY',
              description: 'List of DSL strings in drawing order. Programmable: "LET|var=val", "DEF|name(p1,p2)|cmd1;cmd2", "CALL|name|arg1|arg2", "FOR|i|start..end|cmd", "REPEAT|count|cmd", "CONNECT|a -> b -> c|color|label|styles", "ROW|x,y,gap|cmd1;cmd2", "COL|x,y,gap|cmd1;cmd2". MCP & Ops: "GROUP|groupId|id1,id2", "UNGROUP|id1,id2", "LINK|id|url", "FRONT|id1,id2", "BACK|id1,id2". Creation: "CHESSBOARD|id|x|y|size|lightColor|darkColor|pieces|styles", "GRID|id|x|y|w|h|rows,cols|color1|color2|styles", "RECT|id|x|y|w|h|color|label|angle|styles", "CIRCLE|id|cx|cy|radius|color|label|styles", "ELLIPSE|id|x|y|w|h|color|label|angle|styles", "DIAMOND|id|x|y|w|h|color|label|angle|styles", "STAR|id|cx|cy|radius|color|label|styles", "CLOUD|id|x|y|w|h|color|label|styles", "FRAME|id|x|y|w|h|color|label|styles", "CARD|id|x|y|w|h|color|title|body|styles", "TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label|styles", "POLYGON|id|x1,y1|x2,y2|...|xn,yn|color|label|styles", "POLYLINE|id|x1,y1|x2,y2|...|xn,yn|color|label|styles", "LINE|id|from|to|color|label|styles", "ARROW|id|from|to|color|label|styles", "BIARROW|id|from|to|color|label|styles", "ELBOW|id|from|to|color|label|styles", "TEXT|id|x|y|fontSize|color|text|styles". Manipulation: "MOVE|id|x,y", "MOVE_BY|id|dx,dy", "RESIZE|id|w,h", "SCALE|id|factor", "ROTATE|id|angle", "ROTATE_BY|id|angle", "HIDE|id1,id2", "SHOW|id1,id2|opacity", "DEL|id1,id2". styles: comma/semicolon separated options (dashed, dotted, hachure, cross-hatch, dots, round, sharp, w=N, opacity=N, font=virgil/sans/mono, align=left/center/right, both/double).',
              items: { type: 'STRING' }
            }
          },
          required: ['commands']
        }
      },
      {
        name: 'create_view',
        description: 'Creates or updates Excalidraw canvas directly with standard element objects.',
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
      }
    ]
  }
];

// 実際に Gemini API を呼び出す部分。単体テストでは realCall を差し替えて
// 実ネットワーク呼び出しなしに MOCK_GEMINI=0 側の分岐もテストできるようにしている
type RealGeminiCaller = (modelName: string, contents: any, config: any) => Promise<AsyncIterable<any>>;
const defaultRealCall: RealGeminiCaller = (modelName, contents, config) =>
  ai.models.generateContentStream({ model: modelName, contents, config });

// Gemini 本体呼び出し。MOCK_GEMINI=1 の場合は実APIを呼ばず、テスト用の固定ストリームを返す
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

// E2Eテスト用の固定ダミーストリーム。draw_dsl の functionCall を複数回に分けて返し、
// 1要素ずつの段階的描画(複数回呼び出し)の経路を検証できるようにする
export async function* mockGeminiStream(): AsyncGenerator<any> {
  yield {
    candidates: [{ content: { parts: [{ text: 'モック応答: フローチャートを3段階で描画します。' }] } }]
  };
  // ステップ1: Start要素
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
  // ステップ2: End要素
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
  // ステップ3: Arrow要素
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

const SYSTEM_INSTRUCTION_PATH = path.join(__dirname, 'SYSTEM_INSTRUCTION.md');
export const SYSTEM_INSTRUCTION = fs.readFileSync(SYSTEM_INSTRUCTION_PATH, 'utf-8');

// 画像URLを検出して Gemini API 用の inlineData に変換するヘルパー関数
export async function fetchImageAsInlineData(url: string, timeoutMs = 8000): Promise<{ inlineData: { mimeType: string; data: string } } | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const resp = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);

    if (!resp.ok) {
      console.warn(`Failed to fetch image from ${url}: ${resp.status} ${resp.statusText}`);
      return null;
    }

    const contentType = resp.headers.get('content-type') || '';
    // 画像形式判定
    let mimeType = contentType.split(';')[0].trim().toLowerCase();
    if (!mimeType.startsWith('image/')) {
      if (url.endsWith('.webp')) mimeType = 'image/webp';
      else if (url.endsWith('.png')) mimeType = 'image/png';
      else if (url.endsWith('.jpg') || url.endsWith('.jpeg')) mimeType = 'image/jpeg';
      else if (url.endsWith('.svg')) mimeType = 'image/svg+xml';
      else {
        console.warn(`URL does not appear to be an image: ${url} (${contentType})`);
        return null;
      }
    }

    const arrayBuffer = await resp.arrayBuffer();
    const base64 = Buffer.from(arrayBuffer).toString('base64');
    return {
      inlineData: {
        mimeType,
        data: base64
      }
    };
  } catch (err: any) {
    console.warn(`Error fetching image from ${url}:`, err.message);
    return null;
  }
}

// /api/chat のハンドラ本体。streamFn を差し替えられるようにして、
// 実Gemini呼び出しなしに 429/フォールバック/複数回functionCall 等の分岐を単体テストできるようにしている
export function createChatHandler(streamFn: typeof streamGeminiResponse = streamGeminiResponse) {
  return async (req: express.Request, res: express.Response) => {
  const { message, history, currentElements } = req.body;

  if (!process.env.GEMINI_API_KEY && process.env.MOCK_GEMINI !== '1') {
    return res.status(400).json({
      error: 'GEMINI_API_KEY environment variable is missing on server.'
    });
  }

  // 初動速度計測用タイムスタンプ（T0: リクエスト受信）
  const t0 = Date.now();
  console.log('⏱️ T0 request received');
  let firstFunctionCallLogged = false;
  let firstBroadcastLogged = false;
  // draw_dsl が1リクエスト内で複数回呼ばれても ARROW の id 参照解決を維持するための共有マップ
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

        return `- [${el.type} id=${el.id}] "${el.text || el.label?.text || ''}" at (${Math.round(x)},${Math.round(y)}) size (${Math.round(w)}x${Math.round(h)})`;
      }).join('\n');

      const suggestedNextY = Math.round(maxY + 60);
      const suggestedNextX = Math.round(maxX + 80);

      promptText += `\n\n[Current Whiteboard Elements (IMPORTANT: REUSE THESE IDs to update text without overlapping!)]:\n${summary}\n\n` +
        `[Whiteboard Layout Bounds & Placement Guidance]:\n` +
        `- Current Bounding Box: X range [${Math.round(minX)} to ${Math.round(maxX)}], Y range [${Math.round(minY)} to ${Math.round(maxY)}]\n` +
        `- Suggested Placement for NEW elements:\n` +
        `  * BELOW existing diagram: X=${Math.round(minX)}, Y=${suggestedNextY}\n` +
        `  * RIGHT of existing diagram: X=${suggestedNextX}, Y=${Math.round(minY)}\n` +
        `  * DO NOT overlap existing bounds [X: ${Math.round(minX)}-${Math.round(maxX)}, Y: ${Math.round(minY)}-${Math.round(maxY)}]!`;
    }

    // ユーザーメッセージ内の画像URL（http:// または https:// で画像拡張子を持つURL）を抽出して fetch
    const userParts: any[] = [{ text: promptText }];
    const imageUrlRegex = /https?:\/\/[^\s"'<>)]+\.(?:webp|png|jpe?g|gif|svg)(?:\?[^\s"'<>]*)?/gi;
    const matchedUrls = message ? (message.match(imageUrlRegex) || []) : [];

    for (const url of matchedUrls) {
      console.log(`🖼️ Fetching image from URL: ${url}`);
      const inlineImage = await fetchImageAsInlineData(url);
      if (inlineImage) {
        userParts.push(inlineImage);
        console.log(`✅ Attached image inlineData for Gemini multimodal input: ${url}`);
      }
    }

    const contents = [
      ...formattedHistory,
      { role: 'user', parts: userParts }
    ];

    const fallbackModels = process.env.GEMINI_MODELS
      ? process.env.GEMINI_MODELS.split(',').map((s) => s.trim()).filter(Boolean)
      : [
          'gemini-3.5-flash',
          'gemini-3.7-flash',
          'gemini-3.5-flash-lite',
          'gemini-3.1-pro-preview'
        ];

    const callModelStreamWithRetry = async (modelName: string, retries = 2, delayMs = 1000): Promise<{ replyText: string; toolCallsExecuted: any[] }> => {
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          console.log(`Streaming model: ${modelName} (attempt ${attempt}) ⏱️ T1 +${Date.now() - t0}ms`);
          const responseStream = streamFn(modelName, contents, {
            systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
            tools: excalidrawTools,
            thinkingConfig: getThinkingConfigFor(modelName),
            maxOutputTokens: 8192,
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

                // 呼び出し単位（fc.id）で重複排除。Gemini API は関数呼び出しの引数を
                // 部分ストリーミングしないため、1つの fc.id につき commands は丸ごと届く前提でよい
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
                    type: 'EXCALIDRAW_UPDATE',
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
          const errMsg = err.message || '';
          const isTransient =
            err.status === 'RESOURCE_EXHAUSTED' ||
            err.status === 'UNAVAILABLE' ||
            err.code === 503 ||
            errMsg.includes('429') ||
            errMsg.includes('503') ||
            errMsg.includes('UNAVAILABLE') ||
            errMsg.includes('high demand') ||
            errMsg.includes('Quota exceeded');

          if (isTransient && attempt < retries) {
            console.warn(`Model ${modelName} hit transient error (429/503). Retrying in ${delayMs / 1000}s... (attempt ${attempt}/${retries})`);
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
        // callModelStreamWithRetry は必ず結果を返すか throw するため、result が falsy になることは
        // 実質無い（防御的チェック）。到達不能な分岐なのでカバレッジ計測から除外する
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
      reply: result.replyText || '（図形を作成・修正しました）',
      toolCalls: result.toolCallsExecuted
    });

  } catch (error: any) {
    console.error('Error generating streaming content:', error);
    return res.status(500).json({ error: error.message || 'Internal Server Error' });
  }
  };
}

app.post('/api/chat', createChatHandler());

const PORT = process.env.PORT || 3001;

// このファイルが直接実行された場合のみ listen する（テストからの import 時に
// ポートを掴んでしまわないようにするためのガード）。実際にポートを bind する分岐は
// テストプロセスからは意図的に実行しないため、カバレッジ計測から除外する
const isMainModule = process.argv[1] === fileURLToPath(import.meta.url);
/* v8 ignore start */
if (isMainModule) {
  server.listen(PORT, () => {
    console.log(`🚀 Express API & WebSocket Server running on http://localhost:${PORT}`);
  });
}
/* v8 ignore stop */
