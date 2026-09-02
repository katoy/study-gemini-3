// 生の要素配列を Excalidraw 要素に変換する関数の型。
// 実体は呼び出し元（App.tsx）から @excalidraw/excalidraw の convertToExcalidrawElements を注入する。
// このファイル自体が @excalidraw/excalidraw を import すると（ブラウザ実行前提の初期化コードが
// 走るため）Node環境での単体テストが困難になるので、依存注入で切り離している。
export type ElementConverter = (rawElements: any[]) => any[];

// server から届いた要素配列を既存シーン要素とマージする純粋関数。
// App コンポーネントから切り出すことで単体テスト可能にしている（React/DOM への依存なし）。
// カメラ更新はスキップ、DEL指定は削除、同一IDは上書き、近接テキストは重複排除する。
export function mergeServerElements(
  currentSceneElements: any[],
  serverElements: any[],
  convert: ElementConverter
): any[] {
  const elementsToDelete = new Set<string>();
  const rawNewElements: any[] = [];

  for (const elem of serverElements) {
    if (elem.type === 'cameraUpdate') {
      continue;
    }

    if (elem.type === 'delete') {
      if (elem.ids) {
        const idsToDelete = elem.ids.split(',').map((id: string) => id.trim());
        idsToDelete.forEach((id: string) => elementsToDelete.add(id));
      }
      continue;
    }

    // Convert tool element payload into standard Excalidraw element object
    const formatted: any = {
      type: elem.type || 'rectangle',
      id: elem.id || `elem_${Math.random().toString(36).substr(2, 9)}`,
      x: Number(elem.x ?? 100),
      y: Number(elem.y ?? 100),
      width: Number(elem.width ?? 140),
      height: Number(elem.height ?? 70),
      strokeColor: elem.strokeColor || '#1e1e1e',
      backgroundColor: elem.backgroundColor || 'transparent',
      fillStyle: elem.fillStyle || 'solid',
      strokeWidth: Number(elem.strokeWidth || 2),
      roughness: Number(elem.roughness || 1),
      opacity: Number(elem.opacity || 100),
    };

    if (elem.roundness) {
      formatted.roundness = elem.roundness;
    }

    if (elem.points) {
      formatted.points = elem.points;
    } else if (formatted.type === 'arrow' || formatted.type === 'line') {
      formatted.points = [[0, 0], [formatted.width, formatted.height]];
    }

    if (elem.endArrowhead) {
      formatted.endArrowhead = elem.endArrowhead;
    }

    if (formatted.type === 'text') {
      const textStr = typeof elem.text === 'string' ? elem.text : (elem.label?.text || elem.label || 'Text');
      formatted.text = textStr;
      formatted.fontSize = elem.fontSize || elem.label?.fontSize || 20;
    } else if (elem.label) {
      const labelText = typeof elem.label === 'string' ? elem.label : elem.label.text;
      if (labelText) {
        formatted.label = {
          text: labelText,
          fontSize: elem.label?.fontSize || 16,
          strokeColor: elem.label?.strokeColor || '#1e1e1e'
        };
      }
    } else if (elem.text) {
      formatted.label = { text: elem.text, fontSize: 16 };
    }

    rawNewElements.push(formatted);
  }

  // 1. Convert new raw elements to Excalidraw elements
  const convertedNewElements = convert(rawNewElements);

  // 2. Merge with existing elements & remove overlapping old elements
  const newElemMap = new Map<string, any>(
    convertedNewElements.map((el: any) => [el.id, el])
  );
  const newElementsList = Array.from(newElemMap.values());

  const updatedExisting = currentSceneElements
    .filter((el: any) => {
      if (elementsToDelete.has(el.id)) return false;

      // Deduplicate: If a new element is placed at almost the same position (especially text), discard the old element
      const isOverlappedByNew = newElementsList.some((newEl: any) => {
        if (newEl.id === el.id) return false; // same ID handled in map
        if (el.type === 'text' && newEl.type === 'text') {
          const dx = Math.abs(Number(el.x || 0) - Number(newEl.x || 0));
          const dy = Math.abs(Number(el.y || 0) - Number(newEl.y || 0));
          return dx < 150 && dy < 40; // Near-by text is considered replaced
        }
        return false;
      });

      return !isOverlappedByNew;
    })
    .map((el: any) => {
      if (newElemMap.has(el.id)) {
        const replacement = newElemMap.get(el.id);
        newElemMap.delete(el.id);
        return {
          ...el,
          ...replacement,
          version: (el.version || 1) + 1,
          versionNonce: Math.floor(Math.random() * 100000)
        };
      }
      return el;
    });

  return [...updatedExisting, ...Array.from(newElemMap.values())];
}
