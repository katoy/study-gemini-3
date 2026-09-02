import express from 'express';
import http from 'http';
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
const clients = new Set<WebSocket>();

wss.on('connection', (ws) => {
  clients.add(ws);
  console.log('Client connected to WebSocket');

  ws.on('close', () => {
    clients.delete(ws);
    console.log('Client disconnected from WebSocket');
  });
});

function broadcast(data: any) {
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
        description: 'Creates or updates the diagram canvas using fast compact DSL commands array. YOU MUST ALWAYS CALL THIS TOOL when asked to draw, create, or modify a diagram/flowchart/architecture.',
        parameters: {
          type: 'OBJECT',
          properties: {
            commands: {
              type: 'ARRAY',
              description: 'List of DSL strings. Formats: "RECT|id|x|y|w|h|color|label", "ELLIPSE|id|x|y|w|h|color|label", "DIAMOND|id|x|y|w|h|color|label", "TEXT|id|x|y|fontSize|color|text", "ARROW|id|fromIdOrX,Y|toIdOrX,Y|color|label", "DEL|id1,id2".',
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

// Gemini 本体呼び出し。MOCK_GEMINI=1 の場合は実APIを呼ばず、テスト用の固定ストリームを返す
async function* streamGeminiResponse(modelName: string, contents: any, config: any): AsyncGenerator<any> {
  if (process.env.MOCK_GEMINI === '1') {
    yield* mockGeminiStream();
    return;
  }
  const responseStream = await ai.models.generateContentStream({ model: modelName, contents, config });
  for await (const chunk of responseStream) {
    yield chunk;
  }
}

// E2Eテスト用の固定ダミーストリーム。draw_dsl の functionCall を意図的に2回に分けて返し、
// 段階的描画（複数回呼び出し）の経路を検証できるようにする
async function* mockGeminiStream(): AsyncGenerator<any> {
  yield {
    candidates: [{ content: { parts: [{ text: 'モック応答: フローチャートを2段階で描画します。' }] } }]
  };
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
  yield {
    candidates: [{
      content: {
        parts: [{
          functionCall: {
            id: 'mock-fc-2',
            name: 'draw_dsl',
            args: { commands: ['RECT|box2|300|100|140|70|green|End', 'ARROW|arr1|box1|box2|dark|next'] }
          }
        }]
      }
    }]
  };
}

const SYSTEM_INSTRUCTION = `
You are an AI assistant in a collaborative whiteboarding and chat application.
You can communicate with text responses AND interact directly with the user's Excalidraw whiteboard using tools.

CRITICAL INSTRUCTIONS:
1. Whenever the user asks to draw, build, create, update, or modify a diagram/flowchart/architecture/visual, YOU MUST CALL the \`draw_dsl\` function tool to update the whiteboard.
2. ALONGSIDE CALLING THE TOOL, YOU MUST ALWAYS PROVIDE A HELPFUL TEXT RESPONSE IN JAPANESE that summarizes the key points, main components, or specific changes/updates made to the diagram!
3. DO NOT just return tool calls alone without a text explanation. Always briefly explain what was created, updated, or added in easy-to-understand Japanese points.
4. FOR DIAGRAMS WITH MORE THAN ~5 ELEMENTS, DO NOT PUT ALL COMMANDS INTO A SINGLE \`draw_dsl\` CALL. Instead, split the diagram into meaningful groups (e.g. one call per major block/section, roughly 3-6 commands per call) and call \`draw_dsl\` MULTIPLE TIMES IN SEQUENCE within your turn, so the user sees the drawing appear progressively instead of all at once at the end. When a later call in the same turn updates an element created by an earlier call in that same turn, ALWAYS REUSE its exact same ID (see ID reuse rules below).

CRITICAL ELEMENT & TEXT EDITING RULES (PREVENT OVERLAPPING):
- When updating, editing, or appending to existing text/elements (e.g. adding the answer "10" to "1 + 2 + 3 + 4 ="):
  * YOU MUST REUSE THE EXACT SAME ID of the existing element!
  * Example: Existing element is [TEXT id=txt1] "1 + 2 + 3 + 4 =". To add "= 10", output "TEXT|txt1|x|y|fontSize|color|1 + 2 + 3 + 4 = 10".
  * DO NOT create a new element ID at the same position, or the text will overlap and get corrupted!
- To delete an element, use "DEL|id".

DSL Syntax for \`draw_dsl\`:
- "RECT|id|x|y|width|height|color|label"
- "ELLIPSE|id|x|y|width|height|color|label"
- "DIAMOND|id|x|y|width|height|color|label"
- "TEXT|id|x|y|fontSize|color|text"
- "ARROW|id|fromIdOrCoords|toIdOrCoords|color|label"
- "DEL|id1,id2"

Color Keywords:
blue, green, orange, purple, red, yellow, teal, dark, gray, default.

LAYOUT GUIDELINES:
- Always make your diagrams visually attractive, clean, well-spaced, and readable.
- Maintain consistent coordinates and alignment for connected nodes.
`;

app.post('/api/chat', async (req, res) => {
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

    const fallbackModels = [
      'gemini-3.6-flash',
      'gemini-3.5-flash-lite',
      'gemini-3.1-pro-preview'
    ];

    const callModelStreamWithRetry = async (modelName: string, retries = 2, delayMs = 2500): Promise<{ replyText: string; toolCallsExecuted: any[] }> => {
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          console.log(`Streaming model: ${modelName} (attempt ${attempt}) ⏱️ T1 +${Date.now() - t0}ms`);
          const responseStream = streamGeminiResponse(modelName, contents, {
            systemInstruction: { parts: [{ text: SYSTEM_INSTRUCTION }] },
            tools: excalidrawTools,
            temperature: 0.2,
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
});

const PORT = process.env.PORT || 3001;
server.listen(PORT, () => {
  console.log(`🚀 Express API & WebSocket Server running on http://localhost:${PORT}`);
});
