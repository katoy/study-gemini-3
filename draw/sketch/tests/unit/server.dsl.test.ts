import { describe, expect, it } from 'vitest';
import { parseDSLToElements, getThinkingConfigFor, COLOR_PALETTE, resolveColor, evaluateExpression } from '../../dsl';

describe('parseDSLToElements for Sketch', () => {
  it('RECT を rectangle 要素に変換する', () => {
    const [elem] = parseDSLToElements(['RECT|box1|10|20|140|70|blue|Hello']);
    expect(elem).toMatchObject({
      type: 'rectangle',
      id: 'box1',
      x: 10,
      y: 20,
      width: 140,
      height: 70,
      text: 'Hello',
      strokeColor: COLOR_PALETTE.blue.stroke,
      backgroundColor: COLOR_PALETTE.blue.fill,
    });
  });

  it('OVAL / ELLIPSE / DIAMOND をそれぞれの shape type に変換する', () => {
    const [oval] = parseDSLToElements(['OVAL|o1|0|0|100|50|green|']);
    const [ellipse] = parseDSLToElements(['ELLIPSE|e1|0|0|100|50|green|']);
    const [diamond] = parseDSLToElements(['DIAMOND|d1|0|0|100|50|red|']);
    expect(oval.type).toBe('oval');
    expect(ellipse.type).toBe('oval');
    expect(diamond.type).toBe('diamond');
  });

  it('TEXT をテキスト要素に変換する', () => {
    const [elem] = parseDSLToElements(['TEXT|txt1|5|5|18|dark|1 + 2 = 3']);
    expect(elem).toMatchObject({
      type: 'text',
      id: 'txt1',
      text: '1 + 2 = 3',
      fontSize: 18,
    });
  });

  it('DEL は delete マーカーに変換される', () => {
    expect(parseDSLToElements(['DEL|box1,box2'])).toEqual([{ type: 'delete', ids: 'box1,box2' }]);
    expect(parseDSLToElements(['CLEAR'])).toEqual([{ type: 'delete', ids: '*' }]);
    expect(parseDSLToElements(['RESET'])).toEqual([{ type: 'delete', ids: '*' }]);
    expect(parseDSLToElements(['DEL ALL'])).toEqual([{ type: 'delete', ids: '*' }]);
    expect(parseDSLToElements(['DEL box1,box2'])).toEqual([{ type: 'delete', ids: 'box1,box2' }]);
  });

  it('未知のコマンドタイプは無視する', () => {
    const elements = parseDSLToElements(['UNKNOWN|foo|bar']);
    expect(elements).toEqual([]);
  });

  it('ARROW は同一コマンド配列内の既存要素IDを座標解決に使う', () => {
    const elements = parseDSLToElements([
      'RECT|box1|0|0|100|60|blue|A',
      'RECT|box2|300|0|100|60|blue|B',
      'ARROW|arr1|box1|box2|dark|',
    ]);
    const arrow = elements.find((e) => e.id === 'arr1');
    expect(arrow.x).toBe(50);
    expect(arrow.y).toBe(30);
    expect(arrow.points).toEqual([[0, 0], [300, 0]]);
  });

  it('ARROW は座標指定 "x,y" 形式もサポートする', () => {
    const [arrow] = parseDSLToElements(['ARROW|arr1|0,0|100,50|dark|']);
    expect(arrow.x).toBe(0);
    expect(arrow.y).toBe(0);
    expect(arrow.points).toEqual([[0, 0], [100, 50]]);
  });

  it('TRIANGLE をポリゴン要素として変換する', () => {
    const [tri] = parseDSLToElements(['TRIANGLE|tri1|0,0|100,0|50,80|green|Label']);
    expect(tri.type).toBe('triangle');
    expect(tri.x).toBe(0);
    expect(tri.y).toBe(0);
    expect(tri.width).toBe(100);
    expect(tri.height).toBe(80);
    expect(tri.text).toBe('Label');
  });

  it('POLYGON を正しく多角形要素（polygon）として変換する', () => {
    const [poly] = parseDSLToElements(['POLYGON|poly1|10,20|110,20|110,120|10,120|blue|Quad']);
    expect(poly.type).toBe('polygon');
    expect(poly.x).toBe(10);
    expect(poly.y).toBe(20);
    expect(poly.width).toBe(100);
    expect(poly.height).toBe(100);
    expect(poly.text).toBe('Quad');
    expect(poly.points?.length).toBe(5); // closed polygon
  });

  it('カンマ区切りRECT (x,y,w,h) を正しく解釈する', () => {
    const [elem] = parseDSLToElements(['RECT|box1|50,60,200,100|sketch|Card|45']);
    expect(elem).toMatchObject({
      type: 'rectangle',
      id: 'box1',
      x: 50,
      y: 60,
      width: 200,
      height: 100,
      text: 'Card',
      strokeColor: COLOR_PALETTE.sketch.stroke,
    });
    expect(elem.angle).toBe(45);
  });

  it('animate / animation オプションをパースして要素に設定する', () => {
    const [elem] = parseDSLToElements(['RECT|box1|100|100|120|120|orange||0|animate=spin']);
    expect(elem.animation).toBe('spin');
  });

  it('HEX カラーコードや black/white を正しく解釈し、青にフォールバックしない', () => {
    const elements = parseDSLToElements([
      'RECT|board|80|80|580|580|#1b4332||0',
      'OVAL|white_piece|316|316|46|46|#ffffff|',
      'OVAL|black_piece|376|316|46|46|#1e1e1e|',
      'OVAL|shadow|318|318|46|46|#22222233|',
      'TEXT|title|270|40|24|#1b4332|オセロ',
      'LINE|line1|130,190|610,190|#1b4332|',
    ]);

    const board = elements.find((e) => e.id === 'board');
    expect(board.backgroundColor).toBe('#1b4332');

    const whitePiece = elements.find((e) => e.id === 'white_piece');
    expect(whitePiece.backgroundColor).toBe('#ffffff');
    expect(whitePiece.strokeColor).toBe('#94a3b8');

    const blackPiece = elements.find((e) => e.id === 'black_piece');
    expect(blackPiece.backgroundColor).toBe('#1e1e1e');
    expect(blackPiece.strokeColor).toBe('#000000');

    const shadow = elements.find((e) => e.id === 'shadow');
    expect(shadow.backgroundColor).toBe('#22222233');
    expect(shadow.strokeColor).toBe('transparent');

    const title = elements.find((e) => e.id === 'title');
    expect(title.strokeColor).toBe('#1b4332');

    const line = elements.find((e) => e.id === 'line1');
    expect(line.strokeColor).toBe('#1b4332');
  });

  it('ARTBOARD を正しくアートボード要素に変換する', () => {
    const [art] = parseDSLToElements(['ARTBOARD|iphone|0|0|393|852|white|iPhone 16']);
    expect(art).toMatchObject({
      type: 'artboard',
      id: 'iphone',
      x: 0,
      y: 0,
      width: 393,
      height: 852,
      name: 'iPhone 16',
      backgroundColor: '#ffffff',
    });
  });

  it('GROUP を正しくグループ要素に変換する', () => {
    const [grp] = parseDSLToElements(['GROUP|nav|0|0|393|60|NavBar|logo,menu,search']);
    expect(grp).toMatchObject({
      type: 'group',
      id: 'nav',
      x: 0,
      y: 0,
      width: 393,
      height: 60,
      name: 'NavBar',
      childIds: ['logo', 'menu', 'search'],
    });
  });

  it('拡張スタイルオプション（radius, shadow, opacity, dash）を正しくパースする', () => {
    const [card] = parseDSLToElements([
      'RECT|card1|50|50|200|100|blue|Card|0|radius=16,shadow=0:4:12:#00000020,opacity=90,dash=4 4,strokeWidth=3'
    ]);
    expect(card).toMatchObject({
      id: 'card1',
      cornerRadius: 16,
      shadow: '0:4:12:#00000020',
      opacity: 90,
      dash: [4, 4],
      strokeWidth: 3,
    });
  });

  it('LET による変数定義と数式展開をサポートする', () => {
    const commands = [
      'LET startX = 50',
      'LET width = 120',
      'RECT|box1|$startX|100|$width|60|blue|Test',
      'RECT|box2|$startX + $width + 20|100|$width|60|green|Next',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(2);
    expect(elements[0].x).toBe(50);
    expect(elements[0].width).toBe(120);
    expect(elements[1].x).toBe(190);
    expect(elements[1].width).toBe(120);
  });

  it('DEF と CALL によるメソッド/テンプレート定義と展開をサポートする', () => {
    const commands = [
      'DEF Card(id, x, y, title, color)',
      '  RECT|$id_bg|$x|$y|180|80|$color||0|radius=8',
      '  TEXT|$id_txt|$x + 10|$y + 10|14|dark|$title',
      'END',
      'CALL Card(c1, 100, 100, "Dashboard", blue)',
      'CALL Card(c2, 300, 100, "Settings", purple)',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(4);

    const c1Bg = elements.find((e) => e.id === 'c1_bg');
    expect(c1Bg).toBeDefined();
    expect(c1Bg.x).toBe(100);
    expect(c1Bg.cornerRadius).toBe(8);

    const c1Txt = elements.find((e) => e.id === 'c1_txt');
    expect(c1Txt).toBeDefined();
    expect(c1Txt.x).toBe(110);
    expect(c1Txt.text).toBe('Dashboard');

    const c2Bg = elements.find((e) => e.id === 'c2_bg');
    expect(c2Bg).toBeDefined();
    expect(c2Bg.x).toBe(300);
  });

  it('REPEAT ループを展開して複数要素を生成する', () => {
    const commands = [
      'REPEAT 3 AS $i',
      '  RECT|item_$i|100 + $i * 120|200|100|50|blue|Item $i',
      'END',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(3);
    expect(elements[0].x).toBe(100);
    expect(elements[0].text).toBe('Item 0');
    expect(elements[1].x).toBe(220);
    expect(elements[1].text).toBe('Item 1');
    expect(elements[2].x).toBe(340);
    expect(elements[2].text).toBe('Item 2');
  });

  it('GRID ループを展開して2次元配置（$x, $y, $r, $c）を生成する', () => {
    const commands = [
      'GRID 2, 3 AS $r, $c AT 50, 60 SIZE 40, 40',
      '  RECT|cell_$r_$c|$x|$y|35|35|green|$r-$c',
      'END',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(6); // 2 rows * 3 cols

    const cell00 = elements.find((e) => e.id === 'cell_0_0');
    expect(cell00).toMatchObject({ x: 50, y: 60, text: '0-0' });

    const cell12 = elements.find((e) => e.id === 'cell_1_2');
    expect(cell12).toMatchObject({ x: 50 + 2 * 40, y: 60 + 1 * 40, text: '1-2' });
  });

  it('相対配置 BELOW と RIGHT_OF を正しく解決する', () => {
    const commands = [
      'RECT|header|100|50|400|60|dark|Header',
      'RECT|sidebar|100|BELOW(header, 20)|100|300|gray|Sidebar',
      'RECT|content|RIGHT_OF(sidebar, 15)|BELOW(header, 20)|285|300|white|Content',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(3);

    const sidebar = elements.find((e) => e.id === 'sidebar');
    expect(sidebar.y).toBe(50 + 60 + 20); // 130

    const content = elements.find((e) => e.id === 'content');
    expect(content.x).toBe(100 + 100 + 15); // 215
    expect(content.y).toBe(130);
  });

  it('相対配置 ABOVE と LEFT_OF を正しく解決する', () => {
    const commands = [
      'RECT|base|200|200|100|50|blue|Base',
      'RECT|top|200|ABOVE(base, 10)|100|40|green|Top',
      'RECT|left|LEFT_OF(base, 15)|200|80|50|orange|Left',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(3);

    const top = elements.find((e) => e.id === 'top');
    expect(top.y).toBe(200 - 10); // 190

    const left = elements.find((e) => e.id === 'left');
    expect(left.x).toBe(200 - 15); // 185
  });

  it('TEXT のカンマ座標 (x,y) を正しく解決する', () => {
    const [txt] = parseDSLToElements(['TEXT|t1|50,80|22|dark|Comma Text']);
    expect(txt.x).toBe(50);
    expect(txt.y).toBe(80);
    expect(txt.fontSize).toBe(22);
    expect(txt.text).toBe('Comma Text');
  });

  it('resolveColor の全分岐をカバーする', () => {
    expect(resolveColor(undefined).fill).toBe(COLOR_PALETTE.blue.fill);
    expect(resolveColor('white,black')).toEqual({ fill: '#ffffff', stroke: '#000000' });
    expect(resolveColor('#123456')).toEqual({ fill: '#123456', stroke: '#123456' });
    expect(resolveColor('rgb(10, 20, 30)')).toEqual({ fill: 'rgb(10, 20, 30)', stroke: 'rgb(10, 20, 30)' });
    expect(resolveColor('hsl(120, 50%, 50%)')).toEqual({ fill: 'hsl(120, 50%, 50%)', stroke: 'hsl(120, 50%, 50%)' });
    expect(resolveColor('black')).toEqual({ fill: '#1e1e1e', stroke: '#000000' });
    expect(resolveColor('white')).toEqual({ fill: '#ffffff', stroke: '#94a3b8' });
    expect(resolveColor('nonexistent_color', 'green').fill).toBe(COLOR_PALETTE.green.fill);
  });

  it('evaluateExpression の算術演算とエッジケースをカバーする', () => {
    expect(evaluateExpression('((10 + 20) * 2) / 4 % 5', {})).toBe(15 % 5);
    expect(evaluateExpression('-10 + +5', {})).toBe(-5);
    expect(evaluateExpression('10 / 0', {})).toBe(0);
    expect(evaluateExpression('10 % 0', {})).toBe(0);
    expect(evaluateExpression('not_a_number', {})).toBe(0);
    expect(evaluateExpression('10 + (2 * 3', {})).toBe(16);
  });

  it('expandDSLMacros のコメントや文字列変数、未定義マクロを適切に処理する', () => {
    const commands = [
      '# this is comment',
      '// this is another comment',
      'LET title = "Hello World"',
      'LET quote = \'Single Quote\'',
      'TEXT|txt1|10|10|16|dark|$title',
      'TEXT|txt2|10|40|16|dark|$quote',
      'CALL NonExistentMacro(foo, bar)',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(2);
    expect(elements[0].text).toBe('Hello World');
    expect(elements[1].text).toBe('Single Quote');
  });

  it('ネストした REPEAT / GRID や再帰ガードを安全に処理する', () => {
    const commands = [
      'REPEAT 2 AS $i',
      '  REPEAT 2 AS $j',
      '    RECT|box_$i_$j|$i * 100 + $j * 50|50|40|30|blue|',
      '  END',
      'END',
      'GRID 1, 1 AS $r, $c',
      '  REPEAT 1 AS $k',
      '    RECT|grid_sub|0|0|10|10|blue|',
      '  END',
      'END',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(5);
  });

  it('マクロ呼び出しで変数を引数に渡し、再帰上限ガードが機能する', () => {
    const commands = [
      'LET colorVal = "red"',
      'DEF Sub(id, col)',
      '  RECT|$id|0|0|50|50|$col|',
      'END',
      'CALL Sub(s1, $colorVal)',
      'DEF Recurse()',
      '  CALL Recurse()',
      'END',
      'CALL Recurse()',
    ];
    const elements = parseDSLToElements(commands);
    expect(elements).toHaveLength(1);
    expect(elements[0].id).toBe('s1');
  });

  it('非文字列や空行入力、ARROW のラベル設定を安全に処理する', () => {
    const elements = parseDSLToElements([
      null as any,
      undefined as any,
      '   ',
      'RECT|r1|0|0|100|50|blue|R1',
      'RECT|r2|200|0|100|50|blue|R2',
      'ARROW|a1|r1|r2|dark|Step Label',
    ]);
    expect(elements).toHaveLength(3);
    const arrow = elements.find((e) => e.id === 'a1');
    expect(arrow?.label?.text).toBe('Step Label');
  });

  it('括弧付き算術式や空の拡張スタイルオプションを処理する', () => {
    expect(evaluateExpression('(10 + 20)', {})).toBe(30);
    expect(evaluateExpression('((5))', {})).toBe(5);

    const [rectNoOpt] = parseDSLToElements(['RECT|b_no_opt|0|0|10|10|blue||0|invalid_pair,radius=notanumber']);
    expect(rectNoOpt).toBeDefined();
    expect(rectNoOpt.cornerRadius).toBeUndefined();
  });
});

describe('getThinkingConfigFor', () => {
  it('gemini-3.7 や gemini-3.1 では thinkingBudget: 0 を返す', () => {
    expect(getThinkingConfigFor('gemini-3.7-flash')).toEqual({ thinkingBudget: 0 });
    expect(getThinkingConfigFor('gemini-3.1-flash-lite')).toEqual({ thinkingBudget: 0 });
  });

  it('thinkingConfig 非対応/不要モデルでは undefined を返す', () => {
    expect(getThinkingConfigFor('gemini-3.6-flash')).toBeUndefined();
    expect(getThinkingConfigFor('gemini-3.5-flash-lite')).toBeUndefined();
    expect(getThinkingConfigFor('gemini-1.5-pro')).toBeUndefined();
  });
});
