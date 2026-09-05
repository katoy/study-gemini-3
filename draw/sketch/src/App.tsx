import React, { useState, useEffect, useRef } from 'react';
import { mergeServerElements } from './mergeServerElements';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: any[];
}

export interface SketchElement {
  id: string;
  type: string;
  name?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  angle?: number;
  text?: string;
  fontSize?: number;
  textAlign?: string;
  verticalAlign?: string;
  strokeColor?: string;
  backgroundColor?: string;
  fillStyle?: string;
  strokeStyle?: string;
  strokeWidth?: number;
  opacity?: number;
  points?: number[][];
  startArrowhead?: string | null;
  endArrowhead?: string | null;
  label?: {
    text: string;
    fontSize?: number;
    strokeColor?: string;
  };
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'こんにちは！Gemini + Sketch (Sketch-mcp) チャットへようこそ。\n「システム構成図を描いて」「ワイヤーフレームを作成して」「フローチャートを描いて」など指示してください。Sketch-mcp と連動した図やUIの自動生成・編集を行います！',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [elements, setElements] = useState<SketchElement[]>([]);
  const [promptHistory, setPromptHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [sketchMcpConnected, setSketchMcpConnected] = useState<boolean>(false);

  const draftInputRef = useRef<string>('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Sketch-mcp サーバー状態確認
  useEffect(() => {
    const checkMcpStatus = async () => {
      try {
        const res = await fetch('/api/sketch-mcp/status');
        const data = await res.json();
        setSketchMcpConnected(!!data.connected);
      } catch {
        setSketchMcpConnected(false);
      }
    };
    checkMcpStatus();
    const interval = setInterval(checkMcpStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = event.target?.result as string;
        const parsed = JSON.parse(content);
        const importedElements = Array.isArray(parsed) ? parsed : (parsed.elements || []);
        setElements(importedElements);
      } catch (err) {
        alert('ファイルの読み込みに失敗しました。有効な JSON ファイルを選択してください。');
        console.error('Failed to parse JSON:', err);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const saveFileWithPicker = async (
    blob: Blob,
    suggestedName: string,
    mimeType?: string,
    extension?: string
  ) => {
    if ('showSaveFilePicker' in window) {
      try {
        const options: any = { suggestedName };
        if (mimeType && extension) {
          options.types = [{ description: 'Save File', accept: { [mimeType]: [extension] } }];
        }
        const handle = await (window as any).showSaveFilePicker(options);
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return;
      } catch (err: any) {
        if (err.name === 'AbortError') return;
      }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = suggestedName;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadJSON = async () => {
    const jsonString = JSON.stringify({ elements, app: 'Sketch-mcp-gemini', version: 1 }, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    await saveFileWithPicker(blob, `sketch-${Date.now()}.json`, 'application/json', '.json');
  };

  const downloadSVG = async () => {
    if (!svgRef.current) return;
    const svgString = new XMLSerializer().serializeToString(svgRef.current);
    const blob = new Blob([svgString], { type: 'image/svg+xml' });
    await saveFileWithPicker(blob, `sketch-${Date.now()}.svg`, 'image/svg+xml', '.svg');
  };

  const downloadPNG = async () => {
    if (!svgRef.current) return;
    const svgString = new XMLSerializer().serializeToString(svgRef.current);
    const img = new Image();
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const URLObj = window.URL || window.webkitURL || window;
    const blobURL = URLObj.createObjectURL(svgBlob);

    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = svgRef.current?.clientWidth || 1200;
      canvas.height = svgRef.current?.clientHeight || 800;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        canvas.toBlob((blob) => {
          if (blob) {
            saveFileWithPicker(blob, `sketch-${Date.now()}.png`, 'image/png', '.png');
          }
        }, 'image/png');
      }
      URLObj.revokeObjectURL(blobURL);
    };
    img.src = blobURL;
  };

  const clearCanvas = () => {
    if (window.confirm('キャンバスをクリアしますか？')) {
      setElements([]);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // WebSocket 受信とアニメーションキュー
  const animationQueueRef = useRef<any[]>([]);
  const isAnimatingRef = useRef(false);

  const processAnimationQueue = async () => {
    if (isAnimatingRef.current) return;
    isAnimatingRef.current = true;

    try {
      while (animationQueueRef.current.length > 0) {
        const nextElement = animationQueueRef.current.shift();
        setElements((prev) => mergeServerElements(prev, [nextElement]));
        if (animationQueueRef.current.length > 0) {
          await new Promise((resolve) => setTimeout(resolve, 300));
        }
      }
    } finally {
      isAnimatingRef.current = false;
    }
  };

  const applyServerElements = (serverElements: any[]) => {
    if (!Array.isArray(serverElements) || serverElements.length === 0) return;
    animationQueueRef.current.push(...serverElements);
    processAnimationQueue();
  };

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'SKETCH_UPDATE') {
          applyServerElements(data.elements);
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setPromptHistory((prev) => {
      if (prev.length > 0 && prev[prev.length - 1] === trimmed) return prev;
      return [...prev, trimmed];
    });
    setHistoryIndex(-1);
    draftInputRef.current = '';

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: trimmed,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage.content,
          history: messages,
          currentElements: elements.map((el) => ({
            id: el.id,
            type: el.type,
            name: el.name,
            x: el.x,
            y: el.y,
            width: el.width,
            height: el.height,
            text: el.text || el.label?.text,
          })),
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Server request failed');
      }

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.reply,
        toolCalls: data.toolCalls,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (data.toolCalls) {
        for (const tc of data.toolCalls) {
          if (tc.name === 'create_view' && tc.args?.elements) {
            applyServerElements(tc.args.elements);
          }
        }
      }
    } catch (err: any) {
      console.error('Error sending message:', err);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: `⚠️ エラーが発生しました: ${err.message}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      sendMessage();
      return;
    }

    if (e.key === 'ArrowUp') {
      const isSingleLineOrAtTop = !input.includes('\n') || e.currentTarget.selectionStart <= input.indexOf('\n');
      if (promptHistory.length > 0 && (historyIndex !== -1 || isSingleLineOrAtTop)) {
        e.preventDefault();
        let nextIndex = historyIndex;
        if (historyIndex === -1) {
          draftInputRef.current = input;
          nextIndex = promptHistory.length - 1;
        } else if (historyIndex > 0) {
          nextIndex = historyIndex - 1;
        }
        if (nextIndex !== -1) {
          setHistoryIndex(nextIndex);
          const historyText = promptHistory[nextIndex];
          setInput(historyText);
        }
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      if (historyIndex !== -1) {
        e.preventDefault();
        if (historyIndex < promptHistory.length - 1) {
          const nextIndex = historyIndex + 1;
          setHistoryIndex(nextIndex);
          setInput(promptHistory[nextIndex]);
        } else {
          setHistoryIndex(-1);
          setInput(draftInputRef.current);
        }
      }
      return;
    }
  };

  // SVG 要素の描画
  const renderElement = (el: SketchElement) => {
    const stroke = el.strokeColor || '#0f172a';
    const fill = el.backgroundColor || 'transparent';
    const strokeWidth = el.strokeWidth || 2;
    const transform = el.angle ? `rotate(${el.angle} ${el.x + el.width / 2} ${el.y + el.height / 2})` : undefined;

    switch (el.type) {
      case 'rectangle':
        return (
          <g key={el.id} transform={transform}>
            <rect
              x={el.x}
              y={el.y}
              width={el.width}
              height={el.height}
              rx={8}
              ry={8}
              fill={fill}
              stroke={stroke}
              strokeWidth={strokeWidth}
            />
            {el.text && (
              <text
                x={el.x + el.width / 2}
                y={el.y + el.height / 2 + 5}
                textAnchor="middle"
                fontSize={el.fontSize || 16}
                fill={stroke}
                fontWeight="500"
              >
                {el.text}
              </text>
            )}
          </g>
        );
      case 'oval':
      case 'ellipse':
        return (
          <g key={el.id} transform={transform}>
            <ellipse
              cx={el.x + el.width / 2}
              cy={el.y + el.height / 2}
              rx={el.width / 2}
              ry={el.height / 2}
              fill={fill}
              stroke={stroke}
              strokeWidth={strokeWidth}
            />
            {el.text && (
              <text
                x={el.x + el.width / 2}
                y={el.y + el.height / 2 + 5}
                textAnchor="middle"
                fontSize={el.fontSize || 16}
                fill={stroke}
                fontWeight="500"
              >
                {el.text}
              </text>
            )}
          </g>
        );
      case 'diamond': {
        const cx = el.x + el.width / 2;
        const cy = el.y + el.height / 2;
        const points = `${cx},${el.y} ${el.x + el.width},${cy} ${cx},${el.y + el.height} ${el.x},${cy}`;
        return (
          <g key={el.id} transform={transform}>
            <polygon points={points} fill={fill} stroke={stroke} strokeWidth={strokeWidth} />
            {el.text && (
              <text
                x={cx}
                y={cy + 5}
                textAnchor="middle"
                fontSize={el.fontSize || 16}
                fill={stroke}
                fontWeight="500"
              >
                {el.text}
              </text>
            )}
          </g>
        );
      }
      case 'triangle': {
        const points = el.points
          ? el.points.map(([px, py]) => `${el.x + px},${el.y + py}`).join(' ')
          : `${el.x + el.width / 2},${el.y} ${el.x + el.width},${el.y + el.height} ${el.x},${el.y + el.height}`;
        return (
          <g key={el.id} transform={transform}>
            <polygon points={points} fill={fill} stroke={stroke} strokeWidth={strokeWidth} />
            {el.text && (
              <text
                x={el.x + el.width / 2}
                y={el.y + (el.height * 2) / 3}
                textAnchor="middle"
                fontSize={el.fontSize || 16}
                fill={stroke}
                fontWeight="500"
              >
                {el.text}
              </text>
            )}
          </g>
        );
      }
      case 'line':
      case 'arrow': {
        const p1 = el.points?.[0] || [0, 0];
        const p2 = el.points?.[1] || [el.width, el.height];
        const x1 = el.x + p1[0];
        const y1 = el.y + p1[1];
        const x2 = el.x + p2[0];
        const y2 = el.y + p2[1];
        const markerEnd = el.type === 'arrow' ? `url(#arrowhead-${el.id})` : undefined;

        return (
          <g key={el.id}>
            {el.type === 'arrow' && (
              <defs>
                <marker
                  id={`arrowhead-${el.id}`}
                  markerWidth="10"
                  markerHeight="7"
                  refX="9"
                  refY="3.5"
                  orient="auto"
                >
                  <polygon points="0 0, 10 3.5, 0 7" fill={stroke} />
                </marker>
              </defs>
            )}
            <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={stroke} strokeWidth={strokeWidth} markerEnd={markerEnd} />
            {el.label?.text && (
              <text
                x={(x1 + x2) / 2}
                y={(y1 + y2) / 2 - 8}
                textAnchor="middle"
                fontSize={el.label.fontSize || 14}
                fill={stroke}
                fontWeight="500"
                className="bg-white"
              >
                {el.label.text}
              </text>
            )}
          </g>
        );
      }
      case 'text':
        return (
          <g key={el.id} transform={transform}>
            <text
              x={el.x}
              y={el.y + (el.fontSize || 18)}
              fontSize={el.fontSize || 18}
              fill={stroke}
              fontWeight="600"
            >
              {el.text}
            </text>
          </g>
        );
      default:
        return null;
    }
  };

  return (
    <div className="app-container">
      {/* Left Chat Side */}
      <div className="chat-panel">
        <div className="chat-header">
          <h1>💎 Gemini Sketch Chat</h1>
          <span className={`status-badge ${sketchMcpConnected ? '' : 'disconnected'}`}>
            {sketchMcpConnected ? 'Sketch MCP Connected' : 'Sketch MCP Ready'}
          </span>
        </div>

        <div className="chat-messages">
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div>{msg.content}</div>
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="message-tool-tag">
                  💎 Sketch Canvas Updated ({msg.toolCalls.length} tool call)
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="message assistant">
              <div>Gemini が思考・Sketch 図を作成中... 💎</div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea
              ref={textareaRef}
              placeholder="質問や Sketch 図の作成指示を入力... (Shift+Enterで送信)"
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                if (historyIndex !== -1) {
                  draftInputRef.current = e.target.value;
                }
              }}
              onKeyDown={handleKeyDown}
            />
            <button
              className="send-button"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
            >
              送信
            </button>
          </div>
        </div>
      </div>

      {/* Right Sketch Whiteboard Side */}
      <div className="whiteboard-panel">
        <div className="whiteboard-toolbar">
          <div className={`mcp-indicator ${sketchMcpConnected ? '' : 'off'}`} title="Sketch Mac App MCP Server status">
            <span className="dot" />
            <span>{sketchMcpConnected ? 'Sketch App Connected' : 'Sketch MCP Offline'}</span>
          </div>

          <span className="toolbar-divider" />

          <input
            type="file"
            ref={fileInputRef}
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
          />
          <button className="toolbar-btn" onClick={triggerFileInput} title="JSONファイルを読み込み">
            📂 アップロード
          </button>
          <button className="toolbar-btn" onClick={clearCanvas} title="キャンバスをクリア">
            🗑️ クリア
          </button>

          <span className="toolbar-divider" />

          <button className="toolbar-btn primary" onClick={downloadJSON} title="Sketch JSON形式で保存 (.json)">
            📄 JSON
          </button>
          <button className="toolbar-btn primary" onClick={downloadPNG} title="PNG画像として保存 (.png)">
            🖼️ PNG
          </button>
          <button className="toolbar-btn primary" onClick={downloadSVG} title="SVGベクターとして保存 (.svg)">
            📐 SVG
          </button>
        </div>

        <div className="sketch-canvas-container">
          <svg
            ref={svgRef}
            width="2500"
            height="2000"
            style={{ display: 'block', backgroundColor: 'transparent' }}
          >
            {elements.map(renderElement)}
          </svg>
        </div>
      </div>
    </div>
  );
}
