/// Pre-filter repair pass: h2z halfwidth-kana normalization.
///
/// Deliberately does NOT strip outer quotes or repair dangling ones: fully
/// quoted utterances are situational dialogue and are rejected by the filter
/// ('quoted'), and dangling quote halves are quote interiors that the
/// unbalanced-brackets rejection removes.
library;

const Map<String, String> _h2zBase = {
  'ｱ': 'ア',
  'ｲ': 'イ',
  'ｳ': 'ウ',
  'ｴ': 'エ',
  'ｵ': 'オ',
  'ｶ': 'カ',
  'ｷ': 'キ',
  'ｸ': 'ク',
  'ｹ': 'ケ',
  'ｺ': 'コ',
  'ｻ': 'サ',
  'ｼ': 'シ',
  'ｽ': 'ス',
  'ｾ': 'セ',
  'ｿ': 'ソ',
  'ﾀ': 'タ',
  'ﾁ': 'チ',
  'ﾂ': 'ツ',
  'ﾃ': 'テ',
  'ﾄ': 'ト',
  'ﾅ': 'ナ',
  'ﾆ': 'ニ',
  'ﾇ': 'ヌ',
  'ﾈ': 'ネ',
  'ﾉ': 'ノ',
  'ﾊ': 'ハ',
  'ﾋ': 'ヒ',
  'ﾌ': 'フ',
  'ﾍ': 'ヘ',
  'ﾎ': 'ホ',
  'ﾏ': 'マ',
  'ﾐ': 'ミ',
  'ﾑ': 'ム',
  'ﾒ': 'メ',
  'ﾓ': 'モ',
  'ﾔ': 'ヤ',
  'ﾕ': 'ユ',
  'ﾖ': 'ヨ',
  'ﾗ': 'ラ',
  'ﾘ': 'リ',
  'ﾙ': 'ル',
  'ﾚ': 'レ',
  'ﾛ': 'ロ',
  'ﾜ': 'ワ',
  'ｦ': 'ヲ',
  'ﾝ': 'ン',
  'ｧ': 'ァ',
  'ｨ': 'ィ',
  'ｩ': 'ゥ',
  'ｪ': 'ェ',
  'ｫ': 'ォ',
  'ｬ': 'ャ',
  'ｭ': 'ュ',
  'ｮ': 'ョ',
  'ｯ': 'ッ',
  'ｰ': 'ー',
  '｡': '。',
  '｢': '「',
  '｣': '」',
  '､': '、',
  '･': '・',
};

const Map<String, String> _h2zVoiced = {
  'ｶ': 'ガ',
  'ｷ': 'ギ',
  'ｸ': 'グ',
  'ｹ': 'ゲ',
  'ｺ': 'ゴ',
  'ｻ': 'ザ',
  'ｼ': 'ジ',
  'ｽ': 'ズ',
  'ｾ': 'ゼ',
  'ｿ': 'ゾ',
  'ﾀ': 'ダ',
  'ﾁ': 'ヂ',
  'ﾂ': 'ヅ',
  'ﾃ': 'デ',
  'ﾄ': 'ド',
  'ﾊ': 'バ',
  'ﾋ': 'ビ',
  'ﾌ': 'ブ',
  'ﾍ': 'ベ',
  'ﾎ': 'ボ',
  'ｳ': 'ヴ',
};

const Map<String, String> _h2zSemiVoiced = {
  'ﾊ': 'パ',
  'ﾋ': 'ピ',
  'ﾌ': 'プ',
  'ﾍ': 'ペ',
  'ﾎ': 'ポ',
};

String _h2z(String s) {
  final out = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    final c = s[i];
    final next = i + 1 < s.length ? s[i + 1] : '';
    if (next == 'ﾞ' && _h2zVoiced.containsKey(c)) {
      out.write(_h2zVoiced[c]);
      i++;
    } else if (next == 'ﾟ' && _h2zSemiVoiced.containsKey(c)) {
      out.write(_h2zSemiVoiced[c]);
      i++;
    } else if (c == 'ﾞ') {
      out.write('゛');
    } else if (c == 'ﾟ') {
      out.write('゜');
    } else {
      out.write(_h2zBase[c] ?? c);
    }
  }
  return out.toString();
}

String repairSentence(String sentence) => _h2z(sentence.trim());
