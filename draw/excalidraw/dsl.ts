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
  white: { fill: '#ffffff', stroke: '#1e1e1e' },
  black: { fill: '#1e1e1e', stroke: '#1e1e1e' },
  pink: { fill: '#fcc2d7', stroke: '#e64980' },
  cyan: { fill: '#99e9f2', stroke: '#0c8599' },
  violet: { fill: '#eebefa', stroke: '#ae3ec9' },
  lime: { fill: '#d8f5a2', stroke: '#74b816' },
  indigo: { fill: '#c5d2fe', stroke: '#4f46e5' },
  default: { fill: 'transparent', stroke: '#1e1e1e' }
};

export function resolveColor(colorStr: string, fallback: { fill: string; stroke: string } = COLOR_PALETTE.blue): { fill: string; stroke: string } {
  if (!colorStr) return fallback;
  const lower = colorStr.toLowerCase().trim();
  if (COLOR_PALETTE[lower]) return COLOR_PALETTE[lower];
  if (lower.startsWith('#')) {
    // If it's a pure white hex color, provide a dark stroke so it is visible on white background
    if (lower === '#ffffff' || lower === '#fff') {
      return { fill: '#ffffff', stroke: '#1e1e1e' };
    }
    return { fill: colorStr, stroke: colorStr };
  }
  return fallback;
}

export interface StyleProps {
  strokeStyle?: 'solid' | 'dashed' | 'dotted';
  fillStyle?: 'solid' | 'hachure' | 'cross-hatch' | 'dots';
  strokeWidth?: number;
  roughness?: number;
  opacity?: number;
  roundness?: { type: number } | null;
  fontFamily?: number; // 1: Virgil, 2: Helvetica, 3: Cascadia
  textAlign?: 'left' | 'center' | 'right';
  verticalAlign?: 'top' | 'middle' | 'bottom';
  startArrowhead?: string | null;
  endArrowhead?: string | null;
}

// Parses styles string e.g. "stroke=dashed;fill=hachure;round;w=3;font=mono;align=center"
// or comma-separated: "dashed,hachure,round,w=3"
export function parseStyleProps(rawStyleStr?: string): StyleProps {
  if (!rawStyleStr) return {};
  const props: StyleProps = {};

  const tokens = rawStyleStr.split(/[;, ]+/).filter(Boolean);

  for (const token of tokens) {
    const hasEqual = token.includes('=');
    const [rawKey, rawVal] = hasEqual ? token.split('=').map(s => s.trim()) : [token.trim(), ''];
    const key = rawKey.toLowerCase();
    const val = rawVal.toLowerCase();

    if (key === 'dashed' || (key === 'stroke' && val === 'dashed')) {
      props.strokeStyle = 'dashed';
    } else if (key === 'dotted' || (key === 'stroke' && val === 'dotted')) {
      props.strokeStyle = 'dotted';
    } else if (key === 'solid') {
      if (val === 'fill') props.fillStyle = 'solid';
      else props.strokeStyle = 'solid';
    } else if (key === 'stroke' && val === 'solid') {
      props.strokeStyle = 'solid';
    } else if (key === 'hachure' || (key === 'fill' && val === 'hachure')) {
      props.fillStyle = 'hachure';
    } else if (key === 'cross-hatch' || key === 'crosshatch' || (key === 'fill' && (val === 'cross-hatch' || val === 'crosshatch'))) {
      props.fillStyle = 'cross-hatch';
    } else if (key === 'dots' || (key === 'fill' && val === 'dots')) {
      props.fillStyle = 'dots';
    } else if (key === 'fill' && val === 'solid') {
      props.fillStyle = 'solid';
    } else if (key === 'round' || key === 'rounded' || (key === 'roundness' && (val === 'round' || val === '1' || val === 'true'))) {
      props.roundness = { type: 3 };
    } else if (key === 'sharp' || (key === 'roundness' && (val === 'sharp' || val === '0' || val === 'false' || val === 'none'))) {
      props.roundness = null;
    } else if (key === 'w' || key === 'width' || key === 'strokewidth') {
      const w = Number(val || key.replace(/^w/, ''));
      if (!isNaN(w) && w > 0) props.strokeWidth = w;
    } else if (/^w\d+$/.test(key)) {
      const w = Number(key.substring(1));
      if (!isNaN(w) && w > 0) props.strokeWidth = w;
    } else if (key === 'rough' || key === 'roughness') {
      const r = Number(val);
      if (!isNaN(r)) props.roughness = r;
    } else if (key === 'opacity') {
      const op = Number(val);
      if (!isNaN(op)) props.opacity = op;
    } else if (key === 'font' || key === 'fontfamily') {
      if (val === 'virgil' || val === 'hand' || val === 'handwritten' || val === '1') props.fontFamily = 1;
      else if (val === 'helvetica' || val === 'sans' || val === 'normal' || val === '2') props.fontFamily = 2;
      else if (val === 'cascadia' || val === 'mono' || val === 'code' || val === '3') props.fontFamily = 3;
    } else if (key === 'virgil' || key === 'hand') {
      props.fontFamily = 1;
    } else if (key === 'sans' || key === 'helvetica') {
      props.fontFamily = 2;
    } else if (key === 'mono' || key === 'code' || key === 'cascadia') {
      props.fontFamily = 3;
    } else if (key === 'align' || key === 'textalign') {
      if (val === 'left' || val === 'center' || val === 'right') props.textAlign = val;
    } else if (key === 'left' || key === 'center' || key === 'right') {
      props.textAlign = key as any;
    } else if (key === 'valign' || key === 'verticalalign') {
      if (val === 'top' || val === 'middle' || val === 'bottom') props.verticalAlign = val;
    } else if (key === 'startarrow' || key === 'start') {
      props.startArrowhead = val === 'none' ? null : (val || 'arrow');
    } else if (key === 'endarrow' || key === 'end') {
      props.endArrowhead = val === 'none' ? null : (val || 'arrow');
    } else if (key === 'arrowhead' || key === 'arrowheads' || key === 'arrows' || key === 'arrow') {
      if (val === 'both' || val === 'double') {
        props.startArrowhead = 'arrow';
        props.endArrowhead = 'arrow';
      }
    } else if (key === 'both' || key === 'double') {
      props.startArrowhead = 'arrow';
      props.endArrowhead = 'arrow';
    }
  }

  return props;
}

// Generates points for a star
export function generateStarPoints(cx: number, cy: number, outerR: number, innerR: number, pointsCount = 5): [number, number][] {
  const points: [number, number][] = [];
  const step = Math.PI / pointsCount;
  let angle = -Math.PI / 2;

  for (let i = 0; i < 2 * pointsCount; i++) {
    const r = i % 2 === 0 ? outerR : innerR;
    const px = cx + r * Math.cos(angle);
    const py = cy + r * Math.sin(angle);
    points.push([px, py]);
    angle += step;
  }
  return points;
}

// Generates points for a cloud shape
export function generateCloudPoints(x: number, y: number, w: number, h: number): [number, number][] {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const rx = w / 2;
  const ry = h / 2;
  const numPoints = 16;
  const points: [number, number][] = [];

  for (let i = 0; i < numPoints; i++) {
    const theta = (i / numPoints) * Math.PI * 2;
    // Harmonic scalloping for fluffy cloud appearance
    const scallop = 0.82 + 0.18 * Math.cos(i * 3.5);
    const px = cx + rx * scallop * Math.cos(theta);
    const py = cy + ry * scallop * Math.sin(theta);
    points.push([px, py]);
  }
  return points;
}

// Helper to convert absolute points to relative coordinates and bounding box
function pointsToRelativePolygon(pointCoords: [number, number][]) {
  const xs = pointCoords.map(p => p[0]);
  const ys = pointCoords.map(p => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);

  const points = pointCoords.map(p => [p[0] - minX, p[1] - minY]);
  // Close polygon
  points.push([pointCoords[0][0] - minX, pointCoords[0][1] - minY]);

  return { minX, minY, width, height, points };
}

// Helper to resolve reference point (ID or comma coordinates)
export function resolveAnchor(ref: string, elementMap: Map<string, any>, defaultX: number, defaultY: number, isTarget: boolean = false): [number, number] {
  if (!ref) return [defaultX, defaultY];
  if (ref.includes(',')) {
    const [x, y] = ref.split(',').map(Number);
    const resolvedX = isTarget ? (x || defaultX) : (x || 0);
    const resolvedY = y || 0;
    return [resolvedX, resolvedY];
  }
  if (elementMap.has(ref)) {
    const el = elementMap.get(ref);
    return [el.x + (el.width || 0) / 2, el.y + (el.height || 0) / 2];
  }
  return [defaultX, defaultY];
}

// 安全な簡単な四則演算の評価
export function evaluateSimpleMath(expr: string): number {
  const sanitized = expr.replace(/\s+/g, '');
  if (!/^[-+*/0-9.()]+$/.test(sanitized)) return NaN;
  try {
    const fn = new Function(`"use strict"; return (${sanitized});`);
    const res = fn();
    return typeof res === 'number' && !isNaN(res) ? res : NaN;
  } catch {
    return NaN;
  }
}

// テンプレート置換 ({var} や {100 + i * 50})
export function interpolateTemplate(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{([^{}]+)\}/g, (match, rawExpr) => {
    let expr = rawExpr.trim();
    let hasReplaced = false;

    for (const [k, v] of Object.entries(vars)) {
      const regex = new RegExp(`\\b${k}\\b`, 'g');
      if (regex.test(expr)) {
        expr = expr.replace(regex, String(v));
        hasReplaced = true;
      }
    }

    if (!hasReplaced && !(expr in vars)) {
      // 数式のみの式かチェック
      const num = evaluateSimpleMath(expr);
      if (!isNaN(num)) {
        return String(num);
      }
      return match; // 変数が vars に存在しない場合は元の波括弧 {var} を保持
    }

    const num = evaluateSimpleMath(expr);
    if (!isNaN(num)) {
      return String(num);
    }
    return expr;
  });
}

// DSL プリプロセッサ: LET, DEF/CALL, FOR/REPEAT, CONNECT, ROW/COL を展開
export function preprocessDSL(rawCommands: string[]): string[] {
  const expanded: string[] = [];
  const variables: Record<string, string | number> = {};
  const methods = new Map<string, { params: string[]; bodyCommands: string[] }>();

  for (const rawCmd of rawCommands) {
    if (typeof rawCmd !== 'string') continue;
    let cmd = rawCmd.trim();
    if (!cmd) continue;

    // 変数置換
    cmd = interpolateTemplate(cmd, variables);

    const parts = cmd.split('|').map(p => p.trim());
    const type = parts[0].toUpperCase();

    // 1. LET 変数定義: LET|w=140|h=70|c=blue
    if (type === 'LET' || type === 'VAR') {
      for (let i = 1; i < parts.length; i++) {
        const token = parts[i];
        if (token.includes('=')) {
          const [k, v] = token.split('=').map(s => s.trim());
          const num = evaluateSimpleMath(v);
          variables[k] = isNaN(num) ? v : num;
        }
      }
      continue;
    }

    // 2. DEF メソッド定義: DEF|name(p1, p2, ...)|cmd1;cmd2;...
    if (type === 'DEF' || type === 'MACRO') {
      const decl = parts[1] || '';
      const match = decl.match(/^([a-zA-Z0-9_-]+)\s*\(([^)]*)\)$/);
      if (match) {
        const methodName = match[1];
        const params = match[2].split(',').map(s => s.trim()).filter(Boolean);
        const bodyStr = parts.slice(2).join('|');
        const bodyCommands = bodyStr.split(';').map(s => s.trim()).filter(Boolean);
        methods.set(methodName, { params, bodyCommands });
      }
      continue;
    }

    // 3. CALL メソッド呼び出し: CALL|name|arg1|arg2|...
    if (type === 'CALL') {
      const methodName = parts[1] || '';
      if (methods.has(methodName)) {
        const def = methods.get(methodName)!;
        const callArgs = parts.slice(2);
        const callVars: Record<string, string | number> = { ...variables };
        def.params.forEach((param, idx) => {
          callVars[param] = callArgs[idx] ?? '';
        });

        // 展開したコマンドを再帰的にプリプロセス
        const substituted = def.bodyCommands.map(bCmd => interpolateTemplate(bCmd, callVars));
        expanded.push(...preprocessDSL(substituted));
      }
      continue;
    }

    // 4. FOR ループ: FOR|i|0..4|cmd_template
    if (type === 'FOR') {
      const varName = parts[1] || 'i';
      const rangeStr = parts[2] || '0..0';
      const [startStr, endStr] = rangeStr.split('..');
      const start = Number(startStr) || 0;
      const end = Number(endStr) || 0;
      const template = parts.slice(3).join('|');
      const subCommands: string[] = [];

      for (let i = start; i <= end; i++) {
        const loopVars = { ...variables, [varName]: i };
        subCommands.push(interpolateTemplate(template, loopVars));
      }
      expanded.push(...preprocessDSL(subCommands));
      continue;
    }

    // 5. REPEAT ループ: REPEAT|count|cmd_template
    if (type === 'REPEAT') {
      const count = Math.max(Number(parts[1]) || 1, 0);
      const template = parts.slice(2).join('|');
      const subCommands: string[] = [];

      for (let i = 0; i < count; i++) {
        const loopVars = { ...variables, i, index: i };
        subCommands.push(interpolateTemplate(template, loopVars));
      }
      expanded.push(...preprocessDSL(subCommands));
      continue;
    }

    // 6. CONNECT 連鎖接続: CONNECT|a -> b -> c|color|label|styles
    if (type === 'CONNECT') {
      const chainStr = parts[1] || '';
      const nodes = chainStr.split('->').map(s => s.trim()).filter(Boolean);
      const color = parts[2] || 'dark';
      let label = parts[3] || '';
      let styles = parts[4] || '';

      if (label.includes(';') && !styles) {
        const [lbl, ...stlParts] = label.split(';');
        label = lbl.trim();
        styles = stlParts.join(';').trim();
      }

      for (let i = 0; i < nodes.length - 1; i++) {
        const from = nodes[i];
        const to = nodes[i + 1];
        const arrId = `conn_${from}_${to}_${Math.random().toString(36).substring(2, 6)}`;
        expanded.push(`ARROW|${arrId}|${from}|${to}|${color}|${label}|${styles}`);
      }
      continue;
    }

    // 7. ROW / COL オートレイアウト
    if (type === 'ROW' || type === 'COL') {
      const layoutOpts = parts[1] || '';
      let startX = 100, startY = 100, gap = 30;

      const optTokens = layoutOpts.split(/[;, ]+/).filter(Boolean);
      for (const tok of optTokens) {
        const [k, v] = tok.split('=').map(s => s.trim());
        if (k === 'x') startX = Number(v) || 100;
        else if (k === 'y') startY = Number(v) || 100;
        else if (k === 'gap') gap = Number(v) || 30;
      }

      const bodyStr = parts.slice(2).join('|');
      const subCmds = bodyStr.split(';').map(s => s.trim()).filter(Boolean);
      let curX = startX;
      let curY = startY;

      for (const subCmd of subCmds) {
        const subParts = subCmd.split('|').map(s => s.trim());
        const subType = subParts[0]?.toUpperCase();

        if (subType === 'RECT' || subType === 'ELLIPSE' || subType === 'DIAMOND' || subType === 'CARD' || subType === 'FRAME') {
          const w = Number(subParts[4] || 140);
          const h = Number(subParts[5] || 70);

          subParts[2] = String(curX);
          subParts[3] = String(curY);
          expanded.push(subParts.join('|'));

          if (type === 'ROW') {
            curX += w + gap;
          } else {
            curY += h + gap;
          }
        } else if (subType === 'CIRCLE') {
          const r = Number(subParts[4] || 50);
          subParts[2] = String(curX + r);
          subParts[3] = String(curY + r);
          expanded.push(subParts.join('|'));

          if (type === 'ROW') {
            curX += r * 2 + gap;
          } else {
            curY += r * 2 + gap;
          }
        } else {
          expanded.push(subCmd);
        }
      }
      continue;
    }

    expanded.push(cmd);
  }

  return expanded;
}

// Converts compact DSL string commands into Excalidraw element objects
// elementMap を呼び出し元と共有することで、1リクエスト内で draw_dsl が複数回
// 呼ばれても（段階的描画）ARROW の id 参照解決を呼び出しをまたいで維持できる
export function parseDSLToElements(rawCommands: string[], elementMap: Map<string, any> = new Map()): any[] {
  const commands = preprocessDSL(rawCommands);
  const elements: any[] = [];

  for (const cmd of commands) {
    const parts = cmd.split('|').map(p => p.trim());
    const type = parts[0].toUpperCase();

    if (type === 'DEL') {
      elements.push({ type: 'delete', ids: parts[1] || '' });
      continue;
    }

    if (type === 'CLEAR') {
      elements.push({ type: 'delete', ids: '*' });
      continue;
    }

    if (type === 'GROUP') {
      elements.push({ type: 'group', groupId: parts[1] || `grp_${Math.random().toString(36).substring(2, 7)}`, ids: parts[2] || '' });
      continue;
    }

    if (type === 'UNGROUP') {
      elements.push({ type: 'ungroup', ids: parts[1] || '' });
      continue;
    }

    if (type === 'LINK') {
      elements.push({ type: 'link', id: parts[1] || '', link: parts[2] || '' });
      continue;
    }

    if (type === 'FRONT' || type === 'BRING_TO_FRONT') {
      elements.push({ type: 'layer', ids: parts[1] || '', position: 'front' });
      continue;
    }

    if (type === 'BACK' || type === 'SEND_TO_BACK') {
      elements.push({ type: 'layer', ids: parts[1] || '', position: 'back' });
      continue;
    }

    if (type === 'HIDE') {
      elements.push({ type: 'hide', ids: parts[1] || '' });
      continue;
    }

    if (type === 'SHOW') {
      elements.push({ type: 'show', ids: parts[1] || '', opacity: Number(parts[2] || 100) });
      continue;
    }

    if (type === 'MOVE' || type === 'MOVE_BY') {
      const id = parts[1] || '';
      const isRelative = type === 'MOVE_BY';
      let x = 0, y = 0;
      if (parts[2] && parts[2].includes(',')) {
        const [px, py] = parts[2].split(',').map(Number);
        x = px || 0;
        y = py || 0;
      } else {
        x = Number(parts[2] || 0);
        y = Number(parts[3] || 0);
      }

      if (isRelative) {
        elements.push({ type: 'move', id, dx: x, dy: y, isRelative: true });
        if (elementMap.has(id)) {
          const el = elementMap.get(id);
          el.x = (el.x || 0) + x;
          el.y = (el.y || 0) + y;
        }
      } else {
        elements.push({ type: 'move', id, x, y, isRelative: false });
        if (elementMap.has(id)) {
          const el = elementMap.get(id);
          el.x = x;
          el.y = y;
        }
      }
      continue;
    }

    if (type === 'RESIZE') {
      const id = parts[1] || '';
      let w = 100, h = 100;
      if (parts[2] && parts[2].includes(',')) {
        const [pw, ph] = parts[2].split(',').map(Number);
        w = pw || 100;
        h = ph || 100;
      } else {
        w = Number(parts[2] || 100);
        h = Number(parts[3] || 100);
      }
      elements.push({ type: 'resize', id, width: w, height: h, isScale: false });
      if (elementMap.has(id)) {
        const el = elementMap.get(id);
        el.width = w;
        el.height = h;
      }
      continue;
    }

    if (type === 'SCALE') {
      const id = parts[1] || '';
      const factor = Number(parts[2] || 1);
      elements.push({ type: 'resize', id, scaleFactor: factor, isScale: true });
      if (elementMap.has(id)) {
        const el = elementMap.get(id);
        el.width = Math.round((el.width || 10) * factor);
        el.height = Math.round((el.height || 10) * factor);
      }
      continue;
    }

    if (type === 'ROTATE' || type === 'ROTATE_BY') {
      const id = parts[1] || '';
      const isRelative = type === 'ROTATE_BY';
      const numAngle = Number(parts[2] || 0);
      const angle = Math.abs(numAngle) > Math.PI * 2 ? (numAngle * Math.PI) / 180 : numAngle;
      elements.push({ type: 'rotate', id, angle, isRelative });
      if (elementMap.has(id)) {
        const el = elementMap.get(id);
        el.angle = isRelative ? ((el.angle || 0) + angle) : angle;
      }
      continue;
    }

    if (type === 'RECT' || type === 'ELLIPSE' || type === 'DIAMOND') {
      // Syntax: TYPE|id|x|y|width|height|color|label|angle|styles
      // またはカンマ座標: TYPE|id|x,y,w,h|color|label|angle|styles
      const id = parts[1] || `elem_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 140, height = 70;
      let colorKey = 'blue', labelText = '', rawAngle = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        if (coords.length >= 4) {
          // Syntax: TYPE|id|x,y,w,h|color|label|angle|styles
          width = Number(coords[2] || 140);
          height = Number(coords[3] || 70);
          colorKey = (parts[3] || 'blue').toLowerCase();
          labelText = parts[4] || '';
          rawAngle = parts[5] || '';
          rawStyles = parts[6] || '';
        } else if (parts.length >= 6 && !isNaN(Number(parts[3])) && !isNaN(Number(parts[4]))) {
          // Syntax: TYPE|id|x,y|width|height|color|label|angle|styles
          width = Number(parts[3] || 140);
          height = Number(parts[4] || 70);
          colorKey = (parts[5] || 'blue').toLowerCase();
          labelText = parts[6] || '';
          rawAngle = parts[7] || '';
          rawStyles = parts[8] || '';
        } else {
          colorKey = (parts[3] || 'blue').toLowerCase();
          labelText = parts[4] || '';
          rawAngle = parts[5] || '';
          rawStyles = parts[6] || '';
        }
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        width = Number(parts[4] || 140);
        height = Number(parts[5] || 70);
        colorKey = (parts[6] || 'blue').toLowerCase();
        labelText = parts[7] || '';
        rawAngle = parts[8] || '';
        rawStyles = parts[9] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.blue);
      const shapeType = type === 'RECT' ? 'rectangle' : type === 'ELLIPSE' ? 'ellipse' : 'diamond';
      const numAngle = Number(rawAngle || 0);
      const angle = Math.abs(numAngle) > Math.PI * 2 ? (numAngle * Math.PI) / 180 : numAngle;
      const styles = parseStyleProps(rawStyles);

      const elemObj: any = {
        type: shapeType,
        id,
        x,
        y,
        width,
        height,
        text: labelText || '',
        fontSize: 16,
        textAlign: styles.textAlign || 'center',
        verticalAlign: styles.verticalAlign || 'middle',
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1
      };

      if (styles.roundness !== undefined) {
        elemObj.roundness = styles.roundness;
      }
      if (styles.opacity !== undefined) {
        elemObj.opacity = styles.opacity;
      }
      if (angle !== 0) {
        elemObj.angle = angle;
      }

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'CIRCLE') {
      // Syntax: CIRCLE|id|cx|cy|radius|color|label|styles
      // または CIRCLE|id|cx,cy,radius|color|label|styles
      const id = parts[1] || `circle_${Math.random().toString(36).substring(2, 7)}`;
      let cx = 100, cy = 100, radius = 50;
      let colorKey = 'blue', labelText = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        cx = Number(coords[0] || 100);
        cy = Number(coords[1] || 100);
        radius = Number(coords[2] || 50);
        colorKey = (parts[3] || 'blue').toLowerCase();
        labelText = parts[4] || '';
        rawStyles = parts[5] || '';
      } else {
        cx = Number(parts[2] || 100);
        cy = Number(parts[3] || 100);
        radius = Number(parts[4] || 50);
        colorKey = (parts[5] || 'blue').toLowerCase();
        labelText = parts[6] || '';
        rawStyles = parts[7] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.blue);
      const styles = parseStyleProps(rawStyles);

      const elemObj: any = {
        type: 'ellipse',
        id,
        x: cx - radius,
        y: cy - radius,
        width: radius * 2,
        height: radius * 2,
        text: labelText || '',
        fontSize: 16,
        textAlign: styles.textAlign || 'center',
        verticalAlign: styles.verticalAlign || 'middle',
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1
      };

      if (styles.opacity !== undefined) elemObj.opacity = styles.opacity;

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'FRAME' || type === 'CONTAINER') {
      // Syntax: FRAME|id|x|y|w|h|color|label|styles
      const id = parts[1] || `frame_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 400, height = 300;
      let colorKey = 'gray', labelText = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        width = Number(coords[2] || 400);
        height = Number(coords[3] || 300);
        colorKey = (parts[3] || 'gray').toLowerCase();
        labelText = parts[4] || '';
        rawStyles = parts[5] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        width = Number(parts[4] || 400);
        height = Number(parts[5] || 300);
        colorKey = (parts[6] || 'gray').toLowerCase();
        labelText = parts[7] || '';
        rawStyles = parts[8] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.gray);
      const styles = parseStyleProps(rawStyles);

      const frameBox: any = {
        type: 'rectangle',
        id,
        x,
        y,
        width,
        height,
        text: '',
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'dashed',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 0,
        roundness: styles.roundness !== undefined ? styles.roundness : { type: 3 }
      };

      if (styles.opacity !== undefined) frameBox.opacity = styles.opacity;

      elementMap.set(id, frameBox);
      elements.push(frameBox);

      if (labelText) {
        const labelId = `${id}_label`;
        const labelElem: any = {
          type: 'text',
          id: labelId,
          x: x + 12,
          y: y + 10,
          width: Math.max(labelText.length * 10, 60),
          height: 22,
          text: labelText,
          fontSize: 16,
          fontFamily: styles.fontFamily || 2,
          strokeColor: colors.stroke,
          backgroundColor: 'transparent',
          fillStyle: 'solid',
          strokeStyle: 'solid',
          roughness: 0
        };
        elementMap.set(labelId, labelElem);
        elements.push(labelElem);
      }
    } else if (type === 'CARD') {
      // Syntax: CARD|id|x|y|w|h|color|title|body|styles
      const id = parts[1] || `card_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 180, height = 110;
      let colorKey = 'blue', titleText = '', bodyText = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        width = Number(coords[2] || 180);
        height = Number(coords[3] || 110);
        colorKey = (parts[3] || 'blue').toLowerCase();
        titleText = parts[4] || '';
        bodyText = parts[5] || '';
        rawStyles = parts[6] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        width = Number(parts[4] || 180);
        height = Number(parts[5] || 110);
        colorKey = (parts[6] || 'blue').toLowerCase();
        titleText = parts[7] || '';
        bodyText = parts[8] || '';
        rawStyles = parts[9] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.blue);
      const styles = parseStyleProps(rawStyles);

      // Card base rectangle
      const cardBase: any = {
        type: 'rectangle',
        id,
        x,
        y,
        width,
        height,
        text: '',
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1,
        roundness: styles.roundness !== undefined ? styles.roundness : { type: 3 }
      };
      if (styles.opacity !== undefined) cardBase.opacity = styles.opacity;
      elementMap.set(id, cardBase);
      elements.push(cardBase);

      // Title element
      if (titleText) {
        const titleId = `${id}_title`;
        const titleElem: any = {
          type: 'text',
          id: titleId,
          x: x + 12,
          y: y + 10,
          width: width - 24,
          height: 22,
          text: titleText,
          fontSize: 16,
          fontFamily: styles.fontFamily || 2,
          strokeColor: colors.stroke,
          backgroundColor: 'transparent',
          fillStyle: 'solid',
          strokeStyle: 'solid',
          roughness: 0
        };
        elementMap.set(titleId, titleElem);
        elements.push(titleElem);
      }

      // Body element
      if (bodyText) {
        const bodyId = `${id}_body`;
        const bodyElem: any = {
          type: 'text',
          id: bodyId,
          x: x + 12,
          y: y + (titleText ? 36 : 12),
          width: width - 24,
          height: Math.max(height - 48, 20),
          text: bodyText,
          fontSize: 14,
          fontFamily: styles.fontFamily || 2,
          strokeColor: '#333333',
          backgroundColor: 'transparent',
          fillStyle: 'solid',
          strokeStyle: 'solid',
          roughness: 0
        };
        elementMap.set(bodyId, bodyElem);
        elements.push(bodyElem);
      }
    } else if (type === 'STAR') {
      // Syntax: STAR|id|cx,cy,radius|color|label|styles
      // または STAR|id|cx|cy|outerR|innerR|color|label|styles
      // または STAR|id|x|y|w|h|color|label|styles
      const id = parts[1] || `star_${Math.random().toString(36).substring(2, 7)}`;
      let pointCoords: [number, number][] = [];
      let colorKey = 'yellow', labelText = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        const cx = Number(coords[0] || 100);
        const cy = Number(coords[1] || 100);
        const outerR = Number(coords[2] || 50);
        const innerR = coords.length >= 4 ? Number(coords[3]) : outerR * 0.45;
        const ptsCount = coords.length >= 5 ? Number(coords[4]) : 5;
        pointCoords = generateStarPoints(cx, cy, outerR, innerR, ptsCount);
        colorKey = (parts[3] || 'yellow').toLowerCase();
        labelText = parts[4] || '';
        rawStyles = parts[5] || '';
      } else if (parts.length >= 7 && !isNaN(Number(parts[2])) && !isNaN(Number(parts[3])) && !isNaN(Number(parts[4])) && !isNaN(Number(parts[5]))) {
        // STAR|id|x|y|w|h|color|label|styles
        const x = Number(parts[2] || 100);
        const y = Number(parts[3] || 100);
        const w = Number(parts[4] || 80);
        const h = Number(parts[5] || 80);
        const cx = x + w / 2;
        const cy = y + h / 2;
        const outerR = Math.min(w, h) / 2;
        pointCoords = generateStarPoints(cx, cy, outerR, outerR * 0.45, 5);
        colorKey = (parts[6] || 'yellow').toLowerCase();
        labelText = parts[7] || '';
        rawStyles = parts[8] || '';
      } else {
        const cx = Number(parts[2] || 100);
        const cy = Number(parts[3] || 100);
        const outerR = Number(parts[4] || 50);
        pointCoords = generateStarPoints(cx, cy, outerR, outerR * 0.45, 5);
        colorKey = (parts[5] || 'yellow').toLowerCase();
        labelText = parts[6] || '';
        rawStyles = parts[7] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.yellow);
      const styles = parseStyleProps(rawStyles);
      const { minX, minY, width, height, points } = pointsToRelativePolygon(pointCoords);

      const elemObj: any = {
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
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1,
        startArrowhead: null,
        endArrowhead: null,
        points
      };

      if (styles.opacity !== undefined) elemObj.opacity = styles.opacity;

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'CLOUD') {
      // Syntax: CLOUD|id|x|y|w|h|color|label|styles
      // またはカンマ座標 CLOUD|id|x,y,w,h|color|label|styles
      const id = parts[1] || `cloud_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 160, height = 100;
      let colorKey = 'teal', labelText = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        width = Number(coords[2] || 160);
        height = Number(coords[3] || 100);
        colorKey = (parts[3] || 'teal').toLowerCase();
        labelText = parts[4] || '';
        rawStyles = parts[5] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        width = Number(parts[4] || 160);
        height = Number(parts[5] || 100);
        colorKey = (parts[6] || 'teal').toLowerCase();
        labelText = parts[7] || '';
        rawStyles = parts[8] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.teal);
      const styles = parseStyleProps(rawStyles);
      const cloudCoords = generateCloudPoints(x, y, width, height);
      const { minX, minY, width: polyW, height: polyH, points } = pointsToRelativePolygon(cloudCoords);

      const elemObj: any = {
        type: 'line',
        id,
        x: minX,
        y: minY,
        width: polyW,
        height: polyH,
        text: labelText || '',
        fontSize: 16,
        strokeColor: colors.stroke,
        backgroundColor: colors.fill,
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1,
        startArrowhead: null,
        endArrowhead: null,
        points
      };

      if (styles.opacity !== undefined) elemObj.opacity = styles.opacity;

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'TRIANGLE' || type === 'POLYGON') {
      // Syntax: TRIANGLE|id|x1,y1|x2,y2|x3,y3|color|label|styles
      // Syntax: POLYGON|id|x1,y1|x2,y2|...|xn,yn|color|label|styles
      const id = parts[1] || `${type.toLowerCase()}_${Math.random().toString(36).substring(2, 7)}`;
      let colorKey = 'blue';
      let labelText = '';
      let rawStyles = '';
      const pointCoords: [number, number][] = [];

      if (type === 'TRIANGLE') {
        const p1 = (parts[2] || '0,0').split(',').map(Number);
        const p2 = (parts[3] || '100,0').split(',').map(Number);
        const p3 = (parts[4] || '50,100').split(',').map(Number);
        pointCoords.push([p1[0] || 0, p1[1] || 0], [p2[0] || 0, p2[1] || 0], [p3[0] || 0, p3[1] || 0]);
        colorKey = (parts[5] || 'blue').toLowerCase();
        labelText = parts[6] || '';
        rawStyles = parts[7] || '';
      } else {
        let i = 2;
        while (i < parts.length && parts[i].includes(',')) {
          const pt = parts[i].split(',').map(Number);
          pointCoords.push([pt[0] || 0, pt[1] || 0]);
          i++;
        }
        if (pointCoords.length < 3) {
          pointCoords.push([0, 0], [100, 0], [100, 100], [0, 100]);
        }
        colorKey = (parts[i] || 'blue').toLowerCase();
        labelText = parts[i + 1] || '';
        rawStyles = parts[i + 2] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.blue);
      const styles = parseStyleProps(rawStyles);
      const { minX, minY, width, height, points } = pointsToRelativePolygon(pointCoords);

      const elemObj: any = {
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
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1,
        startArrowhead: null,
        endArrowhead: null,
        points
      };

      if (styles.opacity !== undefined) elemObj.opacity = styles.opacity;

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'POLYLINE') {
      // Syntax: POLYLINE|id|x1,y1|x2,y2|...|xn,yn|color|label|styles
      // Open multi-point line
      const id = parts[1] || `polyline_${Math.random().toString(36).substring(2, 7)}`;
      const pointCoords: [number, number][] = [];
      let i = 2;
      while (i < parts.length && parts[i].includes(',')) {
        const pt = parts[i].split(',').map(Number);
        pointCoords.push([pt[0] || 0, pt[1] || 0]);
        i++;
      }
      if (pointCoords.length < 2) {
        pointCoords.push([0, 0], [100, 100]);
      }
      const colorKey = (parts[i] || 'dark').toLowerCase();
      const labelText = parts[i + 1] || '';
      const rawStyles = parts[i + 2] || '';

      const colors = resolveColor(colorKey, COLOR_PALETTE.dark);
      const styles = parseStyleProps(rawStyles);

      const xs = pointCoords.map(p => p[0]);
      const ys = pointCoords.map(p => p[1]);
      const minX = Math.min(...xs);
      const minY = Math.min(...ys);
      const maxX = Math.max(...xs);
      const maxY = Math.max(...ys);
      const width = Math.max(maxX - minX, 1);
      const height = Math.max(maxY - minY, 1);
      const relativePoints = pointCoords.map(p => [p[0] - minX, p[1] - minY]);

      const elemObj: any = {
        type: 'line',
        id,
        x: minX,
        y: minY,
        width,
        height,
        text: labelText || '',
        fontSize: 14,
        strokeColor: colors.stroke,
        backgroundColor: 'transparent',
        fillStyle: 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1,
        startArrowhead: styles.startArrowhead !== undefined ? styles.startArrowhead : null,
        endArrowhead: styles.endArrowhead !== undefined ? styles.endArrowhead : null,
        points: relativePoints
      };

      if (styles.opacity !== undefined) elemObj.opacity = styles.opacity;

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'TEXT') {
      // Syntax: TEXT|id|x|y|fontSize|color|text|styles
      // またはカンマ座標: TEXT|id|x,y|fontSize|color|text|styles
      const id = parts[1] || `txt_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, fontSize = 18, colorKey = 'dark', text = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        fontSize = Number(parts[3] || 18);
        colorKey = (parts[4] || 'dark').toLowerCase();
        text = parts[5] || '';
        rawStyles = parts[6] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        fontSize = Number(parts[4] || 18);
        colorKey = (parts[5] || 'dark').toLowerCase();
        text = parts[6] || '';
        rawStyles = parts[7] || '';
      }

      const colors = resolveColor(colorKey, COLOR_PALETTE.dark);
      const styles = parseStyleProps(rawStyles);

      const elemObj: any = {
        type: 'text',
        id,
        x,
        y,
        width: Math.max(text.length * (fontSize * 0.55), 50),
        height: fontSize * 1.5,
        text,
        fontSize,
        textAlign: styles.textAlign || 'left',
        verticalAlign: styles.verticalAlign || 'top',
        strokeColor: colors.stroke,
        backgroundColor: colors.fill === COLOR_PALETTE.dark.fill ? 'transparent' : colors.fill,
        fillStyle: styles.fillStyle || 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        roughness: styles.roughness !== undefined ? styles.roughness : 1
      };

      if (styles.fontFamily !== undefined) {
        elemObj.fontFamily = styles.fontFamily;
      }
      if (styles.opacity !== undefined) {
        elemObj.opacity = styles.opacity;
      }

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'ARROW' || type === 'LINE' || type === 'BIARROW' || type === 'ARROW2' || type === 'ELBOW') {
      // Syntax: TYPE|id|fromRef|toRef|color|label|styles
      const defaultPrefix = type === 'LINE' ? 'line' : (type === 'ARROW' ? 'arr' : type.toLowerCase());
      const id = parts[1] || `${defaultPrefix}_${Math.random().toString(36).substring(2, 7)}`;
      const fromRef = parts[2] || '0,0';
      const toRef = parts[3] || '100,0';
      const colorKey = (parts[4] || 'dark').toLowerCase();
      const labelText = parts[5] || '';
      const rawStyles = parts[6] || '';

      const colors = resolveColor(colorKey, COLOR_PALETTE.dark);
      const styles = parseStyleProps(rawStyles);

      const [startX, startY] = resolveAnchor(fromRef, elementMap, 0, 0, false);
      const [endX, endY] = resolveAnchor(toRef, elementMap, 100, 0, true);

      const dx = endX - startX;
      const dy = endY - startY;

      let startArrow: string | null = null;
      let endArrow: string | null = null;

      if (type === 'LINE') {
        startArrow = styles.startArrowhead !== undefined ? styles.startArrowhead : null;
        endArrow = styles.endArrowhead !== undefined ? styles.endArrowhead : null;
      } else if (type === 'BIARROW' || type === 'ARROW2') {
        startArrow = styles.startArrowhead !== undefined ? styles.startArrowhead : 'arrow';
        endArrow = styles.endArrowhead !== undefined ? styles.endArrowhead : 'arrow';
      } else {
        // ARROW or ELBOW
        startArrow = styles.startArrowhead !== undefined ? styles.startArrowhead : null;
        endArrow = styles.endArrowhead !== undefined ? styles.endArrowhead : 'arrow';
      }

      let points: [number, number][];

      if (type === 'ELBOW') {
        // Orthogonal routing: midpoint corner
        if (Math.abs(dx) >= Math.abs(dy)) {
          // Horizontal first then vertical
          const midX = dx / 2;
          points = [[0, 0], [midX, 0], [midX, dy], [dx, dy]];
        } else {
          // Vertical first then horizontal
          const midY = dy / 2;
          points = [[0, 0], [0, midY], [dx, midY], [dx, dy]];
        }
      } else {
        points = [[0, 0], [dx, dy]];
      }

      const elemObj: any = {
        type: (type === 'LINE') ? 'line' : 'arrow',
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
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 1,
        startArrowhead: startArrow,
        endArrowhead: endArrow,
        points
      };

      if (styles.opacity !== undefined) elemObj.opacity = styles.opacity;

      elementMap.set(id, elemObj);
      elements.push(elemObj);
    } else if (type === 'GRID' || type === 'BOARD') {
      // Syntax: GRID|id|x|y|w|h|rows,cols|color1|color2|styles
      // または カンマ座標: GRID|id|x,y,w,h|rows,cols|color1|color2|styles
      const id = parts[1] || `grid_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 400, height = 400;
      let rowsCols = '8,8', color1Key = '#ffffff', color2Key = '', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        width = Number(coords[2] || 400);
        height = Number(coords[3] || 400);
        rowsCols = parts[3] || '8,8';
        color1Key = parts[4] || '#ffffff';
        color2Key = parts[5] || '';
        rawStyles = parts[6] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        width = Number(parts[4] || 400);
        height = Number(parts[5] || 400);
        rowsCols = parts[6] || '8,8';
        color1Key = parts[7] || '#ffffff';
        color2Key = parts[8] || '';
        rawStyles = parts[9] || '';
      }

      const styles = parseStyleProps(rawStyles);
      const [rStr, cStr] = rowsCols.includes(',') ? rowsCols.split(',') : [rowsCols, rowsCols];
      const rows = Math.max(Number(rStr) || 8, 1);
      const cols = Math.max(Number(cStr) || 8, 1);
      const cellW = width / cols;
      const cellH = height / rows;

      const c1 = resolveColor(color1Key, { fill: color1Key || '#ffffff', stroke: '#1e1e1e' });
      const hasColor2 = Boolean(color2Key && color2Key.toLowerCase() !== 'none');
      const c2 = hasColor2 ? resolveColor(color2Key, { fill: color2Key, stroke: '#1e1e1e' }) : null;

      // Outer border container
      const borderBox: any = {
        type: 'rectangle',
        id: `${id}_board`,
        x,
        y,
        width,
        height,
        strokeColor: c1.stroke,
        backgroundColor: c1.fill,
        fillStyle: 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 0
      };
      elementMap.set(`${id}_board`, borderBox);
      elements.push(borderBox);

      // Generate individual cells
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const isAlternate = (r + c) % 2 === 1;
          const cellColor = (isAlternate && c2) ? c2 : c1;
          const cellX = x + c * cellW;
          const cellY = y + r * cellH;
          const cellId = `${id}_c${c}_r${r}`;

          const cellElem: any = {
            type: 'rectangle',
            id: cellId,
            x: cellX,
            y: cellY,
            width: cellW,
            height: cellH,
            strokeColor: cellColor.stroke,
            backgroundColor: cellColor.fill,
            fillStyle: 'solid',
            strokeStyle: styles.strokeStyle || 'solid',
            strokeWidth: 1,
            roughness: 0
          };

          elementMap.set(cellId, cellElem);
          // Also alias for chess if 8x8
          if (rows === 8 && cols === 8) {
            const fileChar = String.fromCharCode(97 + c); // a - h
            const rankNum = 8 - r; // 8 down to 1
            elementMap.set(`${id}_${fileChar}${rankNum}`, cellElem);
          }

          elements.push(cellElem);
        }
      }
    } else if (type === 'CHESSBOARD') {
      // Syntax: CHESSBOARD|id|x|y|size|lightColor|darkColor|pieces|styles
      // または CHESSBOARD|id|x,y,size|lightColor|darkColor|pieces|styles
      const id = parts[1] || `chess_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, size = 400;
      let lightColor = '#f0d9b5', darkColor = '#b58863', piecesArg = 'init', rawStyles = '';

      if (parts[2] && parts[2].includes(',')) {
        const coords = parts[2].split(',').map(Number);
        x = Number(coords[0] || 100);
        y = Number(coords[1] || 100);
        size = Number(coords[2] || 400);
        lightColor = parts[3] || '#f0d9b5';
        darkColor = parts[4] || '#b58863';
        piecesArg = parts[5] || 'init';
        rawStyles = parts[6] || '';
      } else {
        x = Number(parts[2] || 100);
        y = Number(parts[3] || 100);
        size = Number(parts[4] || 400);
        lightColor = parts[5] || '#f0d9b5';
        darkColor = parts[6] || '#b58863';
        piecesArg = parts[7] || 'init';
        rawStyles = parts[8] || '';
      }

      const styles = parseStyleProps(rawStyles);
      const cellW = size / 8;
      const cellH = size / 8;

      const cLight = resolveColor(lightColor, { fill: '#f0d9b5', stroke: '#8B5A2B' });
      const cDark = resolveColor(darkColor, { fill: '#b58863', stroke: '#8B5A2B' });

      // Outer wooden border
      const borderPadding = 24;
      const outerBox: any = {
        type: 'rectangle',
        id: `${id}_border`,
        x: x - borderPadding,
        y: y - borderPadding,
        width: size + borderPadding * 2,
        height: size + borderPadding * 2,
        strokeColor: '#5c3a21',
        backgroundColor: '#8B5A2B',
        fillStyle: 'solid',
        strokeStyle: styles.strokeStyle || 'solid',
        strokeWidth: styles.strokeWidth || 2,
        roughness: styles.roughness !== undefined ? styles.roughness : 0,
        roundness: styles.roundness !== undefined ? styles.roundness : { type: 3 }
      };
      if (styles.opacity !== undefined) outerBox.opacity = styles.opacity;
      elementMap.set(`${id}_border`, outerBox);
      elements.push(outerBox);

      // Coordinate labels (a-h and 1-8)
      const files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
      for (let i = 0; i < 8; i++) {
        // Files top/bottom
        const fileLabel: any = {
          type: 'text',
          id: `${id}_label_file_${files[i]}`,
          x: x + i * cellW + cellW / 2 - 5,
          y: y + size + 4,
          width: 16,
          height: 16,
          text: files[i],
          fontSize: 14,
          fontFamily: 2,
          strokeColor: '#ffffff',
          backgroundColor: 'transparent',
          fillStyle: 'solid',
          strokeStyle: 'solid',
          roughness: 0
        };
        elementMap.set(fileLabel.id, fileLabel);
        elements.push(fileLabel);

        // Ranks left/right
        const rankLabel: any = {
          type: 'text',
          id: `${id}_label_rank_${8 - i}`,
          x: x - 18,
          y: y + i * cellH + cellH / 2 - 8,
          width: 16,
          height: 16,
          text: String(8 - i),
          fontSize: 14,
          fontFamily: 2,
          strokeColor: '#ffffff',
          backgroundColor: 'transparent',
          fillStyle: 'solid',
          strokeStyle: 'solid',
          roughness: 0
        };
        elementMap.set(rankLabel.id, rankLabel);
        elements.push(rankLabel);
      }

      // Generate 64 cells
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
          const isDark = (r + c) % 2 === 1;
          const cellColor = isDark ? cDark : cLight;
          const cellX = x + c * cellW;
          const cellY = y + r * cellH;
          const fileChar = files[c];
          const rankNum = 8 - r;
          const cellId = `${id}_${fileChar}${rankNum}`;

          const cellElem: any = {
            type: 'rectangle',
            id: cellId,
            x: cellX,
            y: cellY,
            width: cellW,
            height: cellH,
            strokeColor: cellColor.fill,
            backgroundColor: cellColor.fill,
            fillStyle: 'solid',
            strokeStyle: 'solid',
            strokeWidth: 1,
            roughness: 0
          };

          elementMap.set(cellId, cellElem);
          elements.push(cellElem);
        }
      }

      // Place pieces if requested
      const shouldPlacePieces = piecesArg !== 'none' && piecesArg !== 'false' && piecesArg !== 'empty';
      if (shouldPlacePieces) {
        // Standard initial chess setup
        const blackMajor = ['♜', '♞', '♝', '♛', '♚', '♝', '♞', '♜'];
        const whiteMajor = ['♖', '♘', '♗', '♕', '♔', '♗', '♘', '♖'];
        const pieceFontSize = Math.round(cellW * 0.65);

        // Black back rank (rank 8, r = 0)
        for (let c = 0; c < 8; c++) {
          const pId = `${id}_piece_${files[c]}8`;
          const pieceElem: any = {
            type: 'text',
            id: pId,
            x: x + c * cellW + (cellW - pieceFontSize) / 2 - 2,
            y: y + (cellH - pieceFontSize) / 2 - 4,
            width: pieceFontSize,
            height: pieceFontSize,
            text: blackMajor[c],
            fontSize: pieceFontSize,
            textAlign: 'center',
            verticalAlign: 'middle',
            strokeColor: '#1e1e1e',
            backgroundColor: 'transparent',
            fillStyle: 'solid',
            strokeStyle: 'solid',
            roughness: 0
          };
          elementMap.set(pId, pieceElem);
          elements.push(pieceElem);
        }

        // Black pawns (rank 7, r = 1)
        for (let c = 0; c < 8; c++) {
          const pId = `${id}_piece_${files[c]}7`;
          const pieceElem: any = {
            type: 'text',
            id: pId,
            x: x + c * cellW + (cellW - pieceFontSize) / 2 - 2,
            y: y + 1 * cellH + (cellH - pieceFontSize) / 2 - 4,
            width: pieceFontSize,
            height: pieceFontSize,
            text: '♟',
            fontSize: pieceFontSize,
            textAlign: 'center',
            verticalAlign: 'middle',
            strokeColor: '#1e1e1e',
            backgroundColor: 'transparent',
            fillStyle: 'solid',
            strokeStyle: 'solid',
            roughness: 0
          };
          elementMap.set(pId, pieceElem);
          elements.push(pieceElem);
        }

        // White pawns (rank 2, r = 6)
        for (let c = 0; c < 8; c++) {
          const pId = `${id}_piece_${files[c]}2`;
          const pieceElem: any = {
            type: 'text',
            id: pId,
            x: x + c * cellW + (cellW - pieceFontSize) / 2 - 2,
            y: y + 6 * cellH + (cellH - pieceFontSize) / 2 - 4,
            width: pieceFontSize,
            height: pieceFontSize,
            text: '♙',
            fontSize: pieceFontSize,
            textAlign: 'center',
            verticalAlign: 'middle',
            strokeColor: '#1e1e1e',
            backgroundColor: 'transparent',
            fillStyle: 'solid',
            strokeStyle: 'solid',
            roughness: 0
          };
          elementMap.set(pId, pieceElem);
          elements.push(pieceElem);
        }

        // White major pieces (rank 1, r = 7)
        for (let c = 0; c < 8; c++) {
          const pId = `${id}_piece_${files[c]}1`;
          const pieceElem: any = {
            type: 'text',
            id: pId,
            x: x + c * cellW + (cellW - pieceFontSize) / 2 - 2,
            y: y + 7 * cellH + (cellH - pieceFontSize) / 2 - 4,
            width: pieceFontSize,
            height: pieceFontSize,
            text: whiteMajor[c],
            fontSize: pieceFontSize,
            textAlign: 'center',
            verticalAlign: 'middle',
            strokeColor: '#1e1e1e',
            backgroundColor: 'transparent',
            fillStyle: 'solid',
            strokeStyle: 'solid',
            roughness: 0
          };
          elementMap.set(pId, pieceElem);
          elements.push(pieceElem);
        }
      }
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
