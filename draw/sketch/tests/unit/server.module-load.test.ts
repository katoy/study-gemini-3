import { describe, expect, it } from 'vitest';
import * as serverModule from '../../server';

describe('server module loading for Sketch', () => {
  it('主要な関数・オブジェクトが export されている', () => {
    expect(typeof serverModule.createChatHandler).toBe('function');
    expect(typeof serverModule.streamGeminiResponse).toBe('function');
    expect(typeof serverModule.mockGeminiStream).toBe('function');
    expect(typeof serverModule.handleWsConnection).toBe('function');
    expect(typeof serverModule.broadcast).toBe('function');
    expect(serverModule.clients).toBeInstanceOf(Set);
    expect(Array.isArray(serverModule.sketchTools)).toBe(true);
    expect(typeof serverModule.SYSTEM_INSTRUCTION).toBe('string');
  });
});
