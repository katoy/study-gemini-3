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
      // Syntax: TYPE|id|x|y|width|height|color|label|angle
      // またはカンマ座標: TYPE|id|x,y,w,h|color|label|angle
      const id = parts[1] || `elem_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 140, height = 70;
      let colorKey = 'blue', labelText = '', rawAngle = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        width = Number(coords[2] || 140);
        height = Number(coords[3] || 70);
        colorKey = (parts[3] || 'blue').toLowerCase();
        labelText = parts[4] || '';
        rawAngle = parts[5] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        width = Number(parts[4] || 140);
        height = Number(parts[5] || 70);
        colorKey = (parts[6] || 'blue').toLowerCase();
        labelText = parts[7] || '';
        rawAngle = parts[8] || '';
      }

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.blue;
      const shapeType = type === 'RECT' ? 'rectangle' : type === 'ELLIPSE' ? 'ellipse' : 'diamond';
      const numAngle = Number(rawAngle || 0);
      const angle = Math.abs(numAngle) > Math.PI * 2 ? (numAngle * Math.PI) / 180 : numAngle;

      const elemObj: any = {
        type: shapeType,
        id,
        x,
        y,
        width,
        height,
        text: labelText || '',
        fontSize: 16,
        textAlign: 'center',
        verticalAlign: 'middle',
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: 'solid',
        strokeStyle: 'solid',
        strokeWidth: 2,
        roughness: 1
      };

      if (angle !== 0) {
        elemObj.angle = angle;
      }

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'TRIANGLE') {
      // Syntax: TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label
      const id = parts[1] || `tri_${Math.random().toString(36).substring(2, 7)}`;
      const p1 = (parts[2] || '0,0').split(',').map(Number);
      const p2 = (parts[3] || '100,0').split(',').map(Number);
      const p3 = (parts[4] || '50,100').split(',').map(Number);
      const colorKey = (parts[5] || 'blue').toLowerCase();
      const labelText = parts[6] || '';

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.blue;
      const x1 = p1[0] || 0, y1 = p1[1] || 0;
      const x2 = p2[0] || 0, y2 = p2[1] || 0;
      const x3 = p3[0] || 0, y3 = p3[1] || 0;

      const minX = Math.min(x1, x2, x3);
      const minY = Math.min(y1, y2, y3);
      const maxX = Math.max(x1, x2, x3);
      const maxY = Math.max(y1, y2, y3);
      const width = Math.max(maxX - minX, 1);
      const height = Math.max(maxY - minY, 1);

      const elemObj = {
        type: 'line',
        id,
        x: minX,
        y: minY,
        width,
        height,
        text: labelText || '',
        fontSize: 16,
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: 'solid',
        strokeStyle: 'solid',
        strokeWidth: 2,
        roughness: 1,
        startArrowhead: null,
        endArrowhead: null,
        points: [
          [x1 - minX, y1 - minY],
          [x2 - minX, y2 - minY],
          [x3 - minX, y3 - minY],
          [x1 - minX, y1 - minY]
        ]
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'TEXT') {
      // Syntax: TEXT|id|x|y|fontSize|color|text
      // またはカンマ座標: TEXT|id|x,y|fontSize|color|text
      const id = parts[1] || `txt_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, fontSize = 18, colorKey = 'dark', text = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        fontSize = Number(parts[3] || 18);
        colorKey = (parts[4] || 'dark').toLowerCase();
        text = parts[5] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        fontSize = Number(parts[4] || 18);
        colorKey = (parts[5] || 'dark').toLowerCase();
        text = parts[6] || '';
      }

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.dark;

      const elemObj = {
        type: 'text',
        id,
        x,
        y,
        width: Math.max(text.length * (fontSize * 0.55), 50),
        height: fontSize * 1.5,
        text,
        fontSize,
        textAlign: 'left',
        verticalAlign: 'top',
        strokeColor: colors.stroke,
        backgroundColor: 'transparent',
        fillStyle: 'solid',
        strokeStyle: 'solid',
        roughness: 1
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'ARROW' || type === 'LINE') {
      // Syntax: ARROW/LINE|id|fromRef|toRef|color|label
      const id = parts[1] || `${type === 'LINE' ? 'line' : 'arr'}_${Math.random().toString(36).substring(2, 7)}`;
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
        type: type === 'LINE' ? 'line' : 'arrow',
        id,
        x: startX,
        y: startY,
        width: Math.abs(dx) || 1,
        height: Math.abs(dy) || 1,
        text: labelText || '',
        fontSize: 14,
        strokeColor: colors.stroke,
        backgroundColor: 'transparent',
        fillStyle: 'solid',
        strokeStyle: 'solid',
        strokeWidth: 2,
        roughness: 1,
        startArrowhead: null,
        endArrowhead: type === 'LINE' ? null : 'arrow',
        points: [[0, 0], [dx, dy]]
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
