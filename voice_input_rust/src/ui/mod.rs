use crate::audio::AudioRecorder;
use crate::dictionary::UserDictionary;
use crate::engine::asr::{BatchAsrEngine, DummyAsrEngine, WhisperAsrEngine};
use crate::engine::refiner::{RefinerEngine, TextRefiner};
use crate::inserter::TextInserter;
use eframe::egui;

pub struct VoiceInputApp {
    pub recording: bool,
    pub preview_text: String,
    pub model_path: String,
    pub selected_preset: usize,
    pub initial_prompt: String,
    pub enable_refiner: bool,
    pub engine_status: String,
    pub recorder: Option<AudioRecorder>,
    pub asr_engine: Box<dyn BatchAsrEngine>,
    pub dictionary: UserDictionary,
    pub refiner: TextRefiner,

    // Dictionary UI inputs
    pub dict_reading_input: String,
    pub dict_target_input: String,

    pub target_pid: Option<i32>,
}


const MODEL_PRESETS: &[(&str, &str)] = &[
    ("tiny (軽量・最速)", "models/ggml-tiny.bin"),
    ("base (標準・軽量)", "models/ggml-base.bin"),
    ("small (高精度・推奨)", "models/ggml-small.bin"),
    ("medium (超高精度)", "models/ggml-medium.bin"),
    ("large-v3 (最高精度)", "models/ggml-large-v3.bin"),
];

impl Default for VoiceInputApp {
    fn default() -> Self {
        let mut model_path = String::from("models/ggml-small.bin");
        if !std::path::Path::new(&model_path).exists() {
            if let Ok(exe_dir) = std::env::current_exe() {
                if let Some(parent) = exe_dir.parent() {
                    let alt_path = parent.join("models/ggml-small.bin");
                    if alt_path.exists() {
                        if let Some(s) = alt_path.to_str() {
                            model_path = s.to_string();
                        }
                    }
                }
            }
        }
        let initial_prompt = String::from("古池や蛙飛び込む水の音。こちらは日本語の文字起こしです。句読点を含めて正確に記述してください。");

        let (asr_engine, engine_status): (Box<dyn BatchAsrEngine>, String) =
            if std::path::Path::new(&model_path).exists() {
                match WhisperAsrEngine::new(&model_path, Some("ja")) {
                    Ok(mut engine) => {
                        engine.set_initial_prompt(&initial_prompt);
                        (Box::new(engine), format!("Loaded model: {}", model_path))
                    }
                    Err(e) => (
                        Box::new(DummyAsrEngine::default()),
                        format!("Failed to load model: {:?}", e),
                    ),
                }
            } else {
                (
                    Box::new(DummyAsrEngine::default()),
                    String::from("Using Dummy Engine (Model file not found)"),
                )
            };

        Self {
            recording: false,
            preview_text: String::new(),
            model_path,
            selected_preset: 2,
            initial_prompt,
            enable_refiner: true,
            engine_status,
            recorder: None,
            asr_engine,
            dictionary: UserDictionary::default(),
            refiner: TextRefiner::default(),
            dict_reading_input: String::new(),
            dict_target_input: String::new(),
            target_pid: None,
        }
    }
}


impl VoiceInputApp {
    fn load_selected_model(&mut self) {
        if std::path::Path::new(&self.model_path).exists() {
            match WhisperAsrEngine::new(&self.model_path, Some("ja")) {
                Ok(mut engine) => {
                    engine.set_initial_prompt(&self.initial_prompt);
                    self.asr_engine = Box::new(engine);
                    self.engine_status = format!("Loaded model: {}", self.model_path);
                }
                Err(e) => {
                    self.engine_status = format!("Failed to load model: {:?}", e);
                }
            }
        } else {
            self.engine_status = format!(
                "Model file not found at '{}'. Please download ggml model.",
                self.model_path
            );
        }
    }

    fn render_model_settings(&mut self, ui: &mut egui::Ui) {
        ui.collapsing("モデル設定 & 精度パラメータ", |ui| {
            ui.horizontal(|ui| {
                ui.label("プリセットモデル:");
                let current_label = MODEL_PRESETS
                    .get(self.selected_preset)
                    .map(|p| p.0)
                    .unwrap_or("カスタム");
                egui::ComboBox::from_id_salt("model_preset_combo")
                    .selected_text(current_label)
                    .show_ui(ui, |ui| {
                        for (i, (name, path)) in MODEL_PRESETS.iter().enumerate() {
                            if ui
                                .selectable_value(&mut self.selected_preset, i, *name)
                                .clicked()
                            {
                                self.model_path = path.to_string();
                            }
                        }
                    });
            });

            ui.horizontal(|ui| {
                ui.label("モデルファイルパス:");
                ui.text_edit_singleline(&mut self.model_path);
                if ui.button("モデルをロード").clicked() {
                    self.load_selected_model();
                }
            });

            ui.horizontal(|ui| {
                ui.label("初期プロンプト (Initial Prompt):");
                ui.text_edit_singleline(&mut self.initial_prompt);
            });
            ui.label(
                egui::RichText::new("※ 文脈や用語を固定・補正するためのプロンプトです。")
                    .small()
                    .weak(),
            );

            ui.checkbox(
                &mut self.enable_refiner,
                "ハルシネーション・ノイズ自動除去フィルターを有効化",
            );
        });
    }

    fn render_dictionary_settings(&mut self, ui: &mut egui::Ui) {
        ui.collapsing("ユーザー辞書・用語置換設定", |ui| {
            ui.horizontal(|ui| {
                ui.label("置換元:");
                ui.text_edit_singleline(&mut self.dict_reading_input);
                ui.label("置換先:");
                ui.text_edit_singleline(&mut self.dict_target_input);
                if ui.button("単語を追加").clicked()
                    && !self.dict_reading_input.trim().is_empty()
                {
                    self.dictionary.insert(
                        self.dict_reading_input.trim(),
                        self.dict_target_input.trim(),
                    );
                    self.dict_reading_input.clear();
                    self.dict_target_input.clear();
                }
            });
        });
    }

    fn toggle_recording(&mut self) {
        if self.recording {
            // Stop recording and process audio
            if let Some(recorder) = self.recorder.take() {
                let audio_data = recorder.get_whisper_samples();
                match self.asr_engine.transcribe(&audio_data) {
                    Ok(raw_text) => {
                        let mut text = raw_text;
                        if self.enable_refiner {
                            if let Ok(refined) = self.refiner.refine(&text) {
                                text = refined;
                            }
                        }
                        text = self.dictionary.apply(&text);
                        self.preview_text = text.clone();
                        if !text.trim().is_empty() {
                            let _ = TextInserter::copy_and_paste(&text, self.target_pid);
                        }
                    }
                    Err(e) => {
                        self.preview_text = format!("Error transcribing: {:?}", e);
                    }
                }
            }
            self.recording = false;
        } else {
            match AudioRecorder::start() {
                Ok(recorder) => {
                    self.recorder = Some(recorder);
                    self.recording = true;
                    self.preview_text.clear();
                }
                Err(e) => {
                    self.preview_text = format!("Error starting audio: {:?}", e);
                }
            }
        }
    }
}

impl eframe::App for VoiceInputApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("VoiceInput - Local Voice Input with Whisper");
            ui.separator();

            self.render_model_settings(ui);
            ui.label(format!("Engine Status: {}", self.engine_status));
            ui.separator();

            self.render_dictionary_settings(ui);
            ui.separator();

            // 自アプリ以外の最前面アプリPIDを常に追跡
            #[cfg(target_os = "macos")]
            {
                if let Some(pid) = crate::inserter::macos_focus::capture_frontmost_app_pid() {
                    self.target_pid = Some(pid);
                }
            }

            let button_text = if self.recording {
                "⏹ 録音停止 & 変換"
            } else {
                "🎙 録音開始"
            };
            if ui.button(button_text).clicked() {
                self.toggle_recording();
            }

            ui.label(format!(
                "ステータス: {}",
                if self.recording {
                    "録音中..."
                } else {
                    "待機中"
                }
            ));
            ui.separator();

            ui.label("変換結果プレビュー:");
            ui.label(&self.preview_text);
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use eframe::App;

    #[test]
    fn test_voice_input_app_default() {
        let app = VoiceInputApp::default();
        assert!(!app.recording);
        assert_eq!(app.preview_text, "");
    }

    #[test]
    fn test_load_selected_model_invalid_path() {
        let mut app = VoiceInputApp::default();
        app.model_path = "invalid/path/to/model.bin".to_string();
        app.load_selected_model();
        assert!(app.engine_status.contains("Model file not found"));
    }

    #[test]
    fn test_load_selected_model_valid_path() {
        if std::path::Path::new("models/ggml-small.bin").exists() {
            let mut app = VoiceInputApp::default();
            app.model_path = "models/ggml-small.bin".to_string();
            app.load_selected_model();
            assert!(app.engine_status.contains("Loaded model"));
        }
    }

    #[test]
    fn test_egui_ui_update() {
        let mut app = VoiceInputApp::default();
        app.dict_reading_input = "テスト入力".to_string();
        app.dict_target_input = "テスト出力".to_string();

        let ctx = egui::Context::default();
        let _ = ctx.run(Default::default(), |ctx| {
            let mut frame: eframe::Frame = unsafe { std::mem::zeroed() };
            app.update(ctx, &mut frame);
        });

        // Verify UI ran without panic
        assert!(!app.recording);
    }
}
