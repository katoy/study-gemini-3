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
  const [promptHistory, setPromptHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const draftInputRef = useRef<string>('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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

  // 段階的アニメーションキューの管理：要素を 1 つずつ順次追加する
  const animationQueueRef = useRef<any[]>([]);
  const isAnimatingRef = useRef(false);

  const processAnimationQueue = async () => {
    if (isAnimatingRef.current || !excalidrawAPI) return;
    isAnimatingRef.current = true;

    try {
      while (animationQueueRef.current.length > 0) {
        const nextElement = animationQueueRef.current.shift();
        const currentScene = excalidrawAPI.getSceneElements() || [];
        const updated = mergeServerElements(currentScene, [nextElement], convertToExcalidrawElements);

        console.log(`⏱️ Adding element at ${Date.now()}:`, nextElement);
        excalidrawAPI.updateScene({ elements: updated });

        if (animationQueueRef.current.length > 0) {
          await new Promise((resolve) => setTimeout(resolve, 1200));
        } else {
          // キュー内の全要素描画完了後、画面内に収める
          setTimeout(() => {
            const final = excalidrawAPI.getSceneElements();
            if (final && final.length > 0) {
              console.log(`✨ Fitting viewport at ${Date.now()}`);
              excalidrawAPI.scrollToContent(final, {
                fitToViewport: true,
                animate: true,
              });
            }
          }, 300);
        }
      }
    } catch (err) {
      console.error('Error in animation queue:', err);
    } finally {
      isAnimatingRef.current = false;
    }
  };

  const applyServerElements = (serverElements: any[]) => {
    if (!excalidrawAPI || !Array.isArray(serverElements) || serverElements.length === 0) {
      return;
    }

    console.log('applyServerElements queued:', serverElements);
    animationQueueRef.current.push(...serverElements);
    processAnimationQueue();
  };

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    setPromptHistory((prev) => {
      if (prev.length > 0 && prev[prev.length - 1] === trimmed) {
        return prev;
      }
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
          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.selectionStart = textareaRef.current.selectionEnd = historyText.length;
            }
          }, 0);
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
          const historyText = promptHistory[nextIndex];
          setInput(historyText);
          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.selectionStart = textareaRef.current.selectionEnd = historyText.length;
            }
          }, 0);
        } else {
          setHistoryIndex(-1);
          const draftText = draftInputRef.current;
          setInput(draftText);
          setTimeout(() => {
            if (textareaRef.current) {
              textareaRef.current.selectionStart = textareaRef.current.selectionEnd = draftText.length;
            }
          }, 0);
        }
      }
      return;
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
              ref={textareaRef}
              placeholder="質問や図の作成指示を入力... (Shift+Enterで送信)"
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
