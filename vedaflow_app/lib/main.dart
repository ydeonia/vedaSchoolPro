import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'core/app.dart';
import 'core/config.dart';
import 'core/storage.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Lock portrait orientation
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  // Initialize Hive for offline storage
  await Hive.initFlutter();
  await LocalStorage.init();

  // Load school config (white-label settings baked at build time)
  await AppConfig.load();

  runApp(
    const ProviderScope(
      child: VedaFlowApp(),
    ),
  );
}
