use std::collections::HashMap;

#[derive(Default, Debug, Clone)]
pub struct UserDictionary {
    entries: HashMap<String, String>,
}

impl UserDictionary {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(&mut self, reading: impl Into<String>, target: impl Into<String>) {
        self.entries.insert(reading.into(), target.into());
    }

    pub fn apply(&self, text: &str) -> String {
        let mut result = text.to_string();
        for (reading, target) in &self.entries {
            result = result.replace(reading, target);
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_user_dictionary_new_and_default() {
        let dict1 = UserDictionary::new();
        let dict2 = UserDictionary::default();
        assert_eq!(dict1.entries, dict2.entries);
    }

    #[test]
    fn test_user_dictionary_insert_and_apply() {
        let mut dict = UserDictionary::new();
        dict.insert("とうきょう", "東京");
        dict.insert("きょうと", "京都");

        let input = "とうきょうからきょうとへ行く";
        let output = dict.apply(input);
        assert_eq!(output, "東京から京都へ行く");
    }

    #[test]
    fn test_user_dictionary_apply_no_match() {
        let mut dict = UserDictionary::new();
        dict.insert("とうきょう", "東京");

        let input = "おおさか";
        let output = dict.apply(input);
        assert_eq!(output, "おおさか");
    }
}
