/// Reject-histogram review: split .txt files, filter every sentence,
/// print counts per reason with samples.
///
/// Usage: dart run bin/reject_histogram.dart <dir-with-txt> [samples-per-reason]
///        [--accepted=<path>]  also write accepted sentences, one per line
library;

import 'dart:io';
import 'dart:math';

import 'package:language_processing/language_processing.dart';

void main(List<String> args) {
  final acceptedArg = args
      .where((a) => a.startsWith('--accepted='))
      .map((a) => a.substring('--accepted='.length))
      .firstOrNull;
  final positional = args.where((a) => !a.startsWith('--')).toList();
  final dir = Directory(positional[0]);
  final samplesPerReason = positional.length > 1 ? int.parse(positional[1]) : 8;
  final acceptedSink =
      acceptedArg == null ? null : File(acceptedArg).openWrite();

  final processor = JapaneseProcessor();
  const options = ProcessorOptions();

  final counts = <String, int>{};
  final samples = <String, List<String>>{};
  final seen = <String>{};
  var total = 0;
  final rng = Random(42);

  final files = dir
      .listSync()
      .whereType<File>()
      .where((f) => f.path.endsWith('.txt'))
      .toList();
  for (final file in files) {
    // Per-paragraph split: bounds runaway-bracket damage to one paragraph.
    for (final line in file.readAsLinesSync()) {
      if (line.trim().isEmpty) continue;
      for (final seg in processor.findSentences(line, options)) {
        final sentence = processor.repairSentence(seg.text, options);
        if (sentence.isEmpty) continue;
        total++;
        var reason = processor.sentenceRejectionReason(sentence, options);
        if (reason == null && !seen.add(sentence)) reason = 'duplicate';
        if (reason == null) acceptedSink?.writeln(sentence);
        final key = reason ?? 'ACCEPT';
        counts[key] = (counts[key] ?? 0) + 1;
        final bucket = samples.putIfAbsent(key, () => []);
        // Reservoir sampling so samples aren't all from the first file.
        if (bucket.length < samplesPerReason) {
          bucket.add(sentence);
        } else if (rng.nextInt(counts[key]!) < samplesPerReason) {
          bucket[rng.nextInt(samplesPerReason)] = sentence;
        }
      }
    }
  }

  // Quoted segments are a category (dialogue), not failed sentences: they
  // leave the denominator before accept/reject percentages are computed.
  final quoted = counts.remove('quoted') ?? 0;
  final candidates = total - quoted;
  stdout.writeln('files: ${files.length}, segments: $total');
  stdout.writeln('quoted (dialogue, not sentences): $quoted');
  stdout.writeln('candidate sentences: $candidates\n');
  final order = counts.keys.toList()
    ..sort((a, b) => counts[b]!.compareTo(counts[a]!));
  for (final reason in order) {
    final n = counts[reason]!;
    final pct = (n * 100 / candidates).toStringAsFixed(2);
    stdout.writeln('$reason: $n ($pct%)');
  }
  for (final reason
      in order.where((r) => r != 'ACCEPT').followedBy(['quoted'])) {
    final bucket = samples[reason];
    if (bucket == null) continue;
    stdout.writeln('\n== $reason');
    for (final s in bucket) {
      final short = s.length > 90 ? '${s.substring(0, 90)}…' : s;
      stdout.writeln('  | $short');
    }
  }
  acceptedSink?.close();
}
