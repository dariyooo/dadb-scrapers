import 'dart:convert';
import 'dart:io';

import 'package:archive/archive_io.dart';
import 'package:builder/bank_builder.dart';
import 'package:language_processing/language_processing.dart';
import 'package:test/test.dart';

void main() {
  final processor = JapaneseProcessor();

  test('extractSentences splits, filters, dedups in text order', () {
    const text = '今日は天気がいいから散歩に行こう。空がとても青いのだ。\n'
        '「これは会話だから入らない」\n'
        '今日は天気がいいから散歩に行こう。\n';
    final sentences = extractSentences(text, processor);
    expect(sentences, [
      '今日は天気がいいから散歩に行こう。',
      '空がとても青いのだ。',
    ]);
  });

  test('buildBankZip emits importable structure with chunking', () {
    final tmp = Directory.systemTemp.createTempSync('bank_test');
    addTearDown(() => tmp.deleteSync(recursive: true));

    final sentences = List.generate(5, (i) => '文番号$iの内容がここにある。');
    final count = buildBankZip(
      site: 'syosetu',
      workId: 'n0000aa',
      workTitle: 'テスト小説',
      workUrl: 'https://ncode.syosetu.com/n0000aa/',
      sentences: sentences,
      outDir: tmp,
      author: '作者名',
      languageProcessingRef: 'abc123',
      chunkSize: 2,
    );
    expect(count, 5);

    final archive = ZipDecoder().decodeBytes(
        File('${tmp.path}/corpus-syosetu-n0000aa.zip').readAsBytesSync());
    final names = archive.files.map((f) => f.name).toSet();
    expect(names, {
      'index.json',
      'tag_bank_1.json',
      'example_bank_1.json',
      'example_bank_2.json',
      'example_bank_3.json',
    });

    Object readJson(String name) => jsonDecode(
        utf8.decode(archive.files.firstWhere((f) => f.name == name).content));

    final index = readJson('index.json') as Map<String, dynamic>;
    expect(index['title'], 'corpus-syosetu-n0000aa');
    expect(index['format'], 3);
    expect(index['sourceLanguage'], 'jpn');
    expect(index['revision'], contains('abc123'));

    final bank1 = readJson('example_bank_1.json') as List;
    expect(bank1, hasLength(2));
    expect((bank1.first as Map)['sentence'], sentences.first);
    expect((bank1.first as Map)['tags'], ['syosetu-n0000aa']);

    final tags = readJson('tag_bank_1.json') as List;
    expect((tags.first as List).first, 'syosetu-n0000aa');
  });
}
