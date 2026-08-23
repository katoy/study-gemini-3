#![allow(dead_code)]

mod audio;
mod dictionary;
mod engine;
mod inserter;
mod ui;

fn setup_custom_fonts(ctx: &egui::Context) {
    let mut fonts = egui::FontDefinitions::default();

    let font_paths = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ];

    for path in font_paths {
        if let Ok(font_data) = std::fs::read(path) {
            fonts.font_data.insert(
                "japanese_font".to_owned(),
                egui::FontData::from_owned(font_data),
            );
            fonts
                .families
                .entry(egui::FontFamily::Proportional)
                .or_default()
                .insert(0, "japanese_font".to_owned());
            fonts
                .families
                .entry(egui::FontFamily::Monospace)
                .or_default()
                .push("japanese_font".to_owned());
            ctx.set_fonts(fonts);
            tracing::info!("Successfully loaded Japanese font from {}", path);
            return;
        }
    }
    tracing::warn!("No Japanese system font found!");
}

fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    tracing::info!("VoiceInput Rust Desktop Application Starting...");

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_always_on_top(),
        ..Default::default()
    };
    eframe::run_native(
        "VoiceInput (Rust)",
        options,
        Box::new(|cc| {
            setup_custom_fonts(&cc.egui_ctx);
            Ok(Box::new(ui::VoiceInputApp::default()))
        }),
    )
    .map_err(|e| anyhow::anyhow!("eframe error: {:?}", e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_setup_custom_fonts() {
        let ctx = egui::Context::default();
        setup_custom_fonts(&ctx);
    }
}
