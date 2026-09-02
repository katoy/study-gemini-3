import { GoogleGenAI } from '@google/genai';

const apiKey = process.env.GEMINI_API_KEY;
if (!apiKey) {
  console.error('GEMINI_API_KEY not set');
  process.exit(1);
}

const ai = new GoogleGenAI({ apiKey });

async function test() {
  try {
    console.log('🧪 Testing gemini-3.6-flash with minimal request...');
    const response = await ai.models.generateContent({
      model: 'gemini-3.6-flash',
      contents: [{ role: 'user', parts: [{ text: 'Hello' }] }],
    });
    console.log('✅ Success');
  } catch (err) {
    console.error('❌ Error:', err.message || err);
  }
}

test();
