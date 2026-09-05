import express from 'express';
import http from 'http';
import { fileURLToPath } from 'url';
import { WebSocketServer, WebSocket } from 'ws';
import { GoogleGenAI } from '@google/genai';
import { parseDSLToElements, getThinkingConfigFor } from './dsl';

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
        description: 'Creates or updates the diagram canvas using compact DSL commands array. When drawing, include ALL components (shapes, connectors, labels) ordered logically (foundations -> connections -> details). The client animates each element sequentially.',
        parameters: {
          type: 'OBJECT',
          properties: {
            commands: {
              type: 'ARRAY',
              description: 'List of DSL strings in drawing order. Formats: "RECT|id|x|y|w|h|color|label|angle", "TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label", "ELLIPSE|id|x|y|w|h|color|label", "DIAMOND|id|x|y|w|h|color|label", "LINE|id|fromX,fromY|toX,toY|color|label", "ARROW|id|fromIdOrX,Y|toIdOrX,Y|color|label", "TEXT|id|x|y|fontSize|color|text", "DEL|id1,id2". (angle in RECT is optional rotation in degrees or radians).',
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

const SYSTEM_INSTRUCTION = `
You are an AI assistant in a collaborative whiteboarding and chat application.
You can communicate with helpful text responses to the user.

INSTRUCTIONS:
1. Always provide clear, helpful, and informative text responses in Japanese.
2. If the user asks about diagrams or architecture, describe them clearly in text format.
3. Maintain a friendly and professional tone.
4. When discussing diagrams or visual concepts, provide detailed text descriptions to help the user understand.

PROGRESSIVE DRAWING (段階的描画):
- When the user asks to draw diagrams, flowcharts, or shapes, generate COMPLETE diagrams with all necessary components (boxes, shapes, connectors, labels).
- NEVER output only a single partial element unless specifically requested. Always build the full diagram requested by the user.
- Order commands logically in the array: (1) foundational shapes/boxes first, (2) intermediate shapes & connectors second, (3) labels & refinements third.
- The client frontend renders the elements sequentially one by one with a smooth animated delay based on this order.
- You may call draw_dsl once with all elements ordered, or multiple times in succession. Always ensure the entire diagram is drawn.

MATHEMATICAL & GEOMETRICAL DIAGRAMS (幾何学図形・三平方の定理など):
- For triangles or geometry (e.g. Pythagorean theorem a² + b² = c²):
  * Use "TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label" to draw real right-angled or arbitrary triangles.
  * Use "RECT|id|x|y|w|h|color|label|angle" to draw squares on triangle sides. "angle" supports rotation in degrees (e.g. -36.87 or 36.87) to attach squares along slanted hypotenuse.
  * Use "LINE|id|x1,y1|x2,y2|color|label" for straight lines without arrowheads (for right-angle marks, borders, axes).
  * Use "TEXT" for clear formula annotations (e.g. "a² + b² = c²", "3² + 4² = 5²").
`;

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

    const contents = [
      ...formattedHistory,
      { role: 'user', parts: [{ text: promptText }] }
    ];

    const fallbackModels = process.env.GEMINI_MODELS
      ? process.env.GEMINI_MODELS.split(',').map((s) => s.trim()).filter(Boolean)
      : [
          'gemini-3.5-flash',
          'gemini-3.7-flash'
        ];

    const callModelStreamWithRetry = async (modelName: string, retries = 2, delayMs = 1000): Promise<{ replyText: string; toolCallsExecuted: any[] }> => {
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          console.log(`Streaming model: ${modelName} (attempt ${attempt}) ⏱️ T1 +${Date.now() - t0}ms`);
          const responseStream = streamFn(modelName, contents, {
            systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
            tools: excalidrawTools,
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
