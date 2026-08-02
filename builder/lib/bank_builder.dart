/// Builds DaDb Example Bank zips from clean per-work text.
///
/// Pipeline per work: extractExampleSentences -> corpus-{site}-{id}.zip
/// (index.json + tag_bank_1.json + example_bank_N.json). File order is
/// import order.
library;

import 'dart:convert';
import 'dart:io';

import 'package:archive/archive_io.dart';

const String builderVersion = '0.1.0';
const int sentencesPerBankFile = 2000;

/// corpus-{site}-{workId}.zip in [outDir]. Returns sentence count.
int buildBankZip({
  required String site,
  required String workId,
  required String workTitle,
  required String workUrl,
  required List<String> sentences,
  required Directory outDir,
  String? author,
  String? languageProcessingRef,
  int chunkSize = sentencesPerBankFile,
}) {
  final tag = '$site-$workId';
  final index = {
    'title': 'corpus-$tag',
    'revision': '$builderVersion+lp.${languageProcessingRef ?? 'local'}',
    'format': 3,
    'sequenced': true,
    'author': author,
    'url': workUrl,
    'description': '$workTitle — example sentences',
    'attribution': workUrl,
    'sourceLanguage': 'jpn',
  };
  final tagBank = [
    [tag, 'source', 0, workTitle, 0],
  ];

  final archive = Archive();
  void addJson(String name, Object json) {
    final bytes = utf8.encode(jsonEncode(json));
    archive.addFile(ArchiveFile(name, bytes.length, bytes));
  }

  addJson('index.json', index);
  addJson('tag_bank_1.json', tagBank);
  var fileNum = 0;
  for (var i = 0; i < sentences.length; i += chunkSize) {
    fileNum++;
    final chunk = sentences
        .sublist(i,
            i + chunkSize > sentences.length ? sentences.length : i + chunkSize)
        .map((s) => {
              'sentence': s,
              'tags': [tag]
            })
        .toList();
    addJson('example_bank_$fileNum.json', chunk);
  }

  outDir.createSync(recursive: true);
  final zipPath = '${outDir.path}/corpus-$tag.zip';
  final encoded = ZipEncoder().encode(archive);
  File(zipPath).writeAsBytesSync(encoded);
  return sentences.length;
}
