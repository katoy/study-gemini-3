use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::{Arc, Mutex};
use tracing::info;

pub struct AudioBuffer {
    pub buffer: Arc<Mutex<Vec<f32>>>,
    pub sample_rate: u32,
    pub channels: u16,
}

impl AudioBuffer {
    pub fn new(sample_rate: u32, channels: u16) -> Self {
        Self {
            buffer: Arc::new(Mutex::new(Vec::new())),
            sample_rate,
            channels,
        }
    }

    /// Convert recorded audio to 16kHz mono f32 samples for Whisper
    pub fn get_whisper_samples(&self) -> Vec<f32> {
        let raw = match self.buffer.lock() {
            Ok(buf) => buf.clone(),
            Err(_) => return Vec::new(),
        };
        if raw.is_empty() {
            return Vec::new();
        }

        // 1. Convert stereo to mono if needed
        let mono: Vec<f32> = if self.channels > 1 {
            raw.chunks(self.channels as usize)
                .map(|chunk| chunk.iter().sum::<f32>() / self.channels as f32)
                .collect()
        } else {
            raw
        };

        // 2. Resample to 16kHz
        if self.sample_rate == 16000 {
            mono
        } else {
            let step = self.sample_rate as f32 / 16000.0;
            let target_len = (mono.len() as f32 / step) as usize;
            let mut resampled = Vec::with_capacity(target_len);
            for i in 0..target_len {
                let index = (i as f32 * step) as usize;
                if index < mono.len() {
                    resampled.push(mono[index]);
                }
            }
            resampled
        }
    }
}

pub struct AudioRecorder {
    _stream: cpal::Stream,
    pub audio_buffer: AudioBuffer,
}

impl AudioRecorder {
    pub fn start() -> anyhow::Result<Self> {
        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .ok_or_else(|| anyhow::anyhow!("No default input device found"))?;

        let config = device.default_input_config()?;
        let sample_rate = config.sample_rate().0;
        let channels = config.channels();
        info!(
            "Audio input device: {}, sample rate: {}, channels: {}",
            device.name()?,
            sample_rate,
            channels
        );

        let audio_buffer = AudioBuffer::new(sample_rate, channels);
        let buffer_clone = Arc::clone(&audio_buffer.buffer);

        let stream = match config.sample_format() {
            cpal::SampleFormat::F32 => device.build_input_stream(
                &config.into(),
                move |data: &[f32], _| {
                    if let Ok(mut buf) = buffer_clone.lock() {
                        buf.extend_from_slice(data);
                    }
                },
                |err| eprintln!("Audio stream error: {:?}", err),
                None,
            )?,
            _ => return Err(anyhow::anyhow!("Unsupported audio sample format")),
        };

        stream.play()?;
        Ok(Self {
            _stream: stream,
            audio_buffer,
        })
    }

    pub fn get_whisper_samples(&self) -> Vec<f32> {
        self.audio_buffer.get_whisper_samples()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_audio_buffer_empty() {
        let buf = AudioBuffer::new(16000, 1);
        assert!(buf.get_whisper_samples().is_empty());
    }

    #[test]
    fn test_audio_buffer_poisoned() {
        let buf = AudioBuffer::new(16000, 1);
        let b = Arc::clone(&buf.buffer);
        let _ = std::panic::catch_unwind(|| {
            let _guard = b.lock().unwrap();
            panic!("poison");
        });
        assert!(buf.get_whisper_samples().is_empty());
    }

    #[test]
    fn test_audio_buffer_stereo_resample() {
        let buf = AudioBuffer::new(32000, 2);
        {
            let mut data = buf.buffer.lock().unwrap();
            // 4 stereo samples (8 floats)
            data.extend_from_slice(&[0.2, 0.4, 0.6, 0.8, 1.0, 1.0, 0.0, 0.0]);
        }
        let samples = buf.get_whisper_samples();
        assert_eq!(samples.len(), 2);
        assert!((samples[0] - 0.3).abs() < 1e-5);
        assert!((samples[1] - 1.0).abs() < 1e-5);
    }
}

