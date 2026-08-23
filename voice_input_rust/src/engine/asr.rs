pub trait StreamingAsrEngine: Send + Sync {
    fn feed(&mut self, samples: &[f32]) -> String;
}

pub trait BatchAsrEngine: Send + Sync {
    fn transcribe(&mut self, audio_data: &[f32]) -> anyhow::Result<String>;
}

/// A dummy ASR engine used for testing or when local models are not loaded.
pub struct DummyAsrEngine {
    pub dummy_text: String,
}

impl Default for DummyAsrEngine {
    fn default() -> Self {
        Self {
            dummy_text: "これはローカルASRのテスト音声入力です。".to_string(),
        }
    }
}

impl BatchAsrEngine for DummyAsrEngine {
    fn transcribe(&mut self, _audio_data: &[f32]) -> anyhow::Result<String> {
        Ok(self.dummy_text.clone())
    }
}

/// Local Whisper ASR engine powered by whisper-rs.
pub struct WhisperAsrEngine {
    ctx: whisper_rs::WhisperContext,
    language: String,
    initial_prompt: Option<String>,
}

impl WhisperAsrEngine {
    pub fn new(model_path: &str, language: Option<&str>) -> anyhow::Result<Self> {
        let ctx = whisper_rs::WhisperContext::new_with_params(
            model_path,
            whisper_rs::WhisperContextParameters::default(),
        )
        .map_err(|e| {
            anyhow::anyhow!(
                "Failed to load Whisper model from '{}': {:?}",
                model_path,
                e
            )
        })?;

        Ok(Self {
            ctx,
            language: language.unwrap_or("ja").to_string(),
            initial_prompt: Some("こんにちは。こちらは日本語の文字起こしです。句読点を含めて正確に記述してください。".to_string()),
        })
    }

    pub fn set_initial_prompt(&mut self, prompt: impl Into<String>) {
        let p = prompt.into();
        if p.trim().is_empty() {
            self.initial_prompt = None;
        } else {
            self.initial_prompt = Some(p);
        }
    }
}

impl BatchAsrEngine for WhisperAsrEngine {
    fn transcribe(&mut self, audio_data: &[f32]) -> anyhow::Result<String> {
        let mut state = self
            .ctx
            .create_state()
            .map_err(|e| anyhow::anyhow!("Failed to create Whisper state: {:?}", e))?;

        let mut params =
            whisper_rs::FullParams::new(whisper_rs::SamplingStrategy::Greedy { best_of: 1 });
        params.set_language(Some(&self.language));
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);

        if let Some(ref prompt) = self.initial_prompt {
            params.set_initial_prompt(prompt);
        }

        state
            .full(params, audio_data)
            .map_err(|e| anyhow::anyhow!("Whisper transcription failed: {:?}", e))?;

        let num_segments = state
            .full_n_segments()
            .map_err(|e| anyhow::anyhow!("Failed to get segment count: {:?}", e))?;

        let mut result = String::new();
        for i in 0..num_segments {
            if let Ok(segment) = state.full_get_segment_text(i) {
                result.push_str(&segment);
            }
        }

        Ok(result.trim().to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dummy_asr_engine() {
        let mut engine = DummyAsrEngine::default();
        let result = engine.transcribe(&[0.0; 16000]).unwrap();
        assert_eq!(result, "これはローカルASRのテスト音声入力です。");
    }

    #[test]
    fn test_whisper_asr_engine_invalid_path() {
        let res = WhisperAsrEngine::new("non_existent_model.bin", None);
        assert!(res.is_err());
    }

    #[test]
    fn test_whisper_asr_engine_prompt_and_transcribe() {
        if std::path::Path::new("models/ggml-small.bin").exists() {
            let mut engine = WhisperAsrEngine::new("models/ggml-small.bin", Some("ja")).unwrap();
            engine.set_initial_prompt("テストプロンプト");
            assert!(engine.initial_prompt.is_some());
            engine.set_initial_prompt("   ");
            assert!(engine.initial_prompt.is_none());

            // Transcribe 1 second of silence
            let audio = vec![0.0f32; 16000];
            let res = engine.transcribe(&audio);
            assert!(res.is_ok());
        }
    }

    struct TestStreaming;
    impl StreamingAsrEngine for TestStreaming {
        fn feed(&mut self, _samples: &[f32]) -> String {
            "stream".to_string()
        }
    }

    #[test]
    fn test_streaming_trait() {
        let mut s = TestStreaming;
        assert_eq!(s.feed(&[]), "stream");
    }
}
