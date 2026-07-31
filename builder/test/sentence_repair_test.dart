import 'package:builder/sentence_repair.dart';
import 'package:test/test.dart';

void main() {
  test('h2z converts halfwidth kana with voicing marks', () {
    expect(repairSentence('ﾄﾞﾗｺﾞﾝがｷﾀ!'), 'ドラゴンがキタ!');
    expect(repairSentence('ﾊﾟﾝとｳﾞｨｵﾗ'), 'パンとヴィオラ');
  });

  test('trims but never strips or repairs quotes', () {
    expect(repairSentence('　「もう帰るの？」　'), '「もう帰るの？」');
    expect(repairSentence('「あはは。'), '「あはは。');
    expect(repairSentence('彼は「うん」と言った。'), '彼は「うん」と言った。');
  });
}
