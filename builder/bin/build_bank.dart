/// Builds a DaDb Example Bank zip per work from a directory of {id}.txt +
/// {id}.json produced by the site parser.
///
/// Usage: dart run bin/build_bank.dart <text-dir> <out-dir> [--site=syosetu]
library;

import 'dart:convert';
import 'dart:io';

import 'package:builder/bank_builder.dart';
import 'package:language_processing/language_processing.dart';

void main(List<String> args) {
  final positional = args.where((a) => !a.startsWith('--')).toList();
  final textDir = Directory(positional[0]);
  final outDir = Directory(positional[1]);
  final site = args
          .where((a) => a.startsWith('--site='))
          .map((a) => a.substring('--site='.length))
          .firstOrNull ??
      'syosetu';

  final processor = JapaneseProcessor();
  final lpRef = _resolvedLanguageProcessingRef();
  final summary = <Map<String, dynamic>>[];

  for (final file in textDir.listSync().whereType<File>()) {
    if (!file.path.endsWith('.txt')) continue;
    final workId = file.uri.pathSegments.last.replaceAll('.txt', '');
    final metaFile = File(file.path.replaceAll('.txt', '.json'));
    final meta = metaFile.existsSync()
        ? jsonDecode(metaFile.readAsStringSync()) as Map<String, dynamic>
        : <String, dynamic>{};

    final sentences = extractSentences(file.readAsStringSync(), processor);
    final count = buildBankZip(
      site: site,
      workId: workId,
      workTitle: meta['title'] as String? ?? workId,
      workUrl: meta['url'] as String? ?? '',
      sentences: sentences,
      outDir: outDir,
      languageProcessingRef: lpRef,
    );
    summary.add({
      'id': workId,
      'title': meta['title'] ?? workId,
      'url': meta['url'] ?? '',
      'chapters': meta['chapters'] ?? 0,
      'sentences': count,
      'bytes': File('${outDir.path}/corpus-$site-$workId.zip').lengthSync(),
      'revision': '$builderVersion+lp.${lpRef ?? 'local'}',
    });
    stdout.writeln('corpus-$site-$workId.zip: $count sentences');
  }

  File('${outDir.path}/build_summary.json')
      .writeAsStringSync(jsonEncode(summary));
}

/// The language_processing commit pinned in pubspec.lock, for the revision.
String? _resolvedLanguageProcessingRef() {
  final lock = File('pubspec.lock');
  if (!lock.existsSync()) return null;
  final m = RegExp(
    r'language_processing:.*?resolved-ref:\s*"?([0-9a-f]+)"?',
    dotAll: true,
  ).firstMatch(lock.readAsStringSync());
  return m == null ? null : m.group(1)!.substring(0, 12);
}
