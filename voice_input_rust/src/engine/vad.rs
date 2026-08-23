pub trait VadEngine: Send + Sync {
    fn process(&mut self, samples: &[f32]) -> bool;
}
