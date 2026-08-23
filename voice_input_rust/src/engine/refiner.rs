pub trait RefinerEngine: Send + Sync {
    fn refine(&self, text: &str) -> anyhow::Result<String>;
}

pub struct TextRefiner {
    pub remove_hallucinations: bool,
    pub custom_prompt: Option<String>,
}

impl Default for TextRefiner {
    fn default() -> Self {
        Self {
            remove_hallucinations: true,
            custom_prompt: None,
        }
    }
}

impl TextRefiner {
    pub fn new() -> Self {
        Self::default()
    }

    /// Clean up common Whisper hallucinations in Japanese audio transcriptions.
    pub fn clean_hallucinations(text: &str) -> String {
        let hallucination_patterns = [
            "ご視聴ありがとうございました",
            "ご視聴、ありがとうございました",
            "チャンネル登録お願いします",
            "チャンネル登録をお願いします",
            "高評価お願いします",
            "Subtitles by",
            "Translated by",
            "視聴してくれてありがとう",
            "最後までご視聴いただき",
            "Thank you for watching",
            "Thanks for watching",
            "【字幕】",
            "[音楽]",
            "（音楽）",
            "(音楽)",
            "( 音楽 )",
            "（ 音楽 ）",
            "(拍手)",
            "（拍手）",
            "[笑い]",
            "(音声)",
            "（音声）",
            "( 音声 )",
            "（ 音声 ）",
            "[音声]",
            "【音声】",
            "(音声指示)",
            "（音声指示）",
            "(無音)",
            "（無音）",
            "(ノイズ)",
            "（ノイズ）",
            "( 雑音 )",
            "(雑音)",
            "（雑音）",
            "( 咳 )",
            "(咳)",
            "（咳）",
            "(笑い)",
            "（笑い）",
            "(ため息)",
            "（ため息）",
        ];

        let mut cleaned = text.to_string();
        for pattern in &hallucination_patterns {
            cleaned = cleaned.replace(pattern, "");
        }

        // Remove excessive repetition of consecutive duplicate punctuation or whitespace
        let cleaned = cleaned.trim();
        cleaned.to_string()
    }
}

impl RefinerEngine for TextRefiner {
    fn refine(&self, text: &str) -> anyhow::Result<String> {
        let mut result = text.to_string();
        if self.remove_hallucinations {
            result = Self::clean_hallucinations(&result);
        }
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_text_refiner_clean_hallucinations() {
        let input = "こんにちは。ご視聴ありがとうございました";
        let output = TextRefiner::clean_hallucinations(input);
        assert_eq!(output, "こんにちは。");

        let input_speech = "(音声)";
        let output_speech = TextRefiner::clean_hallucinations(input_speech);
        assert_eq!(output_speech, "");
    }

    #[test]
    fn test_text_refiner_impl() {
        let refiner = TextRefiner::default();
        let input = "テストです。チャンネル登録お願いします";
        let output = refiner.refine(input).unwrap();
        assert_eq!(output, "テストです。");

        let mut refiner_off = TextRefiner::new();
        refiner_off.remove_hallucinations = false;
        let output_off = refiner_off.refine(input).unwrap();
        assert_eq!(output_off, input);
    }
}
