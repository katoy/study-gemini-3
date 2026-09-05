// Sketch 要素マージ用純粋関数モジュール
// React/DOM 非依存で、Node 環境の単体テストから直接テスト可能

export type ElementConverter = (rawElements: any[]) => any[];

// デフォルトのコンバーター（そのまま通す）
export const defaultConverter: ElementConverter = (rawElements) => rawElements;

export function mergeServerElements(
  currentSceneElements: any[],
  serverElements: any[],
  convert: ElementConverter = defaultConverter
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

    const formatted: any = {
      type: elem.type || 'rectangle',
      id: elem.id || `sketch_${Math.random().toString(36).substring(2, 9)}`,
      name: elem.name || elem.text || elem.type || 'Layer',
      x: Number(elem.x ?? 100),
      y: Number(elem.y ?? 100),
      width: Number(elem.width ?? 140),
      height: Number(elem.height ?? 70),
      strokeColor: elem.strokeColor || '#0f172a',
      backgroundColor: elem.backgroundColor || 'transparent',
      fillStyle: elem.fillStyle || 'solid',
      strokeStyle: elem.strokeStyle || 'solid',
      strokeWidth: Number(elem.strokeWidth || 2),
      opacity: Number(elem.opacity || 100),
    };

    if (elem.angle !== undefined) {
      formatted.angle = elem.angle;
    }

    if (elem.points) {
      formatted.points = elem.points;
    } else if (formatted.type === 'arrow' || formatted.type === 'line') {
      formatted.points = [[0, 0], [formatted.width, formatted.height]];
    }

    if (elem.startArrowhead !== undefined) {
      formatted.startArrowhead = elem.startArrowhead;
    }

    if (elem.endArrowhead) {
      formatted.endArrowhead = elem.endArrowhead;
    }

    if (formatted.type === 'text') {
      const textStr = typeof elem.text === 'string' ? elem.text : (elem.label?.text || elem.label || 'Text');
      formatted.text = textStr;
      formatted.fontSize = elem.fontSize || elem.label?.fontSize || 18;
    } else if (elem.label) {
      const labelText = typeof elem.label === 'string' ? elem.label : elem.label.text;
      if (labelText) {
        formatted.label = {
          text: labelText,
          fontSize: elem.label?.fontSize || 16,
          strokeColor: elem.label?.strokeColor || '#0f172a'
        };
      }
    } else if (elem.text) {
      formatted.label = { text: elem.text, fontSize: 16 };
    }

    rawNewElements.push(formatted);
  }

  // 1. Convert new raw elements
  const convertedNewElements = convert(rawNewElements);

  // 2. Merge with existing elements & remove overlapping old elements
  const newElemMap = new Map<string, any>(
    convertedNewElements.map((el: any) => [el.id, el])
  );
  const newElementsList = Array.from(newElemMap.values());

  const updatedExisting = currentSceneElements
    .filter((el: any) => {
      if (elementsToDelete.has(el.id)) return false;

      // 重複排除: 新しいテキスト要素とほぼ同位置にある古いテキスト要素を削除
      const isOverlappedByNew = newElementsList.some((newEl: any) => {
        if (newEl.id === el.id) return false;
        if (el.type === 'text' && newEl.type === 'text') {
          const dx = Math.abs(Number(el.x || 0) - Number(newEl.x || 0));
          const dy = Math.abs(Number(el.y || 0) - Number(newEl.y || 0));
          return dx < 150 && dy < 40;
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
          version: (el.version || 1) + 1
        };
      }
      return el;
    });

  return [...updatedExisting, ...Array.from(newElemMap.values())];
}
