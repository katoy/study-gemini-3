// 生の要素配列を Excalidraw 要素に変換する関数の型。
// 実体は呼び出し元（App.tsx）から @excalidraw/excalidraw の convertToExcalidrawElements を注入する。
// このファイル自体が @excalidraw/excalidraw を import すると（ブラウザ実行前提の初期化コードが
// 走るため）Node環境での単体テストが困難になるので、依存注入で切り離している。
export type ElementConverter = (rawElements: any[]) => any[];

// server から届いた要素配列を既存シーン要素とマージする純粋関数。
// App コンポーネントから切り出すことで単体テスト可能にしている（React/DOM への依存なし）。
// カメラ更新はスキップ、DEL指定は削除、同一IDは上書き、近接テキストは重複排除する。
export function applyElementModifications(el: any, mod: any): any {
  if (!mod) return el;
  let updated = { ...el };

  if (mod.move) {
    if (mod.move.isRelative) {
      updated.x = (updated.x || 0) + (mod.move.dx || 0);
      updated.y = (updated.y || 0) + (mod.move.dy || 0);
    } else {
      if (mod.move.x !== undefined) updated.x = mod.move.x;
      if (mod.move.y !== undefined) updated.y = mod.move.y;
    }
  }

  if (mod.resize) {
    if (mod.resize.isScale) {
      const factor = mod.resize.scaleFactor;
      if (factor && factor > 0) {
        updated.width = Math.round((updated.width || 10) * factor);
        updated.height = Math.round((updated.height || 10) * factor);
        if (Array.isArray(updated.points)) {
          updated.points = updated.points.map(([px, py]: [number, number]) => [px * factor, py * factor]);
        }
      }
    } else {
      if (mod.resize.width !== undefined) updated.width = mod.resize.width;
      if (mod.resize.height !== undefined) updated.height = mod.resize.height;
    }
  }

  if (mod.rotate) {
    const numAngle = mod.rotate.angle || 0;
    const radAngle = Math.abs(numAngle) > Math.PI * 2 ? (numAngle * Math.PI) / 180 : numAngle;
    if (mod.rotate.isRelative) {
      updated.angle = (updated.angle || 0) + radAngle;
    } else {
      updated.angle = radAngle;
    }
  }

  return updated;
}

// 1. Convert new raw elements to Excalidraw elements
// 2. Merge with existing elements & remove overlapping old elements
export function mergeServerElements(
  currentSceneElements: any[],
  serverElements: any[],
  convert: ElementConverter
): any[] {
  const elementsToDelete = new Set<string>();
  const elementsToHide = new Set<string>();
  const elementsToShow = new Map<string, number>();
  const elementsToGroup = new Map<string, string>();
  const elementsToUngroup = new Set<string>();
  const elementLinks = new Map<string, string>();
  const elementsToFront = new Set<string>();
  const elementsToBack = new Set<string>();
  const elementModifications = new Map<string, {
    move?: { x?: number; y?: number; dx?: number; dy?: number; isRelative: boolean };
    resize?: { width?: number; height?: number; scaleFactor?: number; isScale: boolean };
    rotate?: { angle: number; isRelative: boolean };
  }>();
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

    if (elem.type === 'group') {
      if (elem.groupId && elem.ids) {
        const ids = elem.ids.split(',').map((id: string) => id.trim());
        ids.forEach((id: string) => elementsToGroup.set(id, elem.groupId));
      }
      continue;
    }

    if (elem.type === 'ungroup') {
      if (elem.ids) {
        const ids = elem.ids.split(',').map((id: string) => id.trim());
        ids.forEach((id: string) => elementsToUngroup.add(id));
      }
      continue;
    }

    if (elem.type === 'link') {
      if (elem.id && elem.link) {
        elementLinks.set(elem.id, elem.link);
      }
      continue;
    }

    if (elem.type === 'layer') {
      if (elem.ids) {
        const ids = elem.ids.split(',').map((id: string) => id.trim());
        if (elem.position === 'front') {
          ids.forEach((id: string) => elementsToFront.add(id));
        } else if (elem.position === 'back') {
          ids.forEach((id: string) => elementsToBack.add(id));
        }
      }
      continue;
    }

    if (elem.type === 'hide') {
      if (elem.ids) {
        const ids = elem.ids.split(',').map((id: string) => id.trim());
        ids.forEach((id: string) => elementsToHide.add(id));
      }
      continue;
    }

    if (elem.type === 'show') {
      if (elem.ids) {
        const ids = elem.ids.split(',').map((id: string) => id.trim());
        const opacity = Number(elem.opacity ?? 100);
        ids.forEach((id: string) => elementsToShow.set(id, opacity));
      }
      continue;
    }

    if (elem.type === 'move') {
      if (elem.id) {
        const currentMod = elementModifications.get(elem.id) || {};
        currentMod.move = {
          x: elem.x,
          y: elem.y,
          dx: elem.dx,
          dy: elem.dy,
          isRelative: Boolean(elem.isRelative)
        };
        elementModifications.set(elem.id, currentMod);
      }
      continue;
    }

    if (elem.type === 'resize') {
      if (elem.id) {
        const currentMod = elementModifications.get(elem.id) || {};
        currentMod.resize = {
          width: elem.width,
          height: elem.height,
          scaleFactor: elem.scaleFactor,
          isScale: Boolean(elem.isScale)
        };
        elementModifications.set(elem.id, currentMod);
      }
      continue;
    }

    if (elem.type === 'rotate') {
      if (elem.id) {
        const currentMod = elementModifications.get(elem.id) || {};
        currentMod.rotate = {
          angle: Number(elem.angle || 0),
          isRelative: Boolean(elem.isRelative)
        };
        elementModifications.set(elem.id, currentMod);
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
      strokeStyle: elem.strokeStyle || 'solid',
      strokeWidth: Number(elem.strokeWidth || 2),
      roughness: Number(elem.roughness || 1),
      opacity: Number(elem.opacity || 100),
    };

    if (elem.roundness !== undefined) {
      formatted.roundness = elem.roundness;
    }
    if (elem.fontFamily !== undefined) {
      formatted.fontFamily = elem.fontFamily;
    }
    if (elem.textAlign !== undefined) {
      formatted.textAlign = elem.textAlign;
    }
    if (elem.verticalAlign !== undefined) {
      formatted.verticalAlign = elem.verticalAlign;
    }

    if (elem.points) {
      formatted.points = elem.points;
    } else if (formatted.type === 'arrow' || formatted.type === 'line') {
      formatted.points = [[0, 0], [formatted.width, formatted.height]];
    }

    if (elem.angle !== undefined) {
      formatted.angle = elem.angle;
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

  const convertedNewElements = convert(rawNewElements);
  const newElemMap = new Map<string, any>(
    convertedNewElements.map((el: any) => [el.id, el])
  );
  const newElementsList = Array.from(newElemMap.values());

  const updatedExisting = currentSceneElements
    .filter((el: any) => {
      if (elementsToDelete.has('*') || elementsToDelete.has('all') || elementsToDelete.has(el.id)) return false;

      // Deduplicate: If a new element is placed at almost the same position (especially text), discard the old element
      const isOverlappedByNew = newElementsList.some((newEl: any) => {
        if (newEl.id === el.id) return false; // same ID handled in map
        if (el.type === 'text' && newEl.type === 'text') {
          const dx = Math.abs(Number(el.x || 0) - Number(newEl.x || 0));
          const dy = Math.abs(Number(el.y || 0) - Number(newEl.y || 0));
          return dx <= 10 && dy <= 10; // Only exact or virtually identical position is considered replaced
        }
        return false;
      });

      return !isOverlappedByNew;
    })
    .map((el: any) => {
      let current = el;
      let modified = false;

      if (newElemMap.has(el.id)) {
        const replacement = newElemMap.get(el.id);
        newElemMap.delete(el.id);
        current = { ...current, ...replacement };
        modified = true;
      }

      if (elementsToHide.has(el.id)) {
        current = {
          ...current,
          _prevOpacity: current.opacity !== 0 ? current.opacity : (current._prevOpacity || 100),
          opacity: 0
        };
        modified = true;
      } else if (elementsToShow.has(el.id)) {
        const targetOp = elementsToShow.get(el.id) ?? current._prevOpacity ?? 100;
        current = {
          ...current,
          opacity: targetOp
        };
        modified = true;
      }

      if (elementsToGroup.has(el.id)) {
        const gId = elementsToGroup.get(el.id)!;
        current = {
          ...current,
          groupIds: Array.from(new Set([...(current.groupIds || []), gId]))
        };
        modified = true;
      } else if (elementsToUngroup.has(el.id)) {
        current = {
          ...current,
          groupIds: []
        };
        modified = true;
      }

      if (elementLinks.has(el.id)) {
        current = {
          ...current,
          link: elementLinks.get(el.id)
        };
        modified = true;
      }

      if (elementModifications.has(el.id)) {
        current = applyElementModifications(current, elementModifications.get(el.id));
        modified = true;
      }

      if (modified) {
        return {
          ...current,
          version: (current.version || 1) + 1,
          versionNonce: Math.floor(Math.random() * 100000)
        };
      }
      return current;
    });

  const finalNewElements = Array.from(newElemMap.values()).map((el: any) => {
    let current = el;
    if (elementsToHide.has(el.id)) {
      current = { ...current, _prevOpacity: current.opacity, opacity: 0 };
    } else if (elementsToShow.has(el.id)) {
      current = { ...current, opacity: elementsToShow.get(el.id) };
    }
    if (elementsToGroup.has(el.id)) {
      const gId = elementsToGroup.get(el.id)!;
      current = {
        ...current,
        groupIds: Array.from(new Set([...(current.groupIds || []), gId]))
      };
    }
    if (elementLinks.has(el.id)) {
      current = { ...current, link: elementLinks.get(el.id) };
    }
    if (elementModifications.has(el.id)) {
      current = applyElementModifications(current, elementModifications.get(el.id));
    }
    return current;
  });

  const combined = [...updatedExisting, ...finalNewElements];

  // レイヤー順序（フロント・バック）の並び替え
  if (elementsToBack.size > 0 || elementsToFront.size > 0) {
    const backList: any[] = [];
    const middleList: any[] = [];
    const frontList: any[] = [];

    for (const el of combined) {
      if (elementsToBack.has(el.id)) {
        backList.push(el);
      } else if (elementsToFront.has(el.id)) {
        frontList.push(el);
      } else {
        middleList.push(el);
      }
    }
    return [...backList, ...middleList, ...frontList];
  }

  return combined;
}
