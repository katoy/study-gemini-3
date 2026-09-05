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
  type: 'rectangle' | 'oval' | 'triangle' | 'polygon' | 'diamond' | 'line' | 'arrow' | 'text' | 'artboard' | 'group';
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
  // Sketch 機能拡張プロパティ
  cornerRadius?: number;
  dash?: number[];
  shadow?: string;
  childIds?: string[];
  presetName?: string;
  animation?: string;
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
  black: { fill: '#1e1e1e', stroke: '#000000' },
  white: { fill: '#ffffff', stroke: '#94a3b8' },
  sketch: { fill: '#fff7ed', stroke: '#f97316' }, // Sketch signature orange
  default: { fill: 'transparent', stroke: '#0f172a' }
};

// カラーキー（HEXや名前、カンマ区切りfill,stroke）を解決する関数
export function resolveColor(colorStr: string | undefined, defaultKey = 'blue'): { fill: string; stroke: string } {
  if (!colorStr) {
    return COLOR_PALETTE[defaultKey] || COLOR_PALETTE.blue;
  }
  const clean = colorStr.trim();
  const lower = clean.toLowerCase();

  // 1. パレット定義名の場合
  if (COLOR_PALETTE[lower]) {
    return COLOR_PALETTE[lower];
  }

  // 2. CSS rgb/hsl または HEXカラー表記の場合 (カンマより優先)
  if (clean.startsWith('rgb') || clean.startsWith('hsl')) {
    return { fill: clean, stroke: clean };
  }

  // 3. カンマ区切りの場合 (例: "#ffffff,#000000" や "white,black")
  if (clean.includes(',')) {
    const [f, s] = clean.split(',').map(s => s.trim());
    const fillRes = resolveColor(f, defaultKey).fill;
    const strokeRes = resolveColor(s, defaultKey).stroke;
    return { fill: fillRes, stroke: strokeRes };
  }

  // 4. HEXカラー表記の場合
  if (clean.startsWith('#')) {
    // 半透明HEXの場合 (#00000044, #22222233 など) -> 影用途等
    if (clean.startsWith('#') && (clean.length === 5 || clean.length === 9)) {
      return { fill: clean, stroke: 'transparent' };
    }
    // 白系
    if (lower === '#fff' || lower === '#ffffff') {
      return { fill: clean, stroke: '#94a3b8' };
    }
    // 黒系
    if (lower === '#000' || lower === '#000000' || lower === '#1e1e1e' || lower === '#111111') {
      return { fill: clean, stroke: '#000000' };
    }
    return { fill: clean, stroke: clean };
  }

  return COLOR_PALETTE[defaultKey] || COLOR_PALETTE.blue;
}

// ----------------------------------------------------------------------------
// 安全な簡易数式パーサー & 変数置換
// ----------------------------------------------------------------------------

export function evaluateExpression(exprStr: string, scope: Record<string, number | string>): number {
  let expr = exprStr.trim();
  // 変数を置換 ($var または var)
  for (const [key, val] of Object.entries(scope)) {
    const safeKey = key.startsWith('$') ? '\\' + key : key;
    // ワード境界または前後が演算子・空白・記号
    const regex = new RegExp(`(?<=[^a-zA-Z0-9_]|^)${safeKey}(?=[^a-zA-Z0-9_]|$)`, 'g');
    expr = expr.replace(regex, String(val));
  }

  // 単純数値の場合
  const num = Number(expr);
  if (!isNaN(num)) return num;

  // 安全な四則演算の再帰下降パーサー
  // サポート: +, -, *, /, %, 括弧, 単項マイナス
  let index = 0;
  function skipWhitespace() {
    while (index < expr.length && /\s/.test(expr[index])) index++;
  }

  function parsePrimary(): number {
    skipWhitespace();
    if (index >= expr.length) return 0;

    if (expr[index] === '(') {
      index++; // skip '('
      const val = parseAddSub();
      skipWhitespace();
      if (expr[index] === ')') index++; // skip ')'
      return val;
    }

    if (expr[index] === '-') {
      index++;
      return -parsePrimary();
    }
    if (expr[index] === '+') {
      index++;
      return parsePrimary();
    }

    const start = index;
    while (index < expr.length && /[0-9.]/.test(expr[index])) {
      index++;
    }
    if (start === index) {
      // 数値としてパースできない場合、残りのトークンをスキップ
      index++;
      return 0;
    }
    const val = parseFloat(expr.substring(start, index));
    return isNaN(val) ? 0 : val;
  }

  function parseMulDiv(): number {
    let left = parsePrimary();
    skipWhitespace();
    while (index < expr.length && (expr[index] === '*' || expr[index] === '/' || expr[index] === '%')) {
      const op = expr[index++];
      const right = parsePrimary();
      if (op === '*') left *= right;
      else if (op === '/') left = right !== 0 ? left / right : 0;
      else if (op === '%') left = right !== 0 ? left % right : 0;
      skipWhitespace();
    }
    return left;
  }

  function parseAddSub(): number {
    let left = parseMulDiv();
    skipWhitespace();
    while (index < expr.length && (expr[index] === '+' || expr[index] === '-')) {
      const op = expr[index++];
      const right = parseMulDiv();
      if (op === '+') left += right;
      else if (op === '-') left -= right;
      skipWhitespace();
    }
    return left;
  }

  try {
    return parseAddSub();
  } catch {
    return 0;
  }
}

// ----------------------------------------------------------------------------
// マクロ・ループ展開器 (expandDSLMacros)
// サポート: LET, DEF/END, CALL, REPEAT/END, GRID/END
// ----------------------------------------------------------------------------

interface MacroDef {
  params: string[];
  bodyLines: string[];
}

export function expandDSLMacros(rawCommands: string[]): string[] {
  // 入力を1行ごとの文字列配列に正規化（改行が含まれる場合に対応）
  const lines: string[] = [];
  for (const cmd of rawCommands) {
    if (typeof cmd !== 'string') continue;
    const splitLines = cmd.split('\n');
    for (const line of splitLines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('//')) continue;
      lines.push(trimmed);
    }
  }

  const globalScope: Record<string, number | string> = {};
  const macros = new Map<string, MacroDef>();

  function processLines(inputLines: string[], currentScope: Record<string, number | string>, depth = 0): string[] {
    if (depth > 20) return []; // 再帰上限ガード
    const output: string[] = [];

    let i = 0;
    while (i < inputLines.length) {
      const line = inputLines[i].trim();
      if (!line || line.startsWith('#') || line.startsWith('//')) {
        i++;
        continue;
      }

      // 1. 変数定義: LET <varName> = <expr>
      const letMatch = line.match(/^LET\s+([$a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$/i);
      if (letMatch) {
        const varName = letMatch[1];
        const rawExpr = letMatch[2].trim();
        // 文字列リテラル判定
        if ((rawExpr.startsWith('"') && rawExpr.endsWith('"')) || (rawExpr.startsWith("'") && rawExpr.endsWith("'"))) {
          currentScope[varName] = rawExpr.substring(1, rawExpr.length - 1);
        } else {
          currentScope[varName] = evaluateExpression(rawExpr, currentScope);
        }
        i++;
        continue;
      }

      // 2. 関数/マクロ定義: DEF <name>(param1, param2, ...) ... END
      const defMatch = line.match(/^DEF\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)/i);
      if (defMatch) {
        const macroName = defMatch[1];
        const params = defMatch[2].split(',').map(p => p.trim().replace(/^\$/, '')).filter(Boolean);
        const bodyLines: string[] = [];
        i++;
        let endFound = false;
        while (i < inputLines.length) {
          const innerLine = inputLines[i].trim();
          if (/^END\b/i.test(innerLine)) {
            endFound = true;
            i++;
            break;
          }
          bodyLines.push(inputLines[i]);
          i++;
        }
        if (endFound) {
          macros.set(macroName, { params, bodyLines });
        }
        continue;
      }

      // 3. マクロ呼び出し: CALL <name>(arg1, arg2, ...)
      const callMatch = line.match(/^CALL\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)$/i);
      if (callMatch) {
        const macroName = callMatch[1];
        const rawArgs = callMatch[2].split(',').map(a => a.trim());
        const macro = macros.get(macroName);
        if (macro) {
          const callScope = { ...currentScope };
          macro.params.forEach((param, idx) => {
            const rawVal = rawArgs[idx] ?? '';
            let cleanVal = rawVal;
            if ((cleanVal.startsWith('"') && cleanVal.endsWith('"')) || (cleanVal.startsWith("'") && cleanVal.endsWith("'"))) {
              cleanVal = cleanVal.substring(1, cleanVal.length - 1);
            } else if (currentScope[cleanVal] !== undefined) {
              cleanVal = String(currentScope[cleanVal]);
            } else if (currentScope['$' + cleanVal] !== undefined) {
              cleanVal = String(currentScope['$' + cleanVal]);
            }
            callScope[param] = cleanVal;
            callScope['$' + param] = cleanVal;
          });
          const expanded = processLines(macro.bodyLines, callScope, depth + 1);
          output.push(...expanded);
        }
        i++;
        continue;
      }

      // 4. 反復ループ: REPEAT <count> [AS <var>] [STEP dx=<expr>, dy=<expr>] ... END
      const repeatMatch = line.match(/^REPEAT\s+([^\s]+)(?:\s+AS\s+([$a-zA-Z_][a-zA-Z0-9_]*))?(?:\s+STEP\s+(.+))?/i);
      if (repeatMatch) {
        const countExpr = repeatMatch[1];
        const varName = (repeatMatch[2] || '$i').replace(/^\$/, '');
        const count = Math.round(evaluateExpression(countExpr, currentScope));
        const bodyLines: string[] = [];
        i++;
        let depthCounter = 1;
        while (i < inputLines.length) {
          const innerLine = inputLines[i].trim();
          if (/^REPEAT\b|^GRID\b/i.test(innerLine)) depthCounter++;
          else if (/^END\b/i.test(innerLine)) {
            depthCounter--;
            if (depthCounter === 0) {
              i++;
              break;
            }
          }
          bodyLines.push(inputLines[i]);
          i++;
        }

        const safeCount = Math.min(Math.max(count, 0), 200); // 無限ループガード
        for (let iter = 0; iter < safeCount; iter++) {
          const loopScope = { ...currentScope };
          loopScope[varName] = iter;
          loopScope['$' + varName] = iter;
          const expanded = processLines(bodyLines, loopScope, depth + 1);
          output.push(...expanded);
        }
        continue;
      }

      // 5. 2次元グリッド: GRID <rows>, <cols> [AS <rowVar>, <colVar>] [AT <startX>, <startY>] [SIZE <stepX>, <stepY>] ... END
      const gridMatch = line.match(/^GRID\s+([0-9$a-zA-Z_+*-]+)\s*,\s*([0-9$a-zA-Z_+*-]+)(?:\s+AS\s+([$a-zA-Z_][a-zA-Z0-9_]*)\s*,\s*([$a-zA-Z_][a-zA-Z0-9_]*))?(?:\s+AT\s+([0-9$a-zA-Z_+*-]+)\s*,\s*([0-9$a-zA-Z_+*-]+))?(?:\s+SIZE\s+([0-9$a-zA-Z_+*-]+)\s*,\s*([0-9$a-zA-Z_+*-]+))?/i);
      if (gridMatch) {
        const rows = Math.min(Math.max(Math.round(evaluateExpression(gridMatch[1], currentScope)), 1), 50);
        const cols = Math.min(Math.max(Math.round(evaluateExpression(gridMatch[2], currentScope)), 1), 50);
        const rowVar = (gridMatch[3] || '$r').replace(/^\$/, '');
        const colVar = (gridMatch[4] || '$c').replace(/^\$/, '');
        const startX = gridMatch[5] ? evaluateExpression(gridMatch[5], currentScope) : 0;
        const startY = gridMatch[6] ? evaluateExpression(gridMatch[6], currentScope) : 0;
        const stepX = gridMatch[7] ? evaluateExpression(gridMatch[7], currentScope) : 50;
        const stepY = gridMatch[8] ? evaluateExpression(gridMatch[8], currentScope) : 50;

        const bodyLines: string[] = [];
        i++;
        let depthCounter = 1;
        while (i < inputLines.length) {
          const innerLine = inputLines[i].trim();
          if (/^REPEAT\b|^GRID\b/i.test(innerLine)) depthCounter++;
          else if (/^END\b/i.test(innerLine)) {
            depthCounter--;
            if (depthCounter === 0) {
              i++;
              break;
            }
          }
          bodyLines.push(inputLines[i]);
          i++;
        }

        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const gridScope = { ...currentScope };
            gridScope[rowVar] = r;
            gridScope['$' + rowVar] = r;
            gridScope[colVar] = c;
            gridScope['$' + colVar] = c;
            gridScope['x'] = startX + c * stepX;
            gridScope['$x'] = startX + c * stepX;
            gridScope['y'] = startY + r * stepY;
            gridScope['$y'] = startY + r * stepY;

            const expanded = processLines(bodyLines, gridScope, depth + 1);
            output.push(...expanded);
          }
        }
        continue;
      }

      // 通常行の場合: スコープ内の変数を置換 ($var, ${var}, $(var))
      let resolvedLine = line;
      const sortedKeys = Object.keys(currentScope)
        .map(k => k.replace(/^\$/, ''))
        .sort((a, b) => b.length - a.length);
      const uniqueKeys = Array.from(new Set(sortedKeys));
      for (const key of uniqueKeys) {
        const val = currentScope[key] ?? currentScope['$' + key];
        if (val !== undefined) {
          const pattern = new RegExp(`\\$\\{${key}\\}|\\$\\(${key}\\)|\\$${key}(?![a-zA-Z0-9])`, 'g');
          resolvedLine = resolvedLine.replace(pattern, String(val));
        }
      }

      // 行内のパイプ区切り各部で、数式が含まれていれば計算 (例: 100+50)
      if (resolvedLine.includes('|')) {
        const parts = resolvedLine.split('|');
        const cmdType = parts[0].trim().toUpperCase();
        const calculatedParts = parts.map((part, pIdx) => {
          if (pIdx === 0 || pIdx === 1) return part.trim();
          const trimmed = part.trim();

          // 文字列・テキスト・色フィールドは数式評価しない
          let isTextField = false;
          if (cmdType === 'RECT' || cmdType === 'OVAL' || cmdType === 'DIAMOND' || cmdType === 'ELLIPSE') {
            isTextField = (pIdx === 6 || pIdx === 7 || pIdx >= 9); // color, label, options
          } else if (cmdType === 'TEXT') {
            isTextField = (pIdx === 5 || pIdx >= 6); // color, text
          } else if (cmdType === 'ARROW' || cmdType === 'LINE') {
            isTextField = (pIdx === 4 || pIdx >= 5); // color, label
          } else if (cmdType === 'ARTBOARD') {
            isTextField = (pIdx >= 6); // bgColor, name
          } else if (cmdType === 'GROUP') {
            isTextField = (pIdx >= 6); // name, childIds
          }

          if (isTextField) return trimmed;

          // カンマ区切りの座標群 (例: 10,20 または 10+5,20*2)。ただし関数呼出し (BELOW等) の中は除外
          if (trimmed.includes(',') && !trimmed.includes('(')) {
            return trimmed.split(',').map(sub => {
              const subTrimmed = sub.trim();
              if (/^[0-9.+\-*/%()\s]+$/.test(subTrimmed) && /[+\-*/%]/.test(subTrimmed)) {
                return String(evaluateExpression(subTrimmed, {}));
              }
              return subTrimmed;
            }).join(',');
          }
          // 単一の数式
          if (/^[0-9.+\-*/%()\s]+$/.test(trimmed) && /[+\-*/%]/.test(trimmed)) {
            return String(evaluateExpression(trimmed, {}));
          }
          return trimmed;
        });
        output.push(calculatedParts.join('|'));
      } else {
        output.push(resolvedLine);
      }

      i++;
    }

    return output;
  }

  return processLines(lines, globalScope);
}

// 拡張スタイルオプション（Key-Value文字列）をパースするヘルパー
export function parseExtendedOptions(optStr: string | undefined): {
  cornerRadius?: number;
  shadow?: string;
  opacity?: number;
  dash?: number[];
  strokeWidth?: number;
} {
  if (!optStr) return {};
  const opts: ReturnType<typeof parseExtendedOptions> = {};
  const pairs = optStr.split(',').map(s => s.trim());

  for (const pair of pairs) {
    if (!pair.includes('=')) continue;
    const [rawKey, rawVal] = pair.split('=').map(s => s.trim());
    const key = rawKey.toLowerCase();

    if (key === 'radius' || key === 'cornerradius' || key === 'rx') {
      const val = Number(rawVal);
      if (!isNaN(val)) opts.cornerRadius = val;
    } else if (key === 'shadow' || key === 'dropshadow') {
      opts.shadow = rawVal;
    } else if (key === 'opacity') {
      const val = Number(rawVal);
      if (!isNaN(val)) opts.opacity = val;
    } else if (key === 'dash' || key === 'dashed') {
      opts.dash = rawVal.split(/[ :]/).map(Number).filter(n => !isNaN(n));
    } else if (key === 'strokewidth') {
      const val = Number(rawVal);
      if (!isNaN(val)) opts.strokeWidth = val;
    } else if (key === 'animate' || key === 'animation') {
      opts.animation = rawVal;
    }
  }

  return opts;
}

// 相対配置式 (BELOW(target, gap), RIGHT_OF(target, gap), ABOVE, LEFT_OF) を解決するヘルパー
export function resolveRelativeCoord(
  valStr: string,
  elementMap: Map<string, any>,
  _axis?: 'x' | 'y'
): number {
  const clean = valStr.trim();
  const belowMatch = clean.match(/^BELOW\(([^,)]+)(?:,\s*([0-9-]+))?\)$/i);
  if (belowMatch) {
    const targetId = belowMatch[1].trim();
    const gap = Number(belowMatch[2] || 0);
    const target = elementMap.get(targetId);
    if (target) {
      return target.y + target.height + gap;
    }
  }

  const rightMatch = clean.match(/^RIGHT_OF\(([^,)]+)(?:,\s*([0-9-]+))?\)$/i);
  if (rightMatch) {
    const targetId = rightMatch[1].trim();
    const gap = Number(rightMatch[2] || 0);
    const target = elementMap.get(targetId);
    if (target) {
      return target.x + target.width + gap;
    }
  }

  const aboveMatch = clean.match(/^ABOVE\(([^,)]+)(?:,\s*([0-9-]+))?\)$/i);
  if (aboveMatch) {
    const targetId = aboveMatch[1].trim();
    const gap = Number(aboveMatch[2] || 0);
    const target = elementMap.get(targetId);
    if (target) {
      return target.y - gap;
    }
  }

  const leftMatch = clean.match(/^LEFT_OF\(([^,)]+)(?:,\s*([0-9-]+))?\)$/i);
  if (leftMatch) {
    const targetId = leftMatch[1].trim();
    const gap = Number(leftMatch[2] || 0);
    const target = elementMap.get(targetId);
    if (target) {
      return target.x - gap;
    }
  }

  return Number(clean || 0);
}

// ----------------------------------------------------------------------------
// メイン: DSL 文字列配列を Sketch 要素オブジェクト配列へパース
// ----------------------------------------------------------------------------

export function parseDSLToElements(commands: string[], elementMap: Map<string, any> = new Map()): any[] {
  // まずマクロ・反復ループ・変数を展開
  const expandedCommands = expandDSLMacros(commands);
  const elements: any[] = [];

  for (const rawCmd of expandedCommands) {
    if (typeof rawCmd !== 'string') continue;
    const cmd = rawCmd.trim();
    if (!cmd) continue;

    const parts = cmd.split('|').map(p => p.trim());
    const type = parts[0].toUpperCase().split(/\s+/)[0];

    if (type === 'CLEAR' || type === 'RESET') {
      elements.push({ type: 'delete', ids: '*' });
      continue;
    }

    if (type === 'DEL') {
      // "DEL|id1,id2", "DEL|*", "DEL id1,id2" (パイプなし空白区切り), "DEL|ALL"
      const targetIds = (parts.length > 1 ? parts[1] : cmd.replace(/^DEL\s+/i, '')) || '';
      elements.push({ type: 'delete', ids: targetIds === 'ALL' ? '*' : targetIds });
      continue;
    }

    // --- ARTBOARD: ARTBOARD|id|x|y|w|h|bgColor|name ---
    if (type === 'ARTBOARD') {
      const id = parts[1] || `art_${Math.random().toString(36).substring(2, 7)}`;
      const x = resolveRelativeCoord(parts[2] || '0', elementMap, 'x');
      const y = resolveRelativeCoord(parts[3] || '0', elementMap, 'y');
      const width = Number(parts[4] || 393);
      const height = Number(parts[5] || 852);
      const colorKey = parts[6] || 'white';
      const name = parts[7] || 'Artboard';
      const colors = resolveColor(colorKey, 'white');

      const elemObj: SketchElement = {
        type: 'artboard',
        id,
        name,
        x,
        y,
        width,
        height,
        backgroundColor: colors.fill,
        strokeColor: colors.stroke || '#cbd5e1',
        strokeWidth: 1,
        opacity: 100,
        text: name
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
      continue;
    }

    // --- GROUP: GROUP|id|x|y|w|h|name|childIds ---
    if (type === 'GROUP') {
      const id = parts[1] || `grp_${Math.random().toString(36).substring(2, 7)}`;
      const x = resolveRelativeCoord(parts[2] || '0', elementMap, 'x');
      const y = resolveRelativeCoord(parts[3] || '0', elementMap, 'y');
      const width = Number(parts[4] || 200);
      const height = Number(parts[5] || 200);
      const name = parts[6] || 'Group';
      const childIds = parts[7] ? parts[7].split(',').map(s => s.trim()) : [];

      const elemObj: SketchElement = {
        type: 'group',
        id,
        name,
        x,
        y,
        width,
        height,
        backgroundColor: 'transparent',
        strokeColor: '#94a3b8',
        strokeWidth: 1,
        dash: [4, 4],
        childIds
      };

      elementMap.set(id, elemObj);
      elements.push(elemObj);
      continue;
    }

    // --- RECT, OVAL, ELLIPSE, DIAMOND ---
    if (type === 'RECT' || type === 'OVAL' || type === 'ELLIPSE' || type === 'DIAMOND') {
      // Syntax: TYPE|id|x|y|width|height|color|label|angle|options
      // またはカンマ座標: TYPE|id|x,y,w,h|color|label|angle|options
      const id = parts[1] || `sketch_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, width = 140, height = 70;
      let colorKey = 'blue', labelText = '', rawAngle = '', optStr = '';

      const isCommaCoords = parts[2] && !parts[2].includes('(') && parts[2].includes(',') && parts[2].split(',').length >= 4;
      if (isCommaCoords) {
        const coords = parts[2].split(',').map(s => s.trim());
        x = resolveRelativeCoord(coords[0] || '100', elementMap, 'x');
        y = resolveRelativeCoord(coords[1] || '100', elementMap, 'y');
        width = Number(coords[2] || 140);
        height = Number(coords[3] || 70);
        colorKey = parts[3] || 'blue';
        labelText = parts[4] || '';
        rawAngle = parts[5] || '';
        optStr = parts[6] || '';
      } else {
        x = resolveRelativeCoord(parts[2] || '100', elementMap, 'x');
        y = resolveRelativeCoord(parts[3] || '100', elementMap, 'y');
        width = Number(parts[4] || 140);
        height = Number(parts[5] || 70);
        colorKey = parts[6] || 'blue';
        labelText = parts[7] || '';
        rawAngle = parts[8] || '';
        optStr = parts[9] || '';
      }

      const colors = resolveColor(colorKey, 'blue');
      const shapeType = (type === 'RECT') ? 'rectangle' : (type === 'DIAMOND' ? 'diamond' : 'oval');
      const numAngle = Number(rawAngle || 0);
      const angle = numAngle;
      const extraOpts = parseExtendedOptions(optStr);

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
        strokeWidth: extraOpts.strokeWidth ?? 2,
        opacity: extraOpts.opacity ?? 100,
        cornerRadius: extraOpts.cornerRadius,
        shadow: extraOpts.shadow,
        dash: extraOpts.dash,
        animation: extraOpts.animation
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
      const colorKey = parts[5] || 'blue';
      const labelText = parts[6] || '';

      const colors = resolveColor(colorKey, 'blue');
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
    } else if (type === 'POLYGON') {
      // Syntax: POLYGON|id|x1,y1|x2,y2|x3,y3|x4,y4...|color|label
      const id = parts[1] || `poly_${Math.random().toString(36).substring(2, 7)}`;
      let colorKey = 'blue';
      let labelText = '';
      const rawPoints: number[][] = [];

      const pointParts = parts.slice(2);
      if (pointParts.length >= 2 && !pointParts[pointParts.length - 1].includes(',') && !Number.isFinite(Number(pointParts[pointParts.length - 1]))) {
        labelText = pointParts.pop() || '';
      }
      if (pointParts.length >= 1 && !pointParts[pointParts.length - 1].includes(',') && !Number.isFinite(Number(pointParts[pointParts.length - 1]))) {
        colorKey = pointParts.pop() || 'blue';
      }

      for (const p of pointParts) {
        if (p.includes(',')) {
          const subCoords = p.split(',').map(s => Number(s.trim()));
          for (let i = 0; i < subCoords.length; i += 2) {
            if (i + 1 < subCoords.length && !isNaN(subCoords[i]) && !isNaN(subCoords[i + 1])) {
              rawPoints.push([subCoords[i], subCoords[i + 1]]);
            }
          }
        }
      }

      if (rawPoints.length >= 3) {
        const xs = rawPoints.map(p => p[0]);
        const ys = rawPoints.map(p => p[1]);
        const minX = Math.min(...xs);
        const minY = Math.min(...ys);
        const maxX = Math.max(...xs);
        const maxY = Math.max(...ys);
        const width = Math.max(maxX - minX, 1);
        const height = Math.max(maxY - minY, 1);
        const colors = resolveColor(colorKey, 'blue');

        const relPoints = rawPoints.map(p => [p[0] - minX, p[1] - minY]);
        if (relPoints[0][0] !== relPoints[relPoints.length - 1][0] || relPoints[0][1] !== relPoints[relPoints.length - 1][1]) {
          relPoints.push([relPoints[0][0], relPoints[0][1]]);
        }

        const elemObj: SketchElement = {
          type: 'polygon',
          id,
          name: labelText || 'Polygon',
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
          points: relPoints
        };

        elementMap.set(id, elemObj);
        elements.push(elemObj);
      }
    } else if (type === 'TEXT') {
      // Syntax: TEXT|id|x|y|fontSize|color|text
      const id = parts[1] || `txt_${Math.random().toString(36).substring(2, 7)}`;
      let x = 100, y = 100, fontSize = 18, colorKey = 'dark', text = '';

      const isCommaCoords = parts[2] && !parts[2].includes('(') && parts[2].includes(',') && parts.length <= 6;
      if (isCommaCoords) {
        const coords = parts[2].split(',').map(s => s.trim());
        x = resolveRelativeCoord(coords[0] || '100', elementMap, 'x');
        y = resolveRelativeCoord(coords[1] || '100', elementMap, 'y');
        fontSize = Number(parts[3] || 18);
        colorKey = parts[4] || 'dark';
        text = parts.slice(5).join('|') || '';
      } else {
        x = resolveRelativeCoord(parts[2] || '100', elementMap, 'x');
        y = resolveRelativeCoord(parts[3] || '100', elementMap, 'y');
        fontSize = Number(parts[4] || 18);
        colorKey = parts[5] || 'dark';
        text = parts.slice(6).join('|') || '';
      }

      const colors = resolveColor(colorKey, 'dark');
      const textColor = (colorKey.startsWith('#') || colorKey.startsWith('rgb')) ? colorKey : colors.stroke;
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
        strokeColor: textColor,
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
      const colorKey = parts[4] || 'dark';
      const labelText = parts[5] || '';
      const colors = resolveColor(colorKey, 'dark');
      const lineColor = (colorKey.startsWith('#') || colorKey.startsWith('rgb')) ? colorKey : colors.stroke;

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
        strokeColor: lineColor,
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
          strokeColor: lineColor
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
  if (modelName.includes('gemini-3.7') || modelName.includes('gemini-3.1')) {
    return {
      thinkingBudget: 0
    };
  }
  return undefined;
}
