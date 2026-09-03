// server.ts から DSL パース関連のロジックを切り出したモジュール。
// 副作用（Express/WebSocket 起動など）を持たないため、単体テストからそのまま import できる。

// Color Palette for DSL conversion
export const COLOR_PALETTE: Record<string, { fill: string; stroke: string }> = {
  blue: { fill: '#a5d8ff', stroke: '#4a9eed' },
  green: { fill: '#b2f2bb', stroke: '#22c55e' },
  orange: { fill: '#ffd8a8', stroke: '#f59e0b' },
  purple: { fill: '#d0bfff', stroke: '#8b5cf6' },
  red: { fill: '#ffc9c9', stroke: '#ef4444' },
  yellow: { fill: '#fff3bf', stroke: '#eab308' },
  teal: { fill: '#c3fae8', stroke: '#0d9488' },
  dark: { fill: '#e9ecef', stroke: '#1e1e1e' },
  gray: { fill: '#f1f3f5', stroke: '#495057' },
  default: { fill: 'transparent', stroke: '#1e1e1e' }
};

// Converts compact DSL string commands into Excalidraw element objects
// elementMap を呼び出し元と共有することで、1リクエスト内で draw_dsl が複数回
// 呼ばれても（段階的描画）ARROW の id 参照解決を呼び出しをまたいで維持できる
export function parseDSLToElements(commands: string[], elementMap: Map<string, any> = new Map()): any[] {
  const elements: any[] = [];

  for (const rawCmd of commands) {
    if (typeof rawCmd !== 'string') continue;
    const cmd = rawCmd.trim();
    if (!cmd) continue;

    const parts = cmd.split('|').map(p => p.trim());
    const type = parts[0].toUpperCase();

    if (type === 'DEL') {
      elements.push({ type: 'delete', ids: parts[1] || '' });
      continue;
    }

    if (type === 'RECT' || type === 'ELLIPSE' || type === 'DIAMOND') {
      // Syntax: TYPE|id|x|y|width|height|color|label
      const id = parts[1] || `elem_${Math.random().toString(36).substring(2, 7)}`;
      const x = Number(parts[2] || 100);
      const y = Number(parts[3] || 100);
      const width = Number(parts[4] || 140);
      const height = Number(parts[5] || 70);
      const colorKey = (parts[6] || 'blue').toLowerCase();
      const labelText = parts[7] || '';

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.blue;
      const shapeType = type === 'RECT' ? 'rectangle' : type === 'ELLIPSE' ? 'ellipse' : 'diamond';

      const elemObj = {
        type: shapeType,
        id,
        x,
        y,
        width,
        height,
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: 'solid',
        strokeWidth: 2,
        roughness: 1,
        label: labelText ? { text: labelText, fontSize: 16, strokeColor: '#1e1e1e' } : undefined
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'TEXT') {
      // Syntax: TEXT|id|x|y|fontSize|color|text
      const id = parts[1] || `txt_${Math.random().toString(36).substring(2, 7)}`;
      const x = Number(parts[2] || 100);
      const y = Number(parts[3] || 100);
      const fontSize = Number(parts[4] || 18);
      const colorKey = (parts[5] || 'dark').toLowerCase();
      const text = parts[6] || '';

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.dark;

      const elemObj = {
        type: 'text',
        id,
        x,
        y,
        text,
        fontSize,
        strokeColor: colors.stroke
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'ARROW') {
      // Syntax: ARROW|id|fromRef|toRef|color|label
      const id = parts[1] || `arr_${Math.random().toString(36).substring(2, 7)}`;
      const fromRef = parts[2] || '0,0';
      const toRef = parts[3] || '100,0';
      const colorKey = (parts[4] || 'dark').toLowerCase();
      const labelText = parts[5] || '';

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.dark;

      let startX = 0, startY = 0, endX = 100, endY = 0;

      if (fromRef.includes(',')) {
        const [x, y] = fromRef.split(',').map(Number);
        startX = x || 0;
        startY = y || 0;
      } else if (elementMap.has(fromRef)) {
        const source = elementMap.get(fromRef);
        startX = source.x + source.width / 2;
        startY = source.y + source.height / 2;
      }

      if (toRef.includes(',')) {
        const [x, y] = toRef.split(',').map(Number);
        endX = x || 100;
        endY = y || 0;
      } else if (elementMap.has(toRef)) {
        const target = elementMap.get(toRef);
        endX = target.x + target.width / 2;
        endY = target.y + target.height / 2;
      }

      const dx = endX - startX;
      const dy = endY - startY;

      elements.push({
        type: 'arrow',
        id,
        x: startX,
        y: startY,
        width: Math.abs(dx) || 1,
        height: Math.abs(dy) || 1,
        strokeColor: colors.stroke,
        backgroundColor: 'transparent',
        fillStyle: 'solid',
        strokeWidth: 2,
        roughness: 1,
        endArrowhead: 'arrow',
        points: [[0, 0], [dx, dy]],
        label: labelText ? { text: labelText, fontSize: 14, strokeColor: '#1e1e1e' } : undefined
      });
    }
  }

  return elements;
}

// モデルごとの thinking 設定。thinking は出力（テキスト・関数呼び出し）が
// 始まる前に発生する先行遅延になるため、flash 系は無効化して最小化し、
// pro 系は 0 を拒否される可能性があるため最小許容値を使う
export function getThinkingConfigFor(modelName: string): { thinkingBudget: number } {
  if (modelName.includes('pro')) {
    return { thinkingBudget: 128 };
  }
  return { thinkingBudget: 0 };
}
