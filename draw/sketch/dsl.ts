// Sketch アプリおよび Sketch-mcp 互換の DSL パーサーモジュール
// 副作用を持たない純粋関数群として設計されており、単体テスト可能

export interface SketchElementStyle {
  fill: string;
  stroke: string;
  strokeWidth: number;
  opacity: number;
  fillStyle?: string;
  strokeStyle?: string;
}

export interface SketchElement {
  id: string;
  type: 'rectangle' | 'oval' | 'triangle' | 'diamond' | 'line' | 'arrow' | 'text' | 'artboard' | 'group';
  name?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  angle?: number;
  text?: string;
  fontSize?: number;
  textAlign?: 'left' | 'center' | 'right';
  verticalAlign?: 'top' | 'middle' | 'bottom';
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
  children?: SketchElement[];
}

// カラーパレット定義（Sketch UI / プレゼンテーション向け）
export const COLOR_PALETTE: Record<string, { fill: string; stroke: string }> = {
  blue: { fill: '#e0f2fe', stroke: '#0284c7' },
  green: { fill: '#dcfce7', stroke: '#16a34a' },
  orange: { fill: '#ffedd5', stroke: '#ea580c' },
  purple: { fill: '#f3e8ff', stroke: '#9333ea' },
  red: { fill: '#fee2e2', stroke: '#dc2626' },
  yellow: { fill: '#fef9c3', stroke: '#ca8a04' },
  teal: { fill: '#ccfbf1', stroke: '#0d9488' },
  dark: { fill: '#f1f5f9', stroke: '#0f172a' },
  gray: { fill: '#f8fafc', stroke: '#475569' },
  sketch: { fill: '#fff7ed', stroke: '#f97316' }, // Sketch signature orange
  default: { fill: 'transparent', stroke: '#0f172a' }
};

// DSL 文字列配列を Sketch 要素オブジェクト配列へパース
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

    if (type === 'RECT' || type === 'OVAL' || type === 'ELLIPSE' || type === 'DIAMOND') {
      // Syntax: TYPE|id|x|y|width|height|color|label|angle
      // またはカンマ座標: TYPE|id|x,y,w,h|color|label|angle
      const id = parts[1] || `sketch_${Math.random().toString(36).substring(2, 7)}`;
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
      const shapeType = (type === 'RECT') ? 'rectangle' : (type === 'DIAMOND' ? 'diamond' : 'oval');
      const numAngle = Number(rawAngle || 0);
      const angle = Math.abs(numAngle) > Math.PI * 2 ? (numAngle * Math.PI) / 180 : numAngle;

      const elemObj: SketchElement = {
        type: shapeType,
        id,
        name: labelText || shapeType,
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
        opacity: 100
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

      const elemObj: SketchElement = {
        type: 'triangle',
        id,
        name: labelText || 'Triangle',
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
        opacity: 100,
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
      const id = parts[1] || `txt_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, fontSize = 18, colorKey = 'dark', text = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        fontSize = Number(parts[3] || 18);
        colorKey = (parts[4] || 'dark').toLowerCase();
        text = parts.slice(5).join('|') || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        fontSize = Number(parts[4] || 18);
        colorKey = (parts[5] || 'dark').toLowerCase();
        text = parts.slice(6).join('|') || '';
      }

      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.dark;
      const approxWidth = Math.max(text.length * (fontSize * 0.65), 50);
      const approxHeight = fontSize * 1.5;

      const elemObj: SketchElement = {
        type: 'text',
        id,
        name: text.substring(0, 20) || 'Text',
        x,
        y,
        width: approxWidth,
        height: approxHeight,
        text,
        fontSize,
        textAlign: 'left',
        verticalAlign: 'top',
        strokeColor: colors.stroke,
        backgroundColor: 'transparent',
        fillStyle: 'solid',
        strokeStyle: 'solid',
        strokeWidth: 1,
        opacity: 100
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'ARROW' || type === 'LINE') {
      // Syntax: ARROW|id|fromIdOrX,Y|toIdOrX,Y|color|label
      const id = parts[1] || `arr_${Math.random().toString(36).substring(2, 7)}`;
      const fromSpec = parts[2] || '100,100';
      const toSpec = parts[3] || '200,200';
      const colorKey = (parts[4] || 'dark').toLowerCase();
      const labelText = parts[5] || '';
      const colors = COLOR_PALETTE[colorKey] || COLOR_PALETTE.dark;

      let startX = 0, startY = 0, endX = 100, endY = 0;

      if (fromSpec.includes(',')) {
        const [x, y] = fromSpec.split(',').map(Number);
        startX = Number.isFinite(x) ? x : 0;
        startY = Number.isFinite(y) ? y : 0;
      } else if (elementMap.has(fromSpec)) {
        const fromElem = elementMap.get(fromSpec);
        startX = fromElem.x + (fromElem.width / 2);
        startY = fromElem.y + (fromElem.height / 2);
      }

      if (toSpec.includes(',')) {
        const [x, y] = toSpec.split(',').map(Number);
        endX = Number.isFinite(x) ? x : 100;
        endY = Number.isFinite(y) ? y : 0;
      } else if (elementMap.has(toSpec)) {
        const toElem = elementMap.get(toSpec);
        endX = toElem.x + (toElem.width / 2);
        endY = toElem.y + (toElem.height / 2);
      }

      const minX = Math.min(startX, endX);
      const minY = Math.min(startY, endY);
      const w = Math.abs(endX - startX) || 1;
      const h = Math.abs(endY - startY) || 1;

      const p1 = [startX - minX, startY - minY];
      const p2 = [endX - minX, endY - minY];

      const elemObj: SketchElement = {
        type: type === 'ARROW' ? 'arrow' : 'line',
        id,
        name: labelText || (type === 'ARROW' ? 'Arrow' : 'Line'),
        x: minX,
        y: minY,
        width: w,
        height: h,
        strokeColor: colors.stroke,
        backgroundColor: 'transparent',
        strokeWidth: 2,
        opacity: 100,
        points: [p1, p2],
        startArrowhead: null,
        endArrowhead: type === 'ARROW' ? 'arrow' : null,
        text: labelText || ''
      };

      if (labelText) {
        elemObj.label = {
          text: labelText,
          fontSize: 14,
          strokeColor: colors.stroke
        };
      }

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    }
  }

  return elements;
}

// Thinking 設定を取得するヘルパー関数
export function getThinkingConfigFor(modelName: string) {
  if (modelName.includes('gemini-2.0') || modelName.includes('gemini-2.5') || modelName.includes('gemini-3')) {
    return {
      thinkingBudget: 0
    };
  }
  return undefined;
}
