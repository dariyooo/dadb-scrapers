/// Sentence quality filter: reject, don't repair.
///
/// Dependency-free so it can move into `language_processing` as a file copy.
library;

/// Bracket pairs treated as type-matched.
const Map<String, String> _closerToOpener = {
  '」': '「',
  '』': '『',
  '）': '（',
  ')': '(',
  '］': '［',
  ']': '[',
  '】': '【',
  '〉': '〈',
  '》': '《',
  '〕': '〔',
  '〟': '〝',
  '≫': '≪',
  '⦆': '⦅',
  '｝': '｛',
  '}': '{',
};
final Set<String> _openers = _closerToOpener.values.toSet();

/// Kana/kanji/CJK — the characters that make a sentence worth keeping.
bool _isMeaty(int r) =>
    (r >= 0x3041 && r <= 0x3096) || // hiragana
    (r >= 0x30A1 && r <= 0x30FA) || // katakana
    (r >= 0x4E00 && r <= 0x9FFF) || // CJK
    (r >= 0x3400 && r <= 0x4DBF) || // CJK ext A
    r == 0x3005 ||
    r == 0x3006 ||
    r == 0x30F6 || // 々〆ヶ
    r == 0x30FC; // ー

bool _isAllowedNonMeaty(int r) =>
    (r >= 0x30 && r <= 0x39) || // 0-9
    (r >= 0x41 && r <= 0x5A) ||
    (r >= 0x61 && r <= 0x7A) || // A-Za-z
    (r >= 0xFF10 && r <= 0xFF19) || // ０-９
    (r >= 0xFF21 && r <= 0xFF3A) ||
    (r >= 0xFF41 && r <= 0xFF5A) || // Ａ-Ｚａ-ｚ
    _exemptPunct.contains(String.fromCharCode(r));

final Set<String> _exemptPunct = {
  '。',
  '、',
  '，',
  '．',
  '！',
  '？',
  '!',
  '?',
  '…',
  '‥',
  '・',
  '―',
  '－',
  '～',
  '〜',
  '：',
  '；',
  "'",
  '"',
  '.',
  ',',
  '％',
  '%',
  '℃',
  '＆',
  ' ',
  '　',
  ..._closerToOpener.keys,
  ..._closerToOpener.values,
};

/// True when one matching bracket pair spans the whole segment (「…」 or
/// 「…」。) — a fully quoted utterance, i.e. situational dialogue.
bool _isFullyEnclosed(List<String> chars) {
  if (!_openers.contains(chars.first)) return false;
  final stack = <String>[];
  for (var i = 0; i < chars.length; i++) {
    final c = chars[i];
    if (_openers.contains(c)) {
      stack.add(c);
    } else if (_closerToOpener.containsKey(c)) {
      if (stack.isEmpty || stack.removeLast() != _closerToOpener[c]) {
        return false; // malformed; the unbalanced check reports it
      }
      if (stack.isEmpty) {
        // Only trailing enders may follow the closing bracket (「…」。).
        for (var j = i + 1; j < chars.length; j++) {
          if (!'。！？!?…‥'.contains(chars[j])) return false;
        }
        return true;
      }
    }
  }
  return false;
}

/// Returns null if the sentence passes, else a reject reason slug.
String? rejectionReason(String sentence) {
  final s = sentence.trim();
  if (s.isEmpty) return 'empty';

  final runes = s.runes.toList();
  final chars = runes.map(String.fromCharCode).toList();

  if (_closerToOpener.containsKey(chars.first)) return 'starts-with-closer';
  if (_isFullyEnclosed(chars)) return 'quoted';

  final stack = <String>[];
  var meaty = 0;
  for (var i = 0; i < runes.length; i++) {
    final c = chars[i];
    if (_openers.contains(c)) {
      stack.add(c);
    } else if (_closerToOpener.containsKey(c)) {
      if (stack.isEmpty || stack.removeLast() != _closerToOpener[c]) {
        return 'unbalanced-brackets';
      }
    }
    if (_isMeaty(runes[i])) {
      meaty++;
    } else if (!_isAllowedNonMeaty(runes[i])) {
      return 'forbidden-char';
    }
  }
  if (stack.isNotEmpty) return 'unbalanced-brackets';

  if (meaty == 0) return 'no-japanese';

  // 4+ identical chars in a row
  var run = 1;
  for (var i = 1; i < chars.length; i++) {
    run = chars[i] == chars[i - 1] ? run + 1 : 1;
    if (run >= 4) return 'char-run';
  }
  // 3+ identical 2-4 char units in a row (morpheme-run approximation)
  for (var unit = 2; unit <= 4; unit++) {
    for (var i = 0; i + unit * 3 <= chars.length; i++) {
      final a = s.substring(i, i + unit);
      if (s.substring(i + unit, i + unit * 2) == a &&
          s.substring(i + unit * 2, i + unit * 3) == a) {
        return 'unit-run';
      }
    }
  }

  // Min: an example needs context around the highlighted word (男は度胸。= 4).
  // Max: loose runaway tripwire; revisit once the splitter fixes + scorer land.
  if (meaty < 4) return 'too-short';
  if (meaty > 200) return 'too-long';
  return null;
}
