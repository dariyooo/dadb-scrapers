import 'package:builder/sentence_filter.dart';
import 'package:test/test.dart';

void main() {
  test('accepts plain sentences', () {
    expect(rejectionReason('今日は天気がいいから散歩に行こう。'), isNull);
    expect(rejectionReason('「もう帰るの？」と彼女は言った。'), isNull);
  });

  test('unbalanced brackets', () {
    expect(rejectionReason('「これは終わらない。'), 'unbalanced-brackets');
    expect(rejectionReason('これは（変だ」。'), 'unbalanced-brackets');
  });

  test('starts with closer', () {
    expect(rejectionReason('」と言った。'), 'starts-with-closer');
  });

  test('fully quoted utterances are rejected as situational dialogue', () {
    expect(rejectionReason('「ふふ。ええ、そうですね」'), 'quoted');
    expect(rejectionReason('「もう帰るところだったんだよ」。'), 'quoted');
    expect(rejectionReason('『拝啓、アレン様。お元気ですか』'), 'quoted');
    // embedded quotes inside narration stay
    expect(rejectionReason('彼女は「もう帰る」とだけ言った。'), isNull);
    // chained quotes are not a single enclosure; unusual but not quoted
    expect(rejectionReason('「おはよう」「おはようございます」'), isNull);
  });

  test('dangling quote halves stay rejected (quote interiors)', () {
    expect(rejectionReason('「あはは。今日はいい天気だ。'), 'unbalanced-brackets');
    expect(rejectionReason('今日はいい天気だと思ったんだ」'), 'unbalanced-brackets');
  });

  test('forbidden char', () {
    expect(rejectionReason('今日は★晴れだ。'), 'forbidden-char');
    expect(rejectionReason('リンクはhttp://例.comを見て。'), 'forbidden-char');
  });

  test('no japanese', () {
    expect(rejectionReason('hello world 123.'), 'no-japanese');
  });

  test('char and unit runs', () {
    expect(rejectionReason('ああああいい天気だ。'), 'char-run');
    expect(rejectionReason('だからだからだから行くんだ。'), 'unit-run');
  });

  test('length bounds on meaty chars', () {
    expect(rejectionReason('短い。'), 'too-short');
    expect(rejectionReason('男は度胸。'), isNull);
    expect(rejectionReason('${'長い文章をここに書く' * 23}。'), 'too-long');
  });

  test('common symbols in prose are exempt', () {
    expect(rejectionReason('全体の5％ほどは魔法の品だ。'), isNull);
    expect(rejectionReason('気温は30℃を超えた。'), isNull);
  });
}
