import React, { useState, useEffect, useRef } from 'react';
import { Excalidraw, convertToExcalidrawElements, exportToBlob, exportToSvg, serializeAsJSON } from '@excalidraw/excalidraw';
import '@excalidraw/excalidraw/index.css';
import { mergeServerElements } from './mergeServerElements';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: any[];
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'こんにちは！Gemini + Excalidraw ホワイトボードチャットへようこそ。\n「アーキテクチャ図を描いて」「フローチャートを作成して」「図の要素を追加して」など、気軽にお尋ねください。図の自動作成や編集を行います！',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [excalidrawAPI, setExcalidrawAPI] = useState<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !excalidrawAPI) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const content = event.target?.result as string;
        const parsed = JSON.parse(content);

        let elements = [];
        let appState = {};
        let files = {};

        if (Array.isArray(parsed)) {
          elements = parsed;
        } else if (parsed && typeof parsed === 'object') {
          elements = parsed.elements || [];
          appState = parsed.appState || {};
          files = parsed.files || {};
        }

        excalidrawAPI.updateScene({
          elements,
          appState,
          files,
        });

        if (elements.length > 0) {
          excalidrawAPI.scrollToContent(elements, {
            fitToViewport: true,
            animate: true,
          });
        }
      } catch (err: any) {
        alert('ファイルの読み込みに失敗しました。有効なExcalidraw JSONファイルを選択してください。');
        console.error('Failed to parse uploaded Excalidraw JSON:', err);
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
        console.log('Opening save file dialog for:', suggestedName);
        const options: any = {
          suggestedName,
        };

        if (mimeType && extension) {
          options.types = [
            {
              description: 'Save File',
              accept: { [mimeType]: [extension] },
            },
          ];
        }

        const handle = await (window as any).showSaveFilePicker(options);
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        console.log('Saved file successfully using showSaveFilePicker');
        return;
      } catch (err: any) {
        if (err.name === 'AbortError') {
          console.log('User cancelled file save dialog.');
          return;
        }
        console.warn('showSaveFilePicker failed or unsupported, using fallback link:', err);
      }
    } else {
      console.log('showSaveFilePicker is not supported in this browser environment.');
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = suggestedName;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadJSON = async () => {
    if (!excalidrawAPI) return;
    const elements = excalidrawAPI.getSceneElements();
    const appState = excalidrawAPI.getAppState();
    const files = excalidrawAPI.getFiles();

    const jsonString = serializeAsJSON(elements, appState, files, 'local');
    const blob = new Blob([jsonString], { type: 'application/json' });
    await saveFileWithPicker(blob, `excalidraw-${Date.now()}.excalidraw`, 'application/json', '.json');
  };

  const downloadPNG = async () => {
    if (!excalidrawAPI) return;
    const elements = excalidrawAPI.getSceneElements();
    const appState = excalidrawAPI.getAppState();
    const files = excalidrawAPI.getFiles();

    if (elements.length === 0) {
      alert('エクスポートする要素がありません。');
      return;
    }

    try {
      const blob = await exportToBlob({
        elements,
        appState: {
          ...appState,
          exportWithBackground: true,
        },
        files,
        mimeType: 'image/png',
      });

      await saveFileWithPicker(blob, `drawing-${Date.now()}.png`, 'image/png', '.png');
    } catch (err) {
      console.error('PNG export failed:', err);
    }
  };

  const downloadSVG = async () => {
    if (!excalidrawAPI) return;
    const elements = excalidrawAPI.getSceneElements();
    const appState = excalidrawAPI.getAppState();
    const files = excalidrawAPI.getFiles();

    if (elements.length === 0) {
      alert('エクスポートする要素がありません。');
      return;
    }

    try {
      const svg = await exportToSvg({
        elements,
        appState: {
          ...appState,
          exportWithBackground: true,
        },
        files,
      });

      const svgString = new XMLSerializer().serializeToString(svg);
      const blob = new Blob([svgString], { type: 'image/svg+xml' });
      await saveFileWithPicker(blob, `drawing-${Date.now()}.svg`, 'image/svg+xml', '.svg');
    } catch (err) {
      console.error('SVG export failed:', err);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // WebSocket Connection to receive real-time Excalidraw updates from Gemini
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;
    const ws = new WebSocket(wsUrl);

    let firstUpdateLogged = false;
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'EXCALIDRAW_UPDATE' && excalidrawAPI) {
          if (!firstUpdateLogged) {
            firstUpdateLogged = true;
            console.log(`⏱️ First EXCALIDRAW_UPDATE received at ${Date.now()}`);
          }
          applyServerElements(data.elements);
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };

    return () => {
      ws.close();
    };
  }, [excalidrawAPI]);

  // Convert & apply elements received from MCP server function calls to Excalidraw state
  // 段階的アニメーション：要素を 1 つずつ出現させる
  const applyServerElements = (serverElements: any[]) => {
    if (!excalidrawAPI) {
      console.warn('excalidrawAPI is not initialized yet');
      return;
    }

    if (!Array.isArray(serverElements) || serverElements.length === 0) {
      return;
    }

    console.log('applyServerElements received:', serverElements);

    try {
      const currentSceneElements = excalidrawAPI.getSceneElements() || [];
      const finalElements = mergeServerElements(currentSceneElements, serverElements, convertToExcalidrawElements);

      console.log('Final elements updating Excalidraw scene:', finalElements);

      // 段階的描画：新規要素を 1 つずつ追加（アニメーション効果付き）
      const newElementCount = serverElements.length;
      const animationDelay = 300; // 各要素間の遅延（ms）

      for (let i = 0; i < newElementCount; i++) {
        setTimeout(() => {
          // 現在の要素まで含めた状態を更新
          const elementsUpToIndex = finalElements.slice(0, finalElements.length - newElementCount + i + 1);
          excalidrawAPI.updateScene({
            elements: elementsUpToIndex,
          });

          // 最後の要素の後に viewport をフィット
          if (i === newElementCount - 1) {
            setTimeout(() => {
              excalidrawAPI.scrollToContent(elementsUpToIndex, {
                fitToViewport: true,
                animate: true,
              });
            }, 100);
          }
        }, animationDelay * i);
      }
    } catch (e) {
      console.error('Error updating Excalidraw scene:', e);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      // Get current Excalidraw elements to send context to Gemini
      const currentElements = excalidrawAPI ? excalidrawAPI.getSceneElements() : [];

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage.content,
          history: messages,
          currentElements: currentElements.map((el: any) => ({
            id: el.id,
            type: el.type,
            x: el.x,
            y: el.y,
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

      // Also apply tool call updates locally if any
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
    }
  };

  return (
    <div className="app-container">
      {/* Left Chat Side */}
      <div className="chat-panel">
        <div className="chat-header">
          <h1>
            🎨 Gemini Excalidraw Chat
          </h1>
          <span className="status-badge">Online</span>
        </div>

        <div className="chat-messages">
          {messages.map((msg) => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div>{msg.content}</div>
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="message-tool-tag">
                  🛠️ Whiteboard Updated ({msg.toolCalls.length} tool call)
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="message assistant">
              <div>Gemini が思考・図を作成中... 🎨</div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea
              placeholder="質問や図の作成指示を入力... (Shift+Enterで送信)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
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

      {/* Right Whiteboard Side */}
      <div className="whiteboard-panel">
        <div className="whiteboard-toolbar">
          <input
            type="file"
            ref={fileInputRef}
            accept=".excalidraw,.json,application/json"
            style={{ display: 'none' }}
            onChange={handleFileUpload}
          />
          <button className="toolbar-btn" onClick={triggerFileInput} title="JSONファイルを読み込んで図を復元">
            📂 アップロード
          </button>

          <span className="toolbar-divider" />

          <button className="toolbar-btn primary" onClick={downloadJSON} title="Excalidraw JSON形式で保存 (.excalidraw)">
            📄 JSON
          </button>
          <button className="toolbar-btn primary" onClick={downloadPNG} title="PNG画像として保存 (.png)">
            🖼️ PNG
          </button>
          <button className="toolbar-btn primary" onClick={downloadSVG} title="SVGベクターとして保存 (.svg)">
            📐 SVG
          </button>
        </div>
        <Excalidraw
          excalidrawAPI={(api) => setExcalidrawAPI(api)}
          initialData={{
            appState: {
              viewBackgroundColor: '#ffffff',
              currentItemFontFamily: 1,
            },
          }}
        />
      </div>
    </div>
  );
}
